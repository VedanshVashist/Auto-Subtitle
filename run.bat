@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call setup.bat
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -c "import PySide6, faster_whisper" >nul 2>nul
if errorlevel 1 (
  echo Required packages are missing. Running the one-time setup...
  call setup.bat
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" main.py %*
