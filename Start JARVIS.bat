@echo off
setlocal
title JARVIS
cd /d "%~dp0"

if not exist "jarvis.py" (
    echo ERROR: jarvis.py was not found in this folder.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo JARVIS is not set up yet. Running setup...
    call "%~dp0setup_windows.bat"
    if errorlevel 1 exit /b 1
)

echo Starting JARVIS...
".venv\Scripts\python.exe" "%~dp0jarvis.py"

echo.
echo JARVIS has stopped.
pause
