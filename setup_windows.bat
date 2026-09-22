@echo off
setlocal EnableExtensions EnableDelayedExpansion
title JARVIS Automatic Windows Installer
color 0A
cd /d "%~dp0"
echo.
echo ============================================================
echo              JARVIS AUTOMATIC WINDOWS INSTALLER
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
    if not errorlevel 1 (
        python --version >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)
if not defined PYTHON_CMD (
    echo Python 3.11 was not found. Downloading Python 3.11.9...
    set "PYTHON_INSTALLER=%TEMP%\python-3.11.9-amd64.exe"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%PYTHON_INSTALLER%'"
    if not exist "%PYTHON_INSTALLER%" (echo ERROR: Python download failed.& pause& exit /b 1)
    "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
    timeout /t 5 /nobreak >nul
    py -3.11 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3.11"
)
if not defined PYTHON_CMD (echo ERROR: Python could not be detected.& pause& exit /b 1)
%PYTHON_CMD% --version

echo.
echo [2/9] Creating JARVIS Python environment...
if not exist ".venv\Scripts\python.exe" %PYTHON_CMD% -m venv ".venv"
if not exist ".venv\Scripts\python.exe" (echo ERROR: Could not create .venv.& pause& exit /b 1)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if not exist "requirements.txt" (echo ERROR: requirements.txt is missing.& pause& exit /b 1)
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 (echo ERROR: Python requirements installation failed.& pause& exit /b 1)

echo.
echo [3/9] Creating JARVIS folders...
if not exist "generated_code" mkdir "generated_code"
if not exist "weekend_plans" mkdir "weekend_plans"
if not exist "voice_cache" mkdir "voice_cache"
if not exist "models" mkdir "models"
if not exist "knowledge" mkdir "knowledge"

echo.
echo [4/9] Checking Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
    echo Ollama not found. Downloading installer...
    set "OLLAMA_INSTALLER=%TEMP%\OllamaSetup.exe"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '%OLLAMA_INSTALLER%'"
    if exist "%OLLAMA_INSTALLER%" "%OLLAMA_INSTALLER%"
    timeout /t 8 /nobreak >nul
)
where ollama >nul 2>&1
if errorlevel 1 if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
where ollama >nul 2>&1
if errorlevel 1 (echo WARNING: Ollama was not detected. Install it and rerun setup.& goto VOICE)
start "" /min ollama serve >nul 2>&1
timeout /t 4 /nobreak >nul

echo.
echo [5/9] Checking AI models...
ollama list 2>nul | findstr /I "llama3" >nul
if errorlevel 1 (echo Downloading llama3...& ollama pull llama3) else echo llama3 already installed.
ollama list 2>nul | findstr /I "nomic-embed-text" >nul
if errorlevel 1 (echo Downloading nomic-embed-text for RAG...& ollama pull nomic-embed-text) else echo nomic-embed-text already installed.

:VOICE
echo.
echo [6/9] Setting up cloned JARVIS voice...
if not exist "Welcome.wav" goto CHECK
if not exist ".voice_env\Scripts\python.exe" py -3.11 -m venv ".voice_env"
if not exist ".voice_env\Scripts\python.exe" goto CHECK
".voice_env\Scripts\python.exe" -m pip install --upgrade pip
".voice_env\Scripts\python.exe" -m pip install TTS==0.22.0 torch==2.5.1 torchaudio==2.5.1 transformers==4.41.2 soundfile scipy numpy requests

:CHECK
echo.
echo [7/9] Checking JARVIS files...
if exist "jarvis.py" echo [OK] jarvis.py
if exist "requirements.txt" echo [OK] requirements.txt
if exist "knowledge" echo [OK] knowledge folder
if exist "Welcome.mp3" echo [OK] Welcome.mp3
if exist "Welcome.wav" echo [OK] Welcome.wav
if exist "Startup Music.mp3" echo [OK] Startup Music.mp3
".venv\Scripts\python.exe" -m py_compile "jarvis.py"
if errorlevel 1 echo WARNING: jarvis.py syntax check failed.
if not errorlevel 1 echo [OK] jarvis.py syntax check passed.

echo.
echo [8/9] Creating Start JARVIS.bat...
(
echo @echo off
echo cd /d "%%~dp0"
echo if not exist ".venv\Scripts\python.exe" ^(echo JARVIS is not installed. Run setup_windows_auto_rag.bat first.^& pause^& exit /b 1^)
echo ".venv\Scripts\python.exe" "%%~dp0jarvis.py"
echo pause
) > "Start JARVIS.bat"

echo.
echo [9/9] RAG setup complete.
echo Put PDFs, DOCX, TXT, Markdown, code, JSON or CSV files into:
echo %~dp0knowledge
echo.
echo JARVIS will index them automatically. You can also say:
echo   index knowledge
echo   open knowledge folder
echo   show knowledge

echo ============================================================
echo                 JARVIS SETUP COMPLETE
echo ============================================================
echo.
pause
exit /b 0
