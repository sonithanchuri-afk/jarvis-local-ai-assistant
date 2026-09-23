import customtkinter as ctk
import tkinter as tk
import threading
import queue
import time
import math
import os
import subprocess
import webbrowser
import json
import datetime
import re
import sys
import shutil
import platform
from pathlib import Path

# Optional voice packages
try:
    import speech_recognition as sr
except Exception:
    sr = None

# The cloned voice runs in its own Python 3.11 process because the main
# JARVIS environment currently uses Python 3.14.
try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    import sounddevice as sd
    import numpy as np
except Exception:
    sd = None
    np = None

# Optional Ollama HTTP client
try:
    import requests
except Exception:
    requests = None

try:
    import psutil
except Exception:
    psutil = None

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import cv2
except Exception:
    cv2 = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None


# ============================================================
# CONFIGURATION
# ============================================================

APP_TITLE = "JARVIS // COMMAND CENTER"
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "llama3"
RAG_EMBED_MODEL = "nomic-embed-text"

BG = "#05080D"
PANEL = "#0A1018"
PANEL2 = "#0D1520"
LINE = "#1A2A3A"
CYAN = "#00D9FF"
CYAN2 = "#35E8FF"
TEXT = "#DCEFFF"
MUTED = "#71869A"
GREEN = "#37F59A"
ORANGE = "#FFB347"
RED = "#FF5B6E"

FONT = "Segoe UI"

BASE = Path(__file__).resolve().parent
# Make JARVIS portable: all local files are resolved relative to jarvis.py,
# regardless of where Python was launched from (Downloads, Desktop, USB, etc.).
os.chdir(BASE)
MEMORY_FILE = BASE / "memory.json"
CODE_OUTPUT = BASE / "generated_code"
PLAN_OUTPUT = BASE / "weekend_plans"
CODE_OUTPUT.mkdir(exist_ok=True)
PLAN_OUTPUT.mkdir(exist_ok=True)
TASK_FILE = BASE / "tasks.json"
SCHEDULE_FILE = BASE / "schedule.json"
RESEARCH_OUTPUT = BASE / "research_reports"
VISION_OUTPUT = BASE / "vision_captures"
WORKFLOW_OUTPUT = BASE / "workflow_logs"
for _d in (RESEARCH_OUTPUT, VISION_OUTPUT, WORKFLOW_OUTPUT): _d.mkdir(exist_ok=True)

# Startup audio and cloned-voice reference are separate files.
# Welcome.mp3 is the startup sound.
# Welcome.wav is the XTTS-v2 speaker reference.
WELCOME_SOUND = BASE / "Welcome.mp3"
VOICE_REFERENCE = BASE / "Welcome.wav"
VOICE_CACHE = BASE / "voice_cache"
VOICE_CACHE.mkdir(exist_ok=True)

# Local RAG knowledge base
KNOWLEDGE_DIR = BASE / "knowledge"
RAG_INDEX_FILE = BASE / "rag_index.json"
KNOWLEDGE_DIR.mkdir(exist_ok=True)
RAG_CHUNK_SIZE = 900
RAG_CHUNK_OVERLAP = 150
RAG_TOP_K = 4


# ============================================================
# GLOBAL STATE
# ============================================================

ui_queue = queue.Queue()
tts_queue = queue.Queue()

state = {
    "page": "HOME",
    "visible": False,
    "running": True,
    "listening": False,
    "ollama": False,
    "wake_word": False,
    "clap": False,
    "closing": False,
    "last_command": "System initialized",
    "last_response": "Awaiting command",
    "tasks": [],
    "messages": [],
    "ui_clock": "",
    "startup_audio_process": None,
    "rag_status": "Starting...",
}


# ============================================================
# UTILITIES
# ============================================================

def ui_call(fn, *args, **kwargs):
    ui_queue.put((fn, args, kwargs))


def safe_open(path_or_url):
    try:
        if isinstance(path_or_url, str) and (
            path_or_url.startswith("http://") or path_or_url.startswith("https://")
        ):
            webbrowser.open(path_or_url)
        else:
            os.startfile(path_or_url)
        return True
    except Exception as e:
        print("[JARVIS] Open error:", e)
        return False


def load_memory():
    try:
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {"facts": [], "conversations": []}


memory = load_memory()


def save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2)
    except Exception as e:
        print("[JARVIS] Memory save error:", e)


# ============================================================
# LOCAL RAG KNOWLEDGE BASE
# ============================================================
RAG_SUPPORTED = {".txt", ".md", ".py", ".js", ".html", ".css", ".json", ".csv", ".c", ".cpp", ".h", ".hpp", ".java", ".m", ".ps1", ".bat", ".log", ".xml", ".yaml", ".yml", ".docx", ".pdf"}

def _read_knowledge_file(path):
    try:
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
        if path.suffix.lower() == ".docx":
            from docx import Document
            return "\n".join(p.text for p in Document(str(path)).paragraphs)
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[JARVIS RAG] Could not read {path.name}: {e}")
        return ""

def _chunk_text(text):
    text = re.sub(r"\s+", " ", str(text)).strip()
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + RAG_CHUNK_SIZE)
        if text[start:end].strip(): chunks.append(text[start:end].strip())
        if end >= len(text): break
        start = max(end - RAG_CHUNK_OVERLAP, start + 1)
    return chunks

def _ollama_embed(texts):
    if requests is None or not texts: return []
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embed", json={"model": RAG_EMBED_MODEL, "input": texts}, timeout=90)
        r.raise_for_status()
        return r.json().get("embeddings", [])
    except Exception as e:
        print("[JARVIS RAG] Embedding error:", e)
        return []

def _load_rag_index():
    try:
        if RAG_INDEX_FILE.exists():
            with open(RAG_INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("chunks"), list): return data
    except Exception as e: print("[JARVIS RAG] Index load error:", e)
    return {"model": RAG_EMBED_MODEL, "chunks": []}

def _save_rag_index(data):
    try:
        tmp = RAG_INDEX_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)
        tmp.replace(RAG_INDEX_FILE)
        return True
    except Exception as e:
        print("[JARVIS RAG] Index save error:", e)
        return False

def rag_index_knowledge():
    files = [p for p in KNOWLEDGE_DIR.rglob("*") if p.is_file() and p.suffix.lower() in RAG_SUPPORTED]
    raw = []
    for path in files:
        for n, chunk in enumerate(_chunk_text(_read_knowledge_file(path))):
            raw.append({"source": str(path.relative_to(KNOWLEDGE_DIR)), "chunk": n, "text": chunk})
    if not raw:
        _save_rag_index({"model": RAG_EMBED_MODEL, "chunks": []})
        state["rag_status"] = "No knowledge files"
        return 0
    vectors = []
    for i in range(0, len(raw), 16):
        part = _ollama_embed([x["text"] for x in raw[i:i+16]])
        if len(part) != len(raw[i:i+16]):
            state["rag_status"] = "Embedding model unavailable"
            return 0
        vectors.extend(part)
    for item, vec in zip(raw, vectors): item["embedding"] = vec
    _save_rag_index({"model": RAG_EMBED_MODEL, "updated": datetime.datetime.now().isoformat(), "files": len(files), "chunks": raw})
    state["rag_status"] = f"Ready: {len(files)} files / {len(raw)} chunks"
    print(f"[JARVIS RAG] Indexed {len(files)} files into {len(raw)} chunks.")
    return len(raw)

def _cosine_similarity(a, b):
    if not a or not b or len(a) != len(b): return -1.0
    dot = sum(x*y for x,y in zip(a,b)); na = sum(x*x for x in a) ** 0.5; nb = sum(y*y for y in b) ** 0.5
    return dot/(na*nb) if na and nb else -1.0

def rag_retrieve(query, top_k=RAG_TOP_K):
    chunks = _load_rag_index().get("chunks", [])
    qv = _ollama_embed([query])
    if not chunks or not qv: return []
    scored = [(_cosine_similarity(qv[0], x.get("embedding", [])), x) for x in chunks]
    scored = [(s,x) for s,x in scored if s >= 0]
    scored.sort(key=lambda z:z[0], reverse=True)
    return scored[:top_k]

def rag_answer(query):
    results = rag_retrieve(query)
    if not results: return None
    context = "\n\n---\n\n".join(f"SOURCE: {x.get('source','unknown')}\nCONTENT: {x.get('text','')}" for _,x in results)
    sources = list(dict.fromkeys(x.get("source", "unknown") for _,x in results))
    prompt = ("You are JARVIS using a local RAG knowledge base. Answer using only the retrieved "
              "source material. Do not invent unsupported facts. If it is insufficient, say so. "
              "Keep the answer practical and concise.\n\nRETRIEVED KNOWLEDGE:\n" + context +
              "\n\nUSER QUESTION:\n" + query)
    answer = ask_ollama(prompt)
    if not answer.lower().startswith("ollama error:") and sources:
        answer += "\n\nSources: " + ", ".join(sources)
    return answer

# ============================================================
# OLLAMA
# ============================================================

def check_ollama():
    if requests is None:
        return False
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        if r.ok:
            models = [m.get("name", "") for m in r.json().get("models", [])]
            return any(x == OLLAMA_MODEL or x.startswith(OLLAMA_MODEL + ":") for x in models)
    except Exception:
        pass
    return False


def start_ollama_if_needed():
    global state
    if check_ollama():
        state["ollama"] = True
        return

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for _ in range(15):
            time.sleep(1)
            if check_ollama():
                state["ollama"] = True
                return
    except Exception as e:
        print("[JARVIS] Could not start Ollama:", e)

    state["ollama"] = False


def ask_ollama(prompt):
    if requests is None:
        return "Requests is not installed."

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are JARVIS, a concise desktop AI assistant. "
                            "Answer naturally and practically. Keep normal answers short."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "temperature": 0.4,
                    "num_predict": 180,
                    "num_ctx": 2048,
                },
            },
            timeout=45,
        )
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "No response received.")
    except Exception as e:
        state["ollama"] = False
        return f"Ollama error: {e}"


# ============================================================
# TTS
# ============================================================

voice_server = None
voice_server_lock = threading.Lock()
voice_server_ready = threading.Event()


def initialize_cloned_voice():
    """Start one persistent XTTS server and keep it alive for all responses."""
    global voice_server

    with voice_server_lock:
        if voice_server is not None and voice_server.poll() is None:
            return True

        voice_python = BASE / ".voice_env" / "Scripts" / "python.exe"

        server_candidates = [
            BASE / "jarvis_voice_server_TORCHCODEC_FREE_FIXED.py",
            BASE / "jarvis_voice_server.py",
        ]
        server_file = next((p for p in server_candidates if p.exists()), None)

        if not voice_python.exists() or server_file is None:
            print("[JARVIS VOICE] Voice environment/server is missing.")
            return False

        if not VOICE_REFERENCE.exists():
            print(f"[JARVIS VOICE] Voice reference not found: {VOICE_REFERENCE}")
            return False

        try:
            env = os.environ.copy()
            env["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"

            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            voice_server = subprocess.Popen(
                [
                    str(voice_python),
                    str(server_file),
                    str(VOICE_REFERENCE),
                    str(VOICE_CACHE),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                creationflags=flags,
                env=env,
            )

            voice_server_ready.clear()
            print("[JARVIS VOICE] XTTS server warming up...")
            return True

        except Exception as e:
            print("[JARVIS VOICE] Could not start voice server:", e)
            voice_server = None
            return False


def windows_speak(text):
    """Send text to the persistent cloned-voice server."""
    if not text:
        return

    # XTTS generation time grows strongly with text length.
    # Keep spoken responses concise while leaving the full text in the UI.
    spoken_text = re.sub(r"\\s+", " ", str(text)).strip()
    if len(spoken_text) > 420:
        spoken_text = spoken_text[:417].rsplit(" ", 1)[0] + "..."

    if initialize_cloned_voice():
        try:
            with voice_server_lock:
                if voice_server is not None and voice_server.poll() is None:
                    voice_server.stdin.write(spoken_text.replace("\n", " ") + "\n")
                    voice_server.stdin.flush()
                    return
        except Exception as e:
            print("[JARVIS VOICE] Clone server playback failed:", e)

    # Windows SAPI fallback.
    safe_text = spoken_text.replace('"', "'")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Volume=100; $s.Rate=0; "
        "$s.Speak(\"" + safe_text.replace("\\", " ") + "\"); "
        "$s.Dispose()"
    )
    try:
        subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-Command", ps
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print("[JARVIS] Fallback TTS error:", e)


def tts_worker():
    print("[JARVIS] Cloned voice output worker ready.")
    while state["running"]:
        try:
            text = tts_queue.get(timeout=0.3)
        except queue.Empty:
            continue
        if text:
            windows_speak(text)


def speak(text):
    if text:
        tts_queue.put(str(text))



# ============================================================
# STARTUP / WELCOME AUDIO
# ============================================================

STARTUP_MUSIC = BASE / "Startup Music.mp3"


def play_mp3_async(path, duration_seconds):
    """Play an MP3 reliably with Windows' built-in WPF MediaPlayer."""
    path = Path(path)

    if not path.exists():
        print(f"[JARVIS AUDIO ERROR] File not found: {path}")
        return None

    # Convert to a PowerShell-safe absolute Windows path.
    ps_path = str(path.resolve()).replace("'", "''")
    duration_ms = int(duration_seconds * 1000)

    # MediaPlayer.Open() is asynchronous. The old version started playback
    # too early, which could result in silence. This version waits until
    # NaturalDuration is available before calling Play().
    script = f"""
Add-Type -AssemblyName PresentationCore

$p = New-Object System.Windows.Media.MediaPlayer
$p.Volume = 1.0
$p.Open([System.Uri]'{ps_path}')

$timeout = 0
while (-not $p.NaturalDuration.HasTimeSpan -and $timeout -lt 10000) {{
    Start-Sleep -Milliseconds 100
    $timeout += 100
}}

if ($p.NaturalDuration.HasTimeSpan) {{
    $p.Play()
    Start-Sleep -Milliseconds {duration_ms}
}}

$p.Stop()
$p.Close()
"""

    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return process

    except Exception as e:
        print("[JARVIS AUDIO ERROR]", e)
        return None

def start_startup_music():
    if state.get("startup_audio_process") is not None:
        return None
    process = play_mp3_async(STARTUP_MUSIC, 98.04)
    state["startup_audio_process"] = process
    if process is not None:
        print("[JARVIS] Startup music playing.")
    return process


def stop_startup_music():
    process = state.get("startup_audio_process")
    if process is not None:
        try:
            process.terminate()
        except Exception:
            pass
        state["startup_audio_process"] = None


def play_welcome_sound():
    process = play_mp3_async(WELCOME_SOUND, 1.65)
    if process is not None:
        print("[JARVIS] Welcome sound playing.")
    return process


def play_startup_sequence():
    """
    Startup audio is strictly sequential:
      1. Welcome.mp3
      2. Startup Music.mp3
    No overlap.
    """
    welcome_process = play_welcome_sound()

    if welcome_process is not None:
        try:
            welcome_process.wait(timeout=8)
        except Exception:
            pass

    if not state.get("running", True):
        return

    start_startup_music()


# ============================================================
# CODE MODE + WEEKEND PLANNER
# ============================================================

def save_text_file(folder, filename, content):
    folder = Path(folder)
    folder.mkdir(exist_ok=True)
    path = folder / filename
    path.write_text(content, encoding="utf-8")
    return path


def code_extension(language):
    lang = language.lower()
    mapping = {
        "python": ".py", "py": ".py",
        "c++": ".cpp", "cpp": ".cpp",
        "c": ".c", "arduino": ".ino",
        "matlab": ".m", "html": ".html", "css": ".css",
        "javascript": ".js", "js": ".js", "java": ".java",
        "json": ".json", "bash": ".sh", "powershell": ".ps1",
    }
    return mapping.get(lang, ".txt")


def extract_code_block(text):
    """Remove markdown fences if the model returned them."""
    text = str(text).strip()
    m = re.search(r"```(?:[\w+#.-]+)?\s*(.*?)```", text, flags=re.S)
    if m:
        return m.group(1).strip()
    return text


def detect_language(command):
    low = command.lower()
    for name in ("python", "c++", "cpp", "c", "arduino", "matlab", "html", "css", "javascript", "js", "java", "powershell", "bash"):
        if re.search(rf"\b{re.escape(name)}\b", low):
            return name
    return "python"


def code_mode(command):
    """Generate code with Llama, save it as a normal source file, and return a short result."""
    language = detect_language(command)
    request = re.sub(r"^(?:create|write|generate|make|build)\s+(?:a\s+)?(?:code|program|script)\s*", "", command, flags=re.I).strip()
    if not request:
        request = command

    prompt = f"""You are JARVIS CODE MODE.\nLanguage: {language}\nTask: {request}\n\nReturn ONLY the complete source code. No markdown fences. No explanation. Make it runnable and include sensible comments only where useful."""
    code = extract_code_block(ask_ollama(prompt))
    if code.lower().startswith("ollama error:"):
        return code

    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", request.lower()).strip("_")[:48] or "jarvis_program"
    filename = f"{safe_name}{code_extension(language)}"
    path = save_text_file(CODE_OUTPUT, filename, code)
    return f"Code generated in {language} and saved as {path.name}."


def weekend_planner(command):
    """Create a fast local Saturday/Sunday plan without waiting for Ollama."""
    now = datetime.datetime.now()

    # Support both the old list format and dictionary-style memory formats.
    raw_facts = memory.get("facts", [])
    if isinstance(raw_facts, dict):
        facts = [str(k) + ": " + str(v) for k, v in raw_facts.items()]
    elif isinstance(raw_facts, list):
        facts = [str(x) for x in raw_facts[-10:]]
    else:
        facts = []

    # Build the plan locally so this command responds immediately even when
    # Ollama is busy warming up or generating another response.
    saturday = now + datetime.timedelta(days=(5 - now.weekday()) % 7)
    if now.weekday() == 5:
        saturday = now
    sunday = saturday + datetime.timedelta(days=1)

    plan = (
        f"WEEKEND PLAN — {saturday:%d %B} & {sunday:%d %B}\n\n"
        "SATURDAY\n"
        "08:00–08:30  Wake up + water + breakfast\n"
        "08:30–10:30  Major project / engineering work\n"
        "10:30–11:00  Break\n"
        "11:00–13:00  Coding / technical learning\n"
        "13:00–14:00  Lunch + rest\n"
        "14:00–16:00  BAJA / CAD / project work\n"
        "16:00–17:00  Exercise / outdoor time\n"
        "17:00–19:00  Gaming / movies / free time\n"
        "19:00–20:00  Dinner\n"
        "20:00–21:30  Light study + plan next week\n"
        "21:30–23:00  Relax / hobby\n"
        "23:00  Wind down and sleep\n\n"
        "SUNDAY\n"
        "08:00–09:00  Wake up + breakfast\n"
        "09:00–11:00  Major project deep-work block\n"
        "11:00–11:30  Break\n"
        "11:30–13:00  Python / interview preparation\n"
        "13:00–14:00  Lunch + rest\n"
        "14:00–16:00  CAD / mechanical engineering practice\n"
        "16:00–17:00  Exercise / outdoor time\n"
        "17:00–19:00  Free time\n"
        "19:00–20:00  Dinner\n"
        "20:00–21:00  Review completed work + Monday preparation\n"
        "21:00–22:30  Relax\n"
        "22:30  Wind down and sleep\n\n"
        "TOP 3 PRIORITIES\n"
        "1. Major project progress\n"
        "2. Coding / interview preparation\n"
        "3. Exercise + proper sleep\n"
    )

    if facts:
        plan += "\nMEMORY CONSIDERED\n" + "\n".join("• " + x for x in facts[-3:])

    filename = f"weekend_plan_{now:%Y%m%d_%H%M%S}.txt"
    path = save_text_file(PLAN_OUTPUT, filename, plan)
    return f"Weekend plan created and saved as {path.name}.\n\n{plan}"


def handle_special_modes(low, command):
    """Return (handled, response) for CODE MODE and WEEKEND PLANNER."""
    if low in {"code mode", "enter code mode", "activate code mode"}:
        return True, "Code Mode is ready. Tell me the language and what you want to build."

    if low in {"weekend planner", "plan my weekend", "plan weekend", "weekend plan"}:
        return True, weekend_planner(command)

    code_trigger = (
        low.startswith("create code") or low.startswith("write code") or
        low.startswith("generate code") or low.startswith("make code") or
        low.startswith("build code") or low.startswith("code for ") or
        low.startswith("write a python") or low.startswith("create a python") or
        low.startswith("write a c++") or low.startswith("create a c++") or
        low.startswith("write a matlab") or low.startswith("create a matlab") or
        low.startswith("write an arduino") or low.startswith("create an arduino")
    )
    if code_trigger:
        return True, code_mode(command)

    if "weekend" in low and any(x in low for x in ("plan", "schedule", "organize")):
        return True, weekend_planner(command)

    return False, ""


# ============================================================
# DESKTOP AUTOMATION MODE
# ============================================================

FLIGHTRADAR_URL = "https://www.flightradar24.com"


def open_chrome_url(url):
    """Open a URL in Chrome when available, otherwise use the default browser."""
    try:
        result = subprocess.run(
            ["cmd", "/c", "where", "chrome.exe"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        chrome = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        if chrome:
            subprocess.Popen([chrome, url], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True
    except Exception:
        pass

    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


def open_desktop_target(target):
    """Open common Windows applications, folders, and websites."""
    low = target.lower().strip()

    sites = {
        "flightradar24": FLIGHTRADAR_URL,
        "flight radar": FLIGHTRADAR_URL,
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
        "chatgpt": "https://chatgpt.com",
    }
    for name, url in sites.items():
        if name in low:
            return open_chrome_url(url), f"Opening {name.title()} in Chrome."

    apps = {
        "calculator": ["calc.exe"],
        "calc": ["calc.exe"],
        "notepad": ["notepad.exe"],
        "file explorer": ["explorer.exe"],
        "explorer": ["explorer.exe"],
    }
    for name, command in apps.items():
        if name in low:
            try:
                subprocess.Popen(command)
                return True, f"Opening {name.title()}."
            except Exception:
                return False, f"I could not open {name.title()}."

    if "solidworks" in low:
        try:
            subprocess.Popen("start sldworks", shell=True)
            return True, "Opening SolidWorks."
        except Exception:
            return False, "I could not open SolidWorks."

    if "jarvis folder" in low or "project folder" in low:
        try:
            os.startfile(str(BASE))
            return True, "Opening the JARVIS project folder."
        except Exception:
            return False, "I could not open the JARVIS folder."

    if low.startswith("http://") or low.startswith("https://"):
        return open_chrome_url(target), "Opening the requested website."

    return False, ""


def desktop_automation(command):
    """Handle fast, deterministic desktop commands without asking Ollama."""
    low = command.lower().strip()

    # Search commands must be checked before generic Google opening.
    if "search google for " in low:
        query=command.split("search google for ",1)[1].strip()
        if query:
            from urllib.parse import quote
            open_chrome_url("https://www.google.com/search?q="+quote(query))
            return f"Searching Google for {query}."
    if low.startswith("search for "):
        query=command[len("search for "):].strip()
        if query:
            from urllib.parse import quote
            open_chrome_url("https://www.google.com/search?q="+quote(query))
            return f"Searching Google for {query}."

    # Direct website/application commands.
    handled, response = open_desktop_target(low)
    if handled:
        return response

    if "search google for " in low:
        query = command.split("search google for ", 1)[1].strip()
        if query:
            from urllib.parse import quote
            url = "https://www.google.com/search?q=" + quote(query)
            open_chrome_url(url)
            return f"Searching Google for {query}."

    if low.startswith("search for "):
        query = command[len("search for "):].strip()
        if query:
            from urllib.parse import quote
            open_chrome_url("https://www.google.com/search?q=" + quote(query))
            return f"Searching Google for {query}."

    if "take a screenshot" in low or low == "screenshot":
        try:
            import pyautogui
            filename = BASE / f"screenshot_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
            pyautogui.screenshot(str(filename))
            return f"Screenshot saved as {filename.name}."
        except Exception:
            return "Screenshot requires pyautogui."

    if low in {"start work session", "start my work session", "open my workspace"}:
        actions = []
        ok, msg = open_desktop_target("solidworks")
        actions.append(msg if ok else "SolidWorks could not be opened")
        ok, msg = open_desktop_target("jarvis folder")
        actions.append(msg if ok else "JARVIS folder could not be opened")
        open_chrome_url(FLIGHTRADAR_URL)
        actions.append("FlightRadar24 opened in Chrome")
        return "Work session started. " + " ".join(actions) + "."

    if low in {"start research mode", "research mode", "start research"}:
        open_chrome_url("https://www.google.com")
        return "Research mode started in Chrome."

    if low in {"open engineering workspace", "engineering workspace"}:
        open_desktop_target("solidworks")
        open_desktop_target("jarvis folder")
        return "Engineering workspace opened."

    return ""


# ============================================================
# JARVIS V28 ALL-IN-ONE AGENT LAYER
# ============================================================

def _json_load(path, default):
    try:
        if path.exists(): return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e: print("[JARVIS] JSON load error:", e)
    return default

def _json_save(path, data):
    try:
        tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8"); tmp.replace(path); return True
    except Exception as e: print("[JARVIS] JSON save error:",e); return False

def persistent_tasks():
    data=_json_load(TASK_FILE,[]); return data if isinstance(data,list) else []

def add_persistent_task(text,due=None):
    tasks=persistent_tasks(); tasks.append({"id":datetime.datetime.now().strftime("%Y%m%d%H%M%S%f"),"text":text,"due":due,"done":False,"created":datetime.datetime.now().isoformat()}); _json_save(TASK_FILE,tasks); state["tasks"]=tasks
    return tasks[-1]

def task_list_response():
    tasks=persistent_tasks(); state["tasks"]=tasks; pending=[t for t in tasks if not t.get("done")]
    if not pending:return "You have no pending tasks."
    return "Pending tasks:\n"+"\n".join(f"{i+1}. {t['text']}"+(f" — due {t['due']}" if t.get("due") else "") for i,t in enumerate(pending[:20]))

def complete_persistent_task(target):
    tasks=persistent_tasks(); target=str(target).lower().strip(); found=False
    for i,t in enumerate(tasks):
        if (target.isdigit() and i+1==int(target)) or target in str(t.get("text","")).lower(): t["done"]=True; found=True; break
    _json_save(TASK_FILE,tasks); state["tasks"]=tasks; return found

def schedule_event(title,when):
    events=_json_load(SCHEDULE_FILE,[]); events=events if isinstance(events,list) else []
    events.append({"title":title,"when":when,"created":datetime.datetime.now().isoformat()}); _json_save(SCHEDULE_FILE,events); return events[-1]

def recent_context():
    return "\n".join(f"{r}: {m}" for r,m in state.get("messages",[])[-12:])

def smart_prompt(command):
    c=recent_context(); return ("Recent conversation:\n"+c+"\n\nCurrent request:\n"+command) if c else command

SAFE_EXT={".py",".txt",".md",".json",".csv",".html",".css",".js",".c",".cpp",".h",".hpp",".java",".m",".ps1",".bat",".ino",".log",".xml",".yaml",".yml"}

def local_path(raw):
    q=str(raw).strip().strip('"').strip("'"); p=Path(q); return (p if p.is_absolute() else BASE/p).resolve()

def file_agent(command):
    low=command.lower().strip()
    if low in {"open knowledge folder","open my knowledge folder"}: os.startfile(str(KNOWLEDGE_DIR)); return "Opening the knowledge folder."
    m=re.match(r"^(?:read|show)\s+(?:file\s+)?(.+)$",command,re.I)
    if m:
        p=local_path(m.group(1))
        if p.is_file():
            if p.suffix.lower() in SAFE_EXT:return f"FILE: {p.name}\n\n{p.read_text(encoding='utf-8',errors='ignore')[:7000]}"
            os.startfile(str(p)); return f"Opened {p.name}."
    m=re.match(r"^(?:create|make)\s+file\s+(.+)$",command,re.I)
    if m:
        spec=m.group(1); parts=re.split(r"\s+with\s+",spec,maxsplit=1,flags=re.I); p=local_path(parts[0]); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(parts[1] if len(parts)>1 else "",encoding="utf-8"); return f"Created {p.name}."
    m=re.match(r"^(?:open|launch)\s+folder\s+(.+)$",command,re.I)
    if m:
        p=local_path(m.group(1))
        if p.is_dir():os.startfile(str(p));return f"Opened folder {p.name}."
    return ""

def run_code(path):
    p=local_path(path)
    if not p.is_file():return f"File not found: {p}"
    try:
        if p.suffix.lower()==".py": r=subprocess.run([sys.executable,str(p)],capture_output=True,text=True,timeout=30,cwd=str(p.parent))
        elif p.suffix.lower()==".ps1": r=subprocess.run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(p)],capture_output=True,text=True,timeout=30,cwd=str(p.parent))
        else:return "Direct execution currently supports Python and PowerShell files."
        return f"Exit code: {r.returncode}\n{(r.stdout+'\n'+r.stderr).strip()[:7000]}"
    except subprocess.TimeoutExpired:return "Execution timed out after 30 seconds."
    except Exception as e:return f"Execution error: {e}"

def code_agent(command):
    m=re.match(r"^(?:run|execute)\s+(?:file\s+)?(.+)$",command,re.I)
    if m:return run_code(m.group(1))
    m=re.match(r"^debug\s+(.+\.py)$",command,re.I)
    if m:
        p=local_path(m.group(1)); result=run_code(str(p))
        if p.is_file() and "Exit code: 0" not in result:
            prompt="Return ONLY corrected Python source. Fix this file using the runtime error.\nFILE:\n"+p.read_text(encoding="utf-8",errors="ignore")[:14000]+"\nERROR:\n"+result
            fixed=extract_code_block(ask_ollama(prompt))
            if not fixed.lower().startswith("ollama error:"):
                shutil.copy2(p,p.with_suffix(p.suffix+'.bak')); p.write_text(fixed,encoding="utf-8"); return f"Fixed {p.name}. Re-run result:\n{run_code(str(p))}"
    return ""

def engineering_agent(command):
    low=command.lower(); n=[float(x) for x in re.findall(r"[-+]?\d*\.?\d+",command)]
    if "gear ratio" in low and len(n)>=2:return f"Gear ratio = {n[0]/n[1]:.4f}:1."
    if "power" in low and "torque" in low and "rpm" in low and len(n)>=2:return f"Mechanical power = {n[0]*2*math.pi*n[1]/60/1000:.3f} kW."
    if "torque" in low and "power" in low and "rpm" in low and len(n)>=2:return f"Torque = {n[0]*1000*60/(2*math.pi*n[1]):.3f} N·m."
    if "kinetic energy" in low and len(n)>=2:return f"Kinetic energy = {0.5*n[0]*n[1]**2:.2f} J."
    if "acceleration" in low and "force" in low and "mass" in low and len(n)>=2:return f"Acceleration = {n[0]/n[1]:.4f} m/s²."
    if "second moment" in low and "circle" in low and n:return f"Solid circle I = {math.pi*n[0]**4/64:.6g} length⁴."
    if "km/h" in low and "m/s" in low and n:return f"{n[0]:g} km/h = {n[0]/3.6:.4f} m/s."
    if "m/s" in low and "km/h" in low and n:return f"{n[0]:g} m/s = {n[0]*3.6:.4f} km/h."
    return ""

def computer_agent(command):
    if pyautogui is None:return ""
    low=command.lower().strip()
    if low in {"computer screenshot","capture screen","screen capture"}:
        p=VISION_OUTPUT/f"screen_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"; pyautogui.screenshot(str(p)); return f"Screen capture saved as {p.name}."
    m=re.match(r"move mouse to\s+(\d+)\s*[, ]\s*(\d+)",low)
    if m:pyautogui.moveTo(int(m.group(1)),int(m.group(2)),duration=.2);return "Mouse moved."
    m=re.match(r"type\s+(.+)",command,re.I)
    if m:pyautogui.write(m.group(1),interval=.01);return "Text typed."
    m=re.match(r"press\s+(.+)",command,re.I)
    if m and m.group(1).lower() in {"enter","esc","escape","tab","space","backspace","delete","up","down","left","right","home","end"}:pyautogui.press("esc" if m.group(1).lower()=="escape" else m.group(1).lower());return f"Pressed {m.group(1)}."
    return ""

def vision_agent(command):
    if cv2 is None:return ""
    low=command.lower().strip()
    if low in {"camera snapshot","take camera snapshot","capture camera"}:
        cam=cv2.VideoCapture(0)
        if not cam.isOpened():return "I could not access the camera."
        ok,frame=cam.read();cam.release()
        if not ok:return "Camera capture failed."
        p=VISION_OUTPUT/f"camera_{datetime.datetime.now():%Y%m%d_%H%M%S}.jpg";cv2.imwrite(str(p),frame);return f"Camera snapshot saved as {p.name}. Resolution: {frame.shape[1]}x{frame.shape[0]}."
    if low in {"camera status","vision status"}:
        cam=cv2.VideoCapture(0);ok=cam.isOpened();cam.release();return "Camera is available." if ok else "Camera is not available."
    return ""

def research_agent(command):
    low=command.lower().strip(); triggers=("research ","research on ","find information about ","look up ")
    if not any(low.startswith(t) for t in triggers):return ""
    if requests is None or BeautifulSoup is None:return "Web research requires requests and beautifulsoup4."
    q=command
    for t in triggers:
        if low.startswith(t):q=command[len(t):].strip();break
    try:
        from urllib.parse import quote
        r=requests.get("https://html.duckduckgo.com/html/?q="+quote(q),headers={"User-Agent":"Mozilla/5.0"},timeout=15);r.raise_for_status();soup=BeautifulSoup(r.text,"html.parser")
        results=[]
        for x in soup.select('.result')[:6]:
            a=x.select_one('.result__a');sn=x.select_one('.result__snippet')
            if a:results.append((a.get_text(' ',strip=True),a.get('href',''),sn.get_text(' ',strip=True) if sn else ''))
        if not results:return "No research results were returned."
        summary=ask_ollama("Summarize these search results, distinguish snippets from verified facts, and keep source titles/URLs.\n\n"+"\n\n".join(f"{i+1}. {a}\n{b}\n{c}" for i,(a,b,c) in enumerate(results)))
        report="RESEARCH: "+q+"\n\n"+summary+"\n\nSOURCES\n"+"\n".join(f"- {a} — {b}" for a,b,c in results)
        fn=f"research_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt";(RESEARCH_OUTPUT/fn).write_text(report,encoding='utf-8');return report[:9000]
    except Exception as e:return f"Research error: {e}"

def autonomous_agent(command):
    low=command.lower().strip()
    if not low.startswith(("do ","handle ","take care of ")):return ""
    goal=re.sub(r"^(do|handle|take care of)\s+","",command,flags=re.I).strip()
    plan=ask_ollama("Create a short 3-6 step plan for this goal using coding, research, planning, files, or engineering. Return numbered steps.\nGOAL: "+goal)
    if plan.lower().startswith("ollama error:"):return plan
    actions=[]
    if "research" in goal.lower():actions.append(research_agent("research "+goal))
    if "weekend" in goal.lower() or "schedule" in goal.lower():actions.append(weekend_planner(goal))
    if "code" in goal.lower() or "python" in goal.lower():actions.append(code_mode(goal))
    if not actions:actions.append("Plan created. No unrecognized actions were executed automatically.")
    fn=f"workflow_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt";(WORKFLOW_OUTPUT/fn).write_text("GOAL: "+goal+"\n\nPLAN:\n"+plan+"\n\nEXECUTION:\n"+"\n\n".join(actions),encoding='utf-8')
    return f"Autonomous workflow completed. Log saved as {fn}.\n\nPLAN:\n{plan}\n\n"+"\n\n".join(actions)[:7000]

def advanced_agent_router(command):
    for fn in (file_agent,code_agent,engineering_agent,computer_agent,vision_agent,research_agent,autonomous_agent):
        try:
            r=fn(command)
            if r:return r
        except Exception as e:print("[JARVIS AGENT]",fn.__name__,e)
    return ""

state["tasks"]=persistent_tasks()

# ============================================================
# CHAT / COMMAND PROCESSING
# ============================================================

def add_message(role, text):
    state["messages"].append((role, text))
    state["messages"] = state["messages"][-100:]



def stop_voice_server():
    global voice_server
    if voice_server is not None:
        try:
            if voice_server.stdin:
                voice_server.stdin.close()
        except Exception:
            pass
        try:
            voice_server.terminate()
        except Exception:
            pass
        voice_server = None


def shutdown_jarvis():
    """Gracefully shut down the JARVIS Command Centre."""
    if state.get("closing"):
        return

    state["closing"] = True
    print("[JARVIS] Shutdown command received.")

    # Stop listeners immediately so they do not start another recording.
    state["running"] = False
    state["wake_word"] = False

    # Speak first, then close the Command Centre.
    speak("Goodbye. Shutting down the command centre.")
    ui_call(app.refresh)

    def finish_shutdown():
        stop_startup_music()
        stop_voice_server()
        try:
            app.destroy()
        except Exception:
            pass

    # Give the Windows voice engine time to finish speaking.
    try:
        app.after(1800, finish_shutdown)
    except Exception:
        finish_shutdown()



def process_command(command, speak_result=True):
    command = command.strip()
    if not command:
        return

    state["last_command"] = command
    add_message("YOU", command)

    low = command.lower()

    # V28 specialist agents.
    advanced_response = advanced_agent_router(command)
    if advanced_response:
        response=advanced_response
        state["last_response"]=response; add_message("JARVIS",response)
        memory.setdefault("conversations",[]).append({"time":datetime.datetime.now().isoformat(),"user":command,"jarvis":response})
        memory["conversations"]=memory["conversations"][-100:]; save_memory(); ui_call(app.refresh)
        if speak_result:speak(response)
        return

    # Fast desktop automation commands.
    automation_response = desktop_automation(command)
    if automation_response:
        response = automation_response
        state["last_response"] = response
        add_message("JARVIS", response)
        memory.setdefault("conversations", []).append(
            {"time": datetime.datetime.now().isoformat(), "user": command, "jarvis": response}
        )
        memory["conversations"] = memory["conversations"][-100:]
        save_memory()
        ui_call(app.refresh)
        if speak_result:
            speak(response)
        return

    # Fast special modes: code generation and weekend planning.
    handled_mode, mode_response = handle_special_modes(low, command)
    if handled_mode:
        response = mode_response
        state["last_response"] = response
        add_message("JARVIS", response)
        memory.setdefault("conversations", []).append(
            {"time": datetime.datetime.now().isoformat(), "user": command, "jarvis": response}
        )
        memory["conversations"] = memory["conversations"][-100:]
        save_memory()
        ui_call(app.refresh)
        if speak_result:
            speak(response)
        return

    # Shutdown command
    if re.search(r"\b(?:bye|goodbye)\s+jarvis\b", low):
        response = "Goodbye. Shutting down the command centre."
        state["last_response"] = response
        add_message("JARVIS", response)
        memory.setdefault("conversations", []).append(
            {
                "time": datetime.datetime.now().isoformat(),
                "user": command,
                "jarvis": response,
            }
        )
        memory["conversations"] = memory["conversations"][-100:]
        save_memory()
        ui_call(app.refresh)
        shutdown_jarvis()
        return

    # RAG / local knowledge commands
    if low in {"index knowledge", "index my knowledge", "refresh knowledge", "refresh rag", "build knowledge base"}:
        state["last_response"] = "Indexing local knowledge..."
        ui_call(app.refresh)
        count = rag_index_knowledge()
        response = f"Knowledge base indexed with {count} chunks." if count else "No readable knowledge was indexed. Add files to the knowledge folder."

    elif low in {"show knowledge", "knowledge status", "rag status"}:
        index = _load_rag_index()
        response = f"RAG status: {state.get('rag_status', 'Not indexed')}. Stored chunks: {len(index.get('chunks', []))}."

    elif low in {"open knowledge folder", "open my knowledge folder"}:
        try:
            os.startfile(str(KNOWLEDGE_DIR))
            response = "Opening the JARVIS knowledge folder."
        except Exception:
            response = "I could not open the knowledge folder."

    # Built-in commands
    if "open chrome" in low:
        safe_open("https://www.google.com/chrome/")
        response = "Opening Chrome."
        try:
            subprocess.Popen("start chrome", shell=True)
        except Exception:
            pass

    elif "open youtube" in low:
        safe_open("https://www.youtube.com")
        response = "Opening YouTube."

    elif "open google" in low:
        safe_open("https://www.google.com")
        response = "Opening Google."

    elif "open solidworks" in low:
        try:
            subprocess.Popen("start sldworks", shell=True)
            response = "Opening SolidWorks."
        except Exception:
            response = "I could not open SolidWorks."

    elif "open calculator" in low:
        try:
            subprocess.Popen("calc.exe")
            response = "Opening Calculator."
        except Exception:
            response = "I could not open Calculator."

    elif "open notepad" in low:
        try:
            subprocess.Popen("notepad.exe")
            response = "Opening Notepad."
        except Exception:
            response = "I could not open Notepad."

    elif "screenshot" in low:
        try:
            import pyautogui
            filename = BASE / f"screenshot_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
            pyautogui.screenshot(str(filename))
            response = f"Screenshot saved as {filename.name}."
        except Exception:
            response = "Screenshot requires pyautogui. Install it with pip install pyautogui."

    elif low in {"hello", "hi", "hey jarvis", "jarvis"}:
        response = "Yes. How can I help?"

    elif low in {"thanks", "thank you", "thanks jarvis"}:
        response = "You're welcome."

    elif "how are you" in low:
        response = "All systems are operational."

    elif "show code" in low or "open code" in low or "code mode" in low:
        ui_call(app.set_page, "TOOLS")
        response = "Opening Code Mode tools."

    elif "show weekend" in low or "open weekend" in low or "weekend planner" in low:
        ui_call(app.set_page, "CALENDAR")
        response = "Opening the weekend planner."

    elif "show dashboard" in low or "open dashboard" in low:
        ui_call(app.set_page, "DASHBOARD")
        response = "Opening dashboard."

    elif "open chat" in low or "show chat" in low:
        ui_call(app.set_page, "CHAT")
        response = "Opening chat."

    elif low.startswith("remember "):
        fact = command[9:].strip()
        if fact:
            if not isinstance(memory.get("facts"), list):
                memory["facts"] = []
            memory["facts"].append(fact)
            save_memory()
            response = "I'll keep that in memory."

    elif "what do you remember" in low:
        facts = memory.get("facts", [])
        if isinstance(facts, dict):
            facts = list(facts.values())
        elif not isinstance(facts, list):
            facts = [str(facts)] if facts else []
        response = "I remember: " + "; ".join(map(str, facts[-5:])) if facts else "I don't have any saved memories yet."

    elif (
        re.search(r"\bwhat(?:'s| is)\s+(?:the\s+)?time\b", low)
        or "what time" in low
        or "current time" in low
        or "tell me the time" in low
        or low == "time"
    ):
        # Read the exact clock value currently displayed in the top-left UI.
        display_time = state.get("ui_clock", "")
        response = (
            f"The time is {display_time}."
            if display_time
            else f"The time is {datetime.datetime.now().strftime('%H:%M:%S')}."
        )

    elif "date" in low or "today" == low:
        response = datetime.datetime.now().strftime("Today is %A, %d %B %Y.")

    else:
        state["last_response"] = "Searching knowledge..."
        ui_call(app.refresh)
        response = rag_answer(command)
        if response is None:
            state["last_response"] = "Thinking..."
            ui_call(app.refresh)
            response = ask_ollama(smart_prompt(command))

    state["last_response"] = response
    add_message("JARVIS", response)
    memory.setdefault("conversations", []).append(
        {
            "time": datetime.datetime.now().isoformat(),
            "user": command,
            "jarvis": response,
        }
    )
    memory["conversations"] = memory["conversations"][-100:]
    save_memory()

    ui_call(app.refresh)

    if speak_result:
        speak(response)


def submit_text():
    text = app.input_var.get().strip()
    if not text:
        return
    app.input_var.set("")
    threading.Thread(target=process_command, args=(text,), daemon=True).start()


# ============================================================
# SPEECH
# ============================================================
# ============================================================
# SOUNDDEVICE MICROPHONE CAPTURE (NO PYAUDIO)
# ============================================================

def record_audio_with_sounddevice(seconds=4, sample_rate=16000):
    """Record microphone audio using sounddevice and return SpeechRecognition AudioData."""
    if sr is None or sd is None or np is None:
        print("[JARVIS] Voice packages missing.")
        return None
    try:
        recording = sd.rec(
            int(seconds * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocking=True,
        )
        return sr.AudioData(recording.tobytes(), sample_rate, 2)
    except Exception as e:
        print("[JARVIS] Microphone error:", e)
        return None


def recognize_audio(audio, recognizer):
    if audio is None:
        return None
    try:
        text = recognizer.recognize_google(audio, language="en-IN")
        text = text.strip()
        if text:
            print("[JARVIS] Heard:", text)
        return text or None
    except sr.UnknownValueError:
        print("[JARVIS] Could not understand audio.")
        return None
    except sr.RequestError as e:
        print("[JARVIS] Google speech service error:", e)
        return None
    except Exception as e:
        print("[JARVIS] Recognition error:", e)
        return None


def listen_once(seconds=6):
    if sr is None or sd is None or np is None:
        print("[JARVIS] Voice unavailable. Check SpeechRecognition, sounddevice and numpy.")
        return None
    ui_call(app.set_listening, True)
    try:
        r = sr.Recognizer()
        r.energy_threshold = 250
        r.dynamic_energy_threshold = True
        audio = record_audio_with_sounddevice(seconds=seconds)
        return recognize_audio(audio, r)
    finally:
        ui_call(app.set_listening, False)


def manual_voice():
    if state["listening"]:
        return
    def worker():
        text = listen_once(6)
        if text:
            ui_call(app.set_last_command_preview, text)
            process_command(text)
    threading.Thread(target=worker, daemon=True).start()


# ============================================================
# WAKE WORD
# ============================================================

def wake_word_worker():
    if sr is None or sd is None or np is None:
        print("[JARVIS] Wake word unavailable: missing voice packages.")
        return

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 250
    recognizer.dynamic_energy_threshold = True
    print("[JARVIS] Wake listener active.")
    print("[JARVIS] Say: Hey JARVIS")

    while state["running"]:
        try:
            audio = record_audio_with_sounddevice(seconds=1.5)
            heard = recognize_audio(audio, recognizer)
            if not heard:
                continue

            low = heard.lower().strip()
            wake = re.search(r"\b(?:hey\s+jarvis|ok(?:ay)?\s+jarvis|hey\s+jervis|jarvis)\b", low)
            if not wake:
                continue

            state["wake_word"] = True
            ui_call(app.set_wake_status, True)
            print("[JARVIS] Wake word detected.")
            # Do not synthesize an extra acknowledgement here.
            # Recording starts immediately to reduce command latency.

            remainder = heard[wake.end():].strip(" ,.!?")
            if remainder:
                process_command(remainder)
            else:
                command = listen_once(4)
                if command:
                    process_command(command)
                else:
                    speak("I didn't catch that. Please try again.")

            state["wake_word"] = False
            ui_call(app.set_wake_status, False)

        except Exception as e:
            print("[JARVIS] Wake listener error:", e)
            state["wake_word"] = False
            ui_call(app.set_wake_status, False)
            time.sleep(2)


# ============================================================
# DOUBLE CLAP
# ============================================================

def clap_worker():
    """Listen for two claps while the UI is hidden.

    The clap detector owns the microphone until activation. Once two claps
    are detected it stops its InputStream; the wake-word listener is then
    started by the UI. This avoids competing microphone streams.
    """
    if sd is None or np is None:
        print("[JARVIS] Double-clap listener unavailable.")
        return

    sample_rate = 16000
    block = 512
    last_clap = 0.0
    clap_count = 0
    noise_floor = 0.015
    consecutive_loud = 0

    try:
        devices = sd.query_devices()
        input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
        if not input_devices:
            print("[JARVIS] No microphone found for clap detection.")
            return

        def callback(indata, frames, time_info, status):
            nonlocal last_clap, clap_count, noise_floor, consecutive_loud

            samples = np.asarray(indata, dtype=np.float32).reshape(-1)
            if samples.size == 0:
                return

            rms = float(np.sqrt(np.mean(samples * samples)))
            peak = float(np.max(np.abs(samples)))

            # Continuously estimate quiet-room level.
            noise_floor = 0.98 * noise_floor + 0.02 * min(rms, 0.08)
            threshold = max(0.12, noise_floor * 4.5)

            if peak > threshold and peak > 0.12 and rms > max(0.012, noise_floor * 1.8):
                consecutive_loud += 1
            else:
                consecutive_loud = 0
                return

            # Require a short burst rather than a single noisy sample.
            if consecutive_loud < 2:
                return
            consecutive_loud = 0

            now = time.time()
            if now - last_clap < 0.15:
                return

            if now - last_clap <= 1.5:
                clap_count += 1
            else:
                clap_count = 1
            last_clap = now

            print(f"[JARVIS] Clap detected ({clap_count}/2)")

            if clap_count >= 2:
                clap_count = 0
                state["visible"] = True
                ui_call(app.show_window)

        print("[JARVIS] Double-clap listener active.")
        print("[JARVIS] Clap twice to open the UI.")

        with sd.InputStream(
            samplerate=sample_rate,
            blocksize=block,
            channels=1,
            dtype="float32",
            callback=callback,
        ):
            state["clap"] = True
            while state["running"] and not state.get("visible", False):
                time.sleep(0.1)

        print("[JARVIS] Clap listener stopped; microphone released.")

    except Exception as e:
        print("[JARVIS] Double-clap listener error:", e)


# ============================================================
# UI
# ============================================================

class JarvisApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("1450x900")
        self.minsize(1100, 700)
        self.configure(fg_color=BG)

        self.input_var = tk.StringVar()
        self.nav_buttons = {}
        self.content = None
        self.header_time = None
        self.status_text = None
        self.command_preview = None
        self.wake_status = None
        self.listening_status = None
        self.chat_box = None
        self.wake_started = False

        self.protocol("WM_DELETE_WINDOW", self.close_app)

        self.build_shell()
        self.set_page("HOME")

        self.after(100, self.process_ui_queue)
        self.after(1000, self.update_clock)

    # --------------------------------------------------------
    # SHELL
    # --------------------------------------------------------

    def build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.sidebar = ctk.CTkFrame(
            self,
            width=245,
            corner_radius=0,
            fg_color="#070B11",
            border_width=1,
            border_color=LINE,
        )
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_propagate(False)

        self.build_sidebar()

        self.topbar = ctk.CTkFrame(
            self,
            height=72,
            corner_radius=0,
            fg_color="#070C13",
            border_width=1,
            border_color=LINE,
        )
        self.topbar.grid(row=0, column=1, sticky="ew")
        self.topbar.grid_propagate(False)

        self.build_topbar()

        self.content = ctk.CTkFrame(
            self,
            fg_color=BG,
            corner_radius=0,
        )
        self.content.grid(row=1, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

    def build_sidebar(self):
        logo = ctk.CTkLabel(
            self.sidebar,
            text="JARVIS",
            font=(FONT, 28, "bold"),
            text_color=CYAN,
        )
        logo.pack(anchor="w", padx=25, pady=(28, 0))

        sub = ctk.CTkLabel(
            self.sidebar,
            text="COMMAND CENTER",
            font=(FONT, 10, "bold"),
            text_color=MUTED,
        )
        sub.pack(anchor="w", padx=27, pady=(0, 30))

        nav = [
            ("HOME", "⌂"),
            ("AI CORE", "◉"),
            ("AGENTS", "◇"),
            ("TASKS", "✓"),
            ("CALENDAR", "▣"),
            ("MEMORY", "◆"),
            ("CHAT", "▤"),
            ("KNOWLEDGE", "◎"),
            ("TOOLS", "⚙"),
            ("WORKFLOWS", "⇄"),
        ]

        for name, icon in nav:
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"  {icon}   {name}",
                anchor="w",
                height=43,
                corner_radius=8,
                fg_color="transparent",
                hover_color="#102333",
                text_color=TEXT,
                font=(FONT, 12, "bold"),
                command=lambda n=name: self.set_page(n),
            )
            btn.pack(fill="x", padx=14, pady=3)
            self.nav_buttons[name] = btn

        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        self.side_status = ctk.CTkLabel(
            self.sidebar,
            text="● SYSTEM ONLINE",
            text_color=GREEN,
            font=(FONT, 11, "bold"),
        )
        self.side_status.pack(anchor="w", padx=25, pady=(0, 7))

        ctk.CTkLabel(
            self.sidebar,
            text="LOCAL / PRIVATE",
            text_color=MUTED,
            font=(FONT, 9),
        ).pack(anchor="w", padx=27, pady=(0, 25))

    def build_topbar(self):
        left = ctk.CTkLabel(
            self.topbar,
            text="AI CORE OVERVIEW",
            text_color=TEXT,
            font=(FONT, 18, "bold"),
        )
        left.pack(side="left", padx=25)

        self.header_time = ctk.CTkLabel(
            self.topbar,
            text="--:--:--",
            text_color=CYAN,
            font=("Consolas", 16, "bold"),
        )
        self.header_time.pack(side="right", padx=25)

        self.wake_status = ctk.CTkLabel(
            self.topbar,
            text="● WAKE: LISTENING",
            text_color=MUTED,
            font=(FONT, 10, "bold"),
        )
        self.wake_status.pack(side="right", padx=25)

    # --------------------------------------------------------
    # NAVIGATION
    # --------------------------------------------------------

    def clear_content(self):
        for widget in self.content.winfo_children():
            widget.destroy()

    def set_page(self, page):
        self.state_page = page
        state["page"] = page

        for name, btn in self.nav_buttons.items():
            if name == page:
                btn.configure(
                    fg_color="#0B2638",
                    text_color=CYAN2,
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=TEXT,
                )

        self.clear_content()

        if page == "HOME":
            self.render_home()
        elif page == "AI CORE":
            self.render_ai_core()
        elif page == "AGENTS":
            self.render_agents()
        elif page == "TASKS":
            self.render_tasks()
        elif page == "CALENDAR":
            self.render_calendar()
        elif page == "MEMORY":
            self.render_memory()
        elif page == "CHAT":
            self.render_chat()
        elif page == "KNOWLEDGE":
            self.render_knowledge()
        elif page == "TOOLS":
            self.render_tools()
        elif page == "WORKFLOWS":
            self.render_workflows()

    # --------------------------------------------------------
    # COMMON
    # --------------------------------------------------------

    def page_title(self, title, subtitle=""):
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.pack(fill="x", padx=30, pady=(25, 10))

        ctk.CTkLabel(
            frame,
            text=title,
            text_color=TEXT,
            font=(FONT, 25, "bold"),
        ).pack(anchor="w")

        if subtitle:
            ctk.CTkLabel(
                frame,
                text=subtitle,
                text_color=MUTED,
                font=(FONT, 11),
            ).pack(anchor="w", pady=(3, 0))

    def card(self, parent, title="", width=None, height=None):
        f = ctk.CTkFrame(
            parent,
            fg_color=PANEL,
            border_width=1,
            border_color=LINE,
            corner_radius=10,
            width=width or 0,
            height=height or 0,
        )
        if width or height:
            f.pack_propagate(False)

        if title:
            ctk.CTkLabel(
                f,
                text=title.upper(),
                text_color=MUTED,
                font=(FONT, 10, "bold"),
            ).pack(anchor="w", padx=18, pady=(15, 5))

        return f

    def action_button(self, parent, text, command, primary=False):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=38,
            corner_radius=7,
            fg_color=CYAN if primary else "#10202D",
            hover_color="#35AFC7" if primary else "#183447",
            text_color=BG if primary else TEXT,
            font=(FONT, 11, "bold"),
        )

    # --------------------------------------------------------
    # HOME
    # --------------------------------------------------------

    def render_home(self):
        self.page_title(
            "AI CORE OVERVIEW",
            "JARVIS autonomous command interface",
        )

        outer = ctk.CTkFrame(self.content, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=30, pady=10)
        outer.grid_columnconfigure(0, weight=3)
        outer.grid_columnconfigure(1, weight=2)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        core = self.card(outer, "AI CORE")
        core.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10), pady=(0, 10))

        self.draw_core(core)

        intelligence = self.card(outer, "LIVE INTELLIGENCE")
        intelligence.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 10))

        self.intelligence_box = ctk.CTkTextbox(
            intelligence,
            fg_color="#060B11",
            border_width=0,
            text_color=TEXT,
            font=("Consolas", 11),
            wrap="word",
        )
        self.intelligence_box.pack(fill="both", expand=True, padx=12, pady=12)
        self.intelligence_box.insert(
            "end",
            "20:45:01  SYSTEM ONLINE\n"
            "20:45:04  LOCAL LLM READY\n"
            "20:45:08  MEMORY DATABASE READY\n"
            "20:45:12  VOICE INTERFACE STANDBY\n"
            "20:45:16  AWAITING COMMAND\n",
        )
        self.intelligence_box.configure(state="disabled")

        agents = self.card(outer, "ACTIVE AGENTS")
        agents.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(10, 0))

        agent_items = [
            ("CORE", "ONLINE", GREEN),
            ("VOICE", "STANDBY", CYAN),
            ("VISION", "READY", GREEN),
            ("MEMORY", "ONLINE", GREEN),
        ]

        for name, status, color in agent_items:
            row = ctk.CTkFrame(agents, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=6)

            ctk.CTkLabel(
                row, text=name, text_color=TEXT,
                font=(FONT, 11, "bold")
            ).pack(side="left")

            ctk.CTkLabel(
                row, text=f"● {status}", text_color=color,
                font=(FONT, 10, "bold")
            ).pack(side="right")

        self.build_bottom_bar()

    def draw_core(self, parent):
        canvas = tk.Canvas(
            parent,
            bg=PANEL,
            highlightthickness=0,
        )
        canvas.pack(fill="both", expand=True, padx=15, pady=10)

        def animate():
            if not canvas.winfo_exists():
                return

            w = max(canvas.winfo_width(), 400)
            h = max(canvas.winfo_height(), 400)
            cx, cy = w / 2, h / 2

            canvas.delete("core")

            t = time.time()

            # Rings
            for i, r in enumerate([75, 110, 145, 180]):
                pulse = 5 * math.sin(t * 2 + i)
                rr = r + pulse
                canvas.create_oval(
                    cx-rr, cy-rr, cx+rr, cy+rr,
                    outline="#16425A",
                    width=1,
                    tags="core",
                )

            # Rays
            for i in range(32):
                a = (i / 32) * math.pi * 2 + t * 0.15
                r1 = 82
                r2 = 175 + 12 * math.sin(t * 2 + i)
                x1 = cx + math.cos(a) * r1
                y1 = cy + math.sin(a) * r1
                x2 = cx + math.cos(a) * r2
                y2 = cy + math.sin(a) * r2
                canvas.create_line(
                    x1, y1, x2, y2,
                    fill="#0C607B",
                    width=1,
                    tags="core",
                )

            # Core
            pulse = 8 * math.sin(t * 3)
            rr = 57 + pulse

            canvas.create_oval(
                cx-rr, cy-rr, cx+rr, cy+rr,
                fill="#062030",
                outline=CYAN,
                width=2,
                tags="core",
            )

            canvas.create_oval(
                cx-35, cy-35, cx+35, cy+35,
                fill="#0A4157",
                outline=CYAN2,
                width=2,
                tags="core",
            )

            canvas.create_text(
                cx, cy-5,
                text="JARVIS",
                fill=TEXT,
                font=(FONT, 17, "bold"),
                tags="core",
            )
            canvas.create_text(
                cx, cy+17,
                text="AI CORE",
                fill=CYAN,
                font=(FONT, 9, "bold"),
                tags="core",
            )

            canvas.create_text(
                cx, cy + 220,
                text="NEURAL ENGINE  •  ONLINE",
                fill=GREEN,
                font=(FONT, 10, "bold"),
                tags="core",
            )

            canvas.after(45, animate)

        canvas.after(100, animate)

    def build_bottom_bar(self):
        bar = ctk.CTkFrame(
            self.content,
            fg_color="#080F17",
            border_width=1,
            border_color=LINE,
            corner_radius=10,
            height=68,
        )
        bar.pack(fill="x", padx=30, pady=(5, 22))
        bar.pack_propagate(False)

        self.input_var = tk.StringVar()

        entry = ctk.CTkEntry(
            bar,
            textvariable=self.input_var,
            placeholder_text="Talk to JARVIS or type a command...",
            height=42,
            fg_color="#060B11",
            border_color=LINE,
            text_color=TEXT,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(12, 8), pady=12)
        entry.bind("<Return>", lambda e: submit_text())

        self.action_button(
            bar, "SEND", submit_text, primary=True
        ).pack(side="right", padx=(0, 8), pady=12)

        self.action_button(
            bar, "🎤 VOICE", manual_voice
        ).pack(side="right", padx=(0, 8), pady=12)

    # --------------------------------------------------------
    # OTHER PAGES
    # --------------------------------------------------------

    def render_ai_core(self):
        self.page_title("AI CORE", "Local Llama 3 inference and system state")

        wrap = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=30, pady=10)

        info = [
            ("MODEL", OLLAMA_MODEL.upper()),
            ("ENGINE", "OLLAMA LOCAL API"),
            ("STATUS", "ONLINE" if state["ollama"] else "OFFLINE"),
            ("MODE", "LOCAL / PRIVATE"),
            ("MEMORY", "ACTIVE"),
            ("VOICE", "READY"),
        ]

        for label, value in info:
            c = self.card(wrap, label, height=95)
            c.pack(fill="x", pady=6)
            ctk.CTkLabel(
                c, text=value,
                text_color=GREEN if "ONLINE" in value or value == "ACTIVE" else TEXT,
                font=(FONT, 17, "bold")
            ).pack(anchor="w", padx=18, pady=5)

    def render_agents(self):
        self.page_title("ACTIVE AGENTS", "Subsystems available to JARVIS")

        for name, desc, status in [
            ("VOICE AGENT", "Speech recognition and JARVIS TTS.", "READY"),
            ("VISION AGENT", "Hidden camera / hand landmark processing.", "READY"),
            ("MEMORY AGENT", "Local persistent memory.json database.", "ONLINE"),
            ("BRAIN AGENT", "Llama 3 through local Ollama.", "ONLINE" if state["ollama"] else "OFFLINE"),
        ]:
            c = self.card(self.content, name)
            c.pack(fill="x", padx=30, pady=7)
            ctk.CTkLabel(c, text=desc, text_color=TEXT, font=(FONT, 12)).pack(
                anchor="w", padx=18, pady=5
            )
            ctk.CTkLabel(c, text=f"● {status}", text_color=GREEN if status != "OFFLINE" else RED,
                         font=(FONT, 10, "bold")).pack(anchor="w", padx=18, pady=(0, 15))

    def render_tasks(self):
        self.page_title("TASKS", "JARVIS task queue")

        add = ctk.CTkFrame(self.content, fg_color="transparent")
        add.pack(fill="x", padx=30, pady=10)

        var = tk.StringVar()
        entry = ctk.CTkEntry(add, textvariable=var, placeholder_text="New task...")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def add_task():
            task = var.get().strip()
            if task:
                state["tasks"].append({"text": task, "done": False})
                var.set("")
                self.set_page("TASKS")

        self.action_button(add, "ADD TASK", add_task, primary=True).pack(side="right")

        for index, task in enumerate(state["tasks"]):
            row = ctk.CTkFrame(self.content, fg_color=PANEL, border_width=1, border_color=LINE)
            row.pack(fill="x", padx=30, pady=4)

            ctk.CTkCheckBox(
                row,
                text=task["text"],
                text_color=TEXT,
                command=lambda i=index: self.toggle_task(i),
            ).pack(side="left", padx=15, pady=12)

    def toggle_task(self, index):
        if 0 <= index < len(state["tasks"]):
            state["tasks"][index]["done"] = not state["tasks"][index]["done"]

    def render_calendar(self):
        self.page_title("CALENDAR", "Local system date + Weekend Planner")

        now = datetime.datetime.now()
        c = self.card(self.content, "TODAY")
        c.pack(fill="x", padx=30, pady=10)

        ctk.CTkLabel(
            c,
            text=now.strftime("%A\n%d %B %Y"),
            text_color=CYAN,
            font=(FONT, 30, "bold"),
            justify="left",
        ).pack(anchor="w", padx=20, pady=20)

        ctk.CTkLabel(
            self.content,
            text="Use JARVIS to generate a balanced Saturday/Sunday schedule.",
            text_color=MUTED,
            font=(FONT, 12),
        ).pack(anchor="w", padx=30, pady=10)

        self.action_button(
            self.content,
            "GENERATE WEEKEND PLAN",
            lambda: threading.Thread(target=process_command, args=("plan my weekend", False), daemon=True).start(),
            primary=True,
        ).pack(anchor="w", padx=30, pady=10)

    def render_memory(self):
        self.page_title("MEMORY", "Persistent JARVIS memory")

        facts = memory.get("facts", [])
        if isinstance(facts, dict):
            facts = list(facts.values())
        elif not isinstance(facts, list):
            facts = [str(facts)] if facts else []

        c = self.card(self.content, "SAVED FACTS")
        c.pack(fill="both", expand=True, padx=30, pady=10)

        box = ctk.CTkTextbox(c, fg_color="#060B11", text_color=TEXT)
        box.pack(fill="both", expand=True, padx=12, pady=12)

        if facts:
            for fact in facts:
                box.insert("end", f"• {fact}\n")
        else:
            box.insert("end", "No saved facts yet.\n")

        box.configure(state="disabled")

    def render_chat(self):
        self.page_title("CHAT", "Direct conversation with JARVIS")

        box = ctk.CTkTextbox(
            self.content,
            fg_color="#060B11",
            text_color=TEXT,
            font=("Consolas", 11),
            wrap="word",
        )
        box.pack(fill="both", expand=True, padx=30, pady=10)

        for role, msg in state["messages"]:
            box.insert("end", f"\n{role}\n{msg}\n")
        box.configure(state="disabled")

        bottom = ctk.CTkFrame(self.content, fg_color="transparent")
        bottom.pack(fill="x", padx=30, pady=(0, 20))

        var = tk.StringVar()
        ent = ctk.CTkEntry(
            bottom,
            textvariable=var,
            placeholder_text="Message JARVIS...",
            height=44,
        )
        ent.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def send():
            text = var.get().strip()
            if text:
                var.set("")
                threading.Thread(target=process_command, args=(text,), daemon=True).start()
                self.after(100, lambda: self.set_page("CHAT"))

        ent.bind("<Return>", lambda e: send())
        self.action_button(bottom, "SEND", send, primary=True).pack(side="right")

    def render_knowledge(self):
        self.page_title("KNOWLEDGE", "Ask JARVIS anything")

        c = self.card(self.content, "QUERY")
        c.pack(fill="x", padx=30, pady=10)

        var = tk.StringVar()
        entry = ctk.CTkEntry(c, textvariable=var, placeholder_text="Enter a question...")
        entry.pack(fill="x", padx=18, pady=15)

        def ask():
            q = var.get().strip()
            if q:
                threading.Thread(target=process_command, args=(q,), daemon=True).start()

        self.action_button(c, "ASK JARVIS", ask, primary=True).pack(anchor="e", padx=18, pady=(0, 15))

    def render_tools(self):
        self.page_title("TOOLS", "Desktop actions + Code Mode")

        tools = [
            ("OPEN CHROME", lambda: process_command("open chrome", False)),
            ("OPEN YOUTUBE", lambda: process_command("open youtube", False)),
            ("OPEN CALCULATOR", lambda: process_command("open calculator", False)),
            ("OPEN NOTEPAD", lambda: process_command("open notepad", False)),
            ("SCREENSHOT", lambda: process_command("take a screenshot", False)),
            ("CODE MODE", lambda: self.set_page("CHAT")),
            ("WEEKEND PLANNER", lambda: process_command("plan my weekend", False)),
        ]

        grid = ctk.CTkFrame(self.content, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=30, pady=10)

        for i, (name, command) in enumerate(tools):
            b = self.action_button(grid, name, command)
            b.grid(row=i // 2, column=i % 2, padx=7, pady=7, sticky="ew")
            grid.grid_columnconfigure(i % 2, weight=1)

    def render_workflows(self):
        self.page_title("WORKFLOWS", "Multi-step JARVIS actions")

        workflows = [
            ("START WORK SESSION", "Open your primary engineering workspace."),
            ("RESEARCH MODE", "Prepare browser and knowledge workflow."),
            ("PRESENTATION MODE", "Prepare a clean presentation workspace."),
        ]

        for name, desc in workflows:
            c = self.card(self.content, name)
            c.pack(fill="x", padx=30, pady=7)

            ctk.CTkLabel(c, text=desc, text_color=TEXT).pack(
                anchor="w", padx=18, pady=5
            )

            self.action_button(
                c, "RUN WORKFLOW",
                lambda n=name: self.run_workflow(n)
            ).pack(anchor="e", padx=18, pady=(0, 15))

    def run_workflow(self, name):
        if "WORK" in name:
            try:
                subprocess.Popen("start explorer", shell=True)
            except Exception:
                pass
            speak("Workspace workflow started.")
        elif "RESEARCH" in name:
            safe_open("https://www.google.com")
            speak("Research mode started.")
        else:
            speak("Presentation mode started.")

    # --------------------------------------------------------
    # UI UPDATES
    # --------------------------------------------------------

    def process_ui_queue(self):
        try:
            while True:
                fn, args, kwargs = ui_queue.get_nowait()
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    print("[JARVIS] UI callback error:", e)
        except queue.Empty:
            pass

        if self.winfo_exists():
            self.after(50, self.process_ui_queue)

    def refresh(self):
        # Do not rebuild continuously. Only update status widgets that exist.
        self.update_status_widgets()

    def update_status_widgets(self):
        if self.status_text is not None and self.status_text.winfo_exists():
            self.status_text.configure(
                text=state["last_response"][:100]
            )

    def set_listening(self, value):
        state["listening"] = value
        if self.listening_status is not None and self.listening_status.winfo_exists():
            self.listening_status.configure(
                text="● LISTENING" if value else "● STANDBY",
                text_color=CYAN if value else MUTED,
            )

    def set_wake_status(self, active):
        if self.wake_status is not None and self.wake_status.winfo_exists():
            self.wake_status.configure(
                text="● WAKE: ACTIVE" if active else "● WAKE: LISTENING",
                text_color=CYAN if active else MUTED,
            )

    def set_last_command_preview(self, text):
        if self.command_preview is not None and self.command_preview.winfo_exists():
            self.command_preview.configure(text=text)

    def update_clock(self):
        # Single source of truth: this is the exact value displayed in the top-left UI clock.
        current_display_time = datetime.datetime.now().strftime("%H:%M:%S")
        state["ui_clock"] = current_display_time
        if self.header_time is not None and self.header_time.winfo_exists():
            self.header_time.configure(text=current_display_time)
        if self.winfo_exists():
            self.after(1000, self.update_clock)

    # --------------------------------------------------------
    # HIDDEN STARTUP / WINDOW
    # --------------------------------------------------------

    def hide_window(self):
        self.withdraw()
        state["visible"] = False

    def show_window(self):
        if not self.winfo_exists():
            return

        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()
        state["visible"] = True

        # Stop startup music and play the short welcome sound.
        stop_startup_music()
        play_welcome_sound()

        # Start voice recognition only after the clap listener releases the
        # microphone. This prevents two sounddevice streams fighting over
        # the same input device.
        if not getattr(self, "wake_started", False):
            self.wake_started = True
            threading.Thread(target=wake_word_worker, daemon=True).start()

        speak("JARVIS command center online.")
        print("[JARVIS] Double clap detected. UI opened.")

    def close_app(self):
        state["running"] = False
        stop_startup_music()
        stop_voice_server()
        try:
            self.destroy()
        except Exception:
            pass


# ============================================================
# STARTUP
# ============================================================

def main():
    global app

    print("=" * 60)
    print("JARVIS V28 // ALL-IN-ONE AUTONOMOUS AGENT")
    print("=" * 60)

    state["tasks"]=persistent_tasks()
    app = JarvisApp()

    # Automatically open FlightRadar24 in Chrome at startup.
    # No voice command or user input is required.
    try:
        subprocess.Popen("start chrome https://www.flightradar24.com", shell=True)
        print("[JARVIS] FlightRadar24 opened automatically in Chrome.")
    except Exception as e:
        print("[JARVIS] Could not open FlightRadar24 automatically:", e)

    # Open the Command Centre immediately when JARVIS is launched.
    app.deiconify()
    app.state("normal")
    app.lift()
    app.focus_force()
    state["visible"] = True

    # Start the startup audio sequence in the correct order:
    # Welcome.mp3 finishes first, then Startup Music.mp3 begins.
    threading.Thread(
        target=play_startup_sequence,
        daemon=True,
    ).start()

    threading.Thread(
        target=start_ollama_if_needed,
        daemon=True,
    ).start()

    def background_rag_setup():
        for _ in range(30):
            if check_ollama(): break
            time.sleep(1)
        if check_ollama(): rag_index_knowledge()
        else: state["rag_status"] = "Ollama unavailable"

    threading.Thread(target=background_rag_setup, daemon=True).start()

    threading.Thread(
        target=tts_worker,
        daemon=True,
    ).start()

    # Warm up the cloned XTTS server in the background so the first spoken
    # response does not have to start model loading on demand.
    threading.Thread(
        target=initialize_cloned_voice,
        daemon=True,
    ).start()

    # Start voice recognition directly. No clap listener is needed.
    app.wake_started = True
    threading.Thread(
        target=wake_word_worker,
        daemon=True,
    ).start()

    print("[JARVIS] Microphone backend: sounddevice (PyAudio disabled).")
    print(f"[JARVIS] Startup music: {STARTUP_MUSIC}")
    print(f"[JARVIS] Startup welcome sound: {WELCOME_SOUND}")
    print(f"[JARVIS] Cloned voice reference: {VOICE_REFERENCE}")
    print("[JARVIS] Command Centre opened automatically.")
    print("[JARVIS] Startup audio: Welcome.mp3 -> Startup Music.mp3 (sequential, no overlap).")
    print("[JARVIS] Desktop Automation Mode: READY")
    print("[JARVIS] Multi-Agent Layer: READY")
    print("[JARVIS] File + Code + Engineering + Vision + Research + Workflow agents: READY")
    print(f"[JARVIS] RAG knowledge folder: {KNOWLEDGE_DIR}")
    print(f"[JARVIS] RAG embedding model: {RAG_EMBED_MODEL}")
    print("[JARVIS] After startup, say: Hey JARVIS")
    print("[JARVIS] Spoken responses are sent to the speaker, not echoed as replies in PowerShell.")
    print("[JARVIS] Press Ctrl+C in PowerShell to stop.")

    app.mainloop()


if __name__ == "__main__":
    main()
