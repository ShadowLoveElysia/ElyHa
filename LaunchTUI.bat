@echo off
setlocal

cd /d "%~dp0"

if not exist data mkdir data

set "DB_PATH=%ELYHA_DB_PATH%"
if "%DB_PATH%"=="" set "DB_PATH=.\data\dev.db"
set "UV_ENV_FROM_USER=1"
if "%UV_PROJECT_ENVIRONMENT%"=="" (
    set "UV_ENV_FROM_USER=0"
    set "UV_PROJECT_ENVIRONMENT=.venv-win"
)

if "%UV_ENV_FROM_USER%"=="0" (
    if exist "%UV_PROJECT_ENVIRONMENT%\lib64" (
        set "UV_PROJECT_ENVIRONMENT=.venv-win-native"
    )
)

set "PYTHON_LAUNCHER=python"
if exist "%UV_PROJECT_ENVIRONMENT%\Scripts\python.exe" (
    set "PYTHON_LAUNCHER=%UV_PROJECT_ENVIRONMENT%\Scripts\python.exe"
)

echo [ElyHa] Web GUI available via LaunchGUI.bat ^(or http://127.0.0.1:8765/web after start^).
echo [ElyHa] Launching TUI with db: %DB_PATH%

where uv >nul 2>nul
if %errorlevel%==0 (
    if "%UV_CACHE_DIR%"=="" set "UV_CACHE_DIR=.uv-cache"
    echo [ElyHa] uv environment: %UV_PROJECT_ENVIRONMENT%
    uv run python -m elyha_tui.main --db "%DB_PATH%"
    if errorlevel 1 (
        echo [ElyHa] uv launch failed, fallback to "%PYTHON_LAUNCHER%".
        "%PYTHON_LAUNCHER%" -m elyha_tui.main --db "%DB_PATH%"
    )
) else (
    echo [ElyHa] uv not found, fallback to "%PYTHON_LAUNCHER%".
    "%PYTHON_LAUNCHER%" -m elyha_tui.main --db "%DB_PATH%"
)

if errorlevel 1 (
    echo.
    echo [ElyHa] Failed to launch TUI. Check Python/uv and dependencies.
)

pause
endlocal
