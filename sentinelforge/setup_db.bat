@echo off
TITLE Sentinel Forge - Database Setup (Manual)
COLOR 0B

echo ===================================================
echo      SENTINEL FORGE DATABASE SETUP
echo ===================================================
echo.

:: Check for Virtual Environment
if exist "..\env\Scripts\activate.bat" (
    set "VENV_PATH=..\env\Scripts\activate.bat"
) else (
    if exist "env\Scripts\activate.bat" (
        set "VENV_PATH=env\Scripts\activate.bat"
    ) else (
        echo [ERROR] Virtual environment not found.
        pause
        exit /b
    )
)

:: Activate Virtual Environment
call "%VENV_PATH%"

echo [INFO] Checking for PostgreSQL connection...
python -c "import socket; s = socket.socket(); s.connect(('localhost', 5432)); s.close(); print('PostgreSQL is reachable')" 2>NUL
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Could not connect to PostgreSQL on localhost:5432.
    echo.
    echo Please ensure:
    echo 1. PostgreSQL is installed and running.
    echo 2. You have created the 'sentinelforge' database.
    echo 3. You have installed the 'pgvector' extension.
    echo.
    echo See docs\README_WINDOWS_DB.md for instructions.
    pause
    exit /b
)

echo [INFO] Running Database Migrations...
alembic upgrade head

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Migration failed. Check your .env credentials.
) else (
    echo.
    echo [SUCCESS] Database setup complete!
)

pause