import shutil
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV = BASE / ".venv"
VENV_PY = VENV / "Scripts" / "python.exe"
REQ = BASE / "requirements_all_in_one.txt"

def pause():
    input("\nPress Enter to close...")

def main():
    print("=" * 60)
    print("             JARVIS DOUBLE-CLICK SETUP")
    print("=" * 60)

    py = shutil.which("py") or shutil.which("python")
    if not py:
        print("\nPython is not installed.")
        print("Install Python 3.11 (64-bit), then run this file again.")
        pause()
        return

    if not VENV_PY.exists():
        subprocess.run([py, "-m", "venv", str(VENV)], check=True)

    if not REQ.exists():
        print("requirements_all_in_one.txt is missing.")
        pause()
        return

    subprocess.run([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "-r", str(REQ)], check=True)

    for folder in ("generated_code", "weekend_plans", "voice_cache", "models",
                   "knowledge", "research_reports", "vision_captures", "workflow_logs"):
        (BASE / folder).mkdir(exist_ok=True)

    ollama = shutil.which("ollama")
    if ollama:
        print("\nOllama found. Checking models...")
        subprocess.Popen([ollama, "serve"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        subprocess.run([ollama, "pull", "llama3"], check=False)
        subprocess.run([ollama, "pull", "nomic-embed-text"], check=False)
    else:
        print("\nOllama was not found. Install Ollama before using the AI features.")

    print("\nSETUP COMPLETE")
    print("Double-click START_JARVIS.pyw to launch JARVIS.")
    pause()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nSETUP ERROR:", e)
        pause()
