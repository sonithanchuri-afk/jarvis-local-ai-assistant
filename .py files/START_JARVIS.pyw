import subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
JARVIS = BASE / "jarvis.py"
VENV_PY = BASE / ".venv" / "Scripts" / "python.exe"

if not JARVIS.exists():
    raise SystemExit("jarvis.py was not found in this folder.")

python = str(VENV_PY) if VENV_PY.exists() else sys.executable
subprocess.Popen([python, str(JARVIS)], cwd=str(BASE))
