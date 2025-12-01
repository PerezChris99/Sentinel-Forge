@echo off
echo [INFO] Launching PostgreSQL 16 Installer...
winget install --id PostgreSQL.PostgreSQL.16 -e --accept-source-agreements --accept-package-agreements

echo.
echo [INFO] Launching Memurai (Redis) Installer...
winget install --id Memurai.MemuraiDeveloper -e --accept-source-agreements --accept-package-agreements

echo.
echo [INFO] Installers have been launched. Please complete the setup wizards.
pause