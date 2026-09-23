@echo off
setlocal EnableExtensions EnableDelayedExpansion
title JARVIS ALL-IN-ONE Windows Installer
cd /d "%~dp0"

echo ============================================================
echo              JARVIS ALL-IN-ONE INSTALLER
echo ============================================================
echo.

echo [1/9] Checking Python 3.11...
set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3.11 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3.11"
)
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo Downloading Python 3.11.9...
    set "PYI=%TEMP%\python-3.11.9-amd64.exe"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%PYI%'"
    if not exist "%PYI%" goto FAIL
    "%PYI%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
    timeout /t 5 /nobreak >nul
    py -3.11 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3.11"
)
if not defined PYTHON_CMD goto FAIL

%PYTHON_CMD% --version

echo.
echo [2/9] Creating JARVIS environment...
if not exist ".venv\Scripts\python.exe" %PYTHON_CMD% -m venv ".venv"
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r "requirements_all_in_one.txt"
if errorlevel 1 goto FAIL

echo.
echo [3/9] Creating folders...
for %%D in (generated_code weekend_plans voice_cache models knowledge research_reports vision_captures workflow_logs) do if not exist "%%D" mkdir "%%D"

echo.
echo [4/9] Checking Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
    echo Downloading Ollama...
    set "OI=%TEMP%\OllamaSetup.exe"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest 'https://ollama.com/download/OllamaSetup.exe' -OutFile '%OI%'"
    if exist "%OI%" "%OI%"
    timeout /t 8 /nobreak >nul
)
where ollama >nul 2>&1
if errorlevel 1 if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
where ollama >nul 2>&1
if errorlevel 1 (
    echo WARNING: Ollama not detected. Install Ollama and rerun this setup.
    goto VOICE
)

echo.
echo [5/9] Starting Ollama and installing models...
start "" /min ollama serve >nul 2>&1
timeout /t 4 /nobreak >nul
ollama list 2>nul | findstr /I "llama3" >nul || ollama pull llama3
ollama list 2>nul | findstr /I "nomic-embed-text" >nul || ollama pull nomic-embed-text

echo.
echo [6/9] Setting up cloned JARVIS voice...
if exist "Welcome.wav" (
    if not exist ".voice_env\Scripts\python.exe" py -3.11 -m venv ".voice_env"
    if exist ".voice_env\Scripts\python.exe" (
        ".voice_env\Scripts\python.exe" -m pip install --upgrade pip
        ".voice_env\Scripts\python.exe" -m pip install TTS==0.22.0 torch==2.5.1 torchaudio==2.5.1 transformers==4.41.2 soundfile scipy numpy requests
    )
) else echo Welcome.wav not found - cloned voice will use fallback.

:VOICE
echo.
echo [7/9] Checking JARVIS...
if not exist "jarvis.py" (
    echo ERROR: jarvis.py not found.
    goto FAIL
)
".venv\Scripts\python.exe" -m py_compile "jarvis.py"
if errorlevel 1 goto FAIL

echo.
echo [8/9] Creating Start JARVIS.bat...
(
echo @echo off
echo cd /d "%%~dp0"
echo if not exist ".venv\Scripts\python.exe" ^(
echo   echo JARVIS is not installed. Run setup_windows_all_in_one.bat first.
echo   pause
echo   exit /b 1
echo ^)
echo ".venv\Scripts\python.exe" "%%~dp0jarvis.py"
echo pause
) > "Start JARVIS.bat"

echo.
echo [9/9] Complete.
echo.
echo RAG: put files in the knowledge folder.
echo Research: say "research ..."
echo Code: say "create code ..." or "run file ..."
echo Engineering: say "calculate power from torque and rpm ..."
echo Vision: say "camera snapshot"
echo Computer control: say "type ..." or "press enter"
echo Tasks: say "add task ..." or "show tasks"
echo Autonomous workflows: say "do ..."
echo.
echo Double-click Start JARVIS.bat to launch.
echo.
pause
exit /b 0

:FAIL
echo.
echo SETUP FAILED. Check the message above.
pause
exit /b 1
