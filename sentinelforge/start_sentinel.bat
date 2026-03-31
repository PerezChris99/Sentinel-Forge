@echo off
TITLE Sentinel Forge - Security System
COLOR 0A

:: Ensure we are running from the script directory
cd /d "%~dp0"

echo ===================================================
echo      SENTINEL FORGE SECURITY SYSTEM
echo ===================================================
echo.

:: Check for Virtual Environment
:: Assuming the standard structure where env is a sibling to the repo folder
if exist "..\env\Scripts\activate.bat" (
    set "VENV_PATH=..\env\Scripts\activate.bat"
) else (
    :: Fallback check if env is inside the repo
    if exist "env\Scripts\activate.bat" (
        set "VENV_PATH=env\Scripts\activate.bat"
    ) else (
        echo [ERROR] Virtual environment not found.
        echo Expected at '..\env' or '.\env'
        pause
        exit /b
    )
)

:: Activate Virtual Environment
echo [INFO] Activating Python Environment...
call "%VENV_PATH%"

:: Start the Server
echo [INFO] Starting Sentinel Forge Server...
echo [INFO] Dashboard available at: http://localhost:8000/dashboard
echo [INFO] API Docs available at:  http://localhost:8000/docs
echo.
echo Press Ctrl+C to stop the server.
echo.

uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

pause