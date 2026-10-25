@echo off
setlocal
cd /d "%~dp0"
echo WordPop Studio - creating the isolated environment...
if not exist ".venv\Scripts\python.exe" (
  py -3.14 -m venv .venv
  if errorlevel 1 (
    echo Could not create a Python 3.14 environment. Install Python 3.14 and try again.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo.
echo Setup complete. Run run.bat to start WordPop Studio.
pause
exit /b 0
:error
echo.
echo Dependency installation did not finish. Check your internet connection and README troubleshooting notes.
pause
exit /b 1
