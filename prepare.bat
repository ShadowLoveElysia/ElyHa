@echo off
setlocal

cd /d "%~dp0"

echo [ElyHa] Preparing environment...

where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [ElyHa] uv not found. Installing uv from official source...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo [ElyHa] Official install failed. Trying pip fallback...
        where pip >nul 2>nul
        if %errorlevel%==0 (
            pip install uv
        ) else (
            echo [ElyHa] Error: All install methods failed.
            echo [ElyHa] Visit: https://docs.astral.sh/uv/getting-started/installation/
            pause
            exit /b 1
        )
    )
)

echo [ElyHa] uv found. Installing dependencies...
if "%UV_CACHE_DIR%"=="" set "UV_CACHE_DIR=.uv-cache"
if "%UV_PROJECT_ENVIRONMENT%"=="" set "UV_PROJECT_ENVIRONMENT=.venv-win"
uv sync

if errorlevel 1 (
    echo [ElyHa] Failed to install dependencies.
    pause
    exit /b 1
)

echo [ElyHa] Setup complete!
echo [ElyHa] Run 'LaunchWebUI.bat' to start Web GUI
echo [ElyHa] Run 'LaunchTUI.bat' to start TUI

pause
endlocal
