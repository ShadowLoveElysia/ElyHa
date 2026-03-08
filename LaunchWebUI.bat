@echo off
setlocal

cd /d "%~dp0"

if not exist data mkdir data

set "DB_PATH=%ELYHA_DB_PATH%"
if "%DB_PATH%"=="" set "DB_PATH=.\data\dev.db"

set "CONFIG_DIR=%ELYHA_CORE_CONFIG_DIR%"
if "%CONFIG_DIR%"=="" set "CONFIG_DIR=.\data\core_configs"
set "ACTIVE_PROFILE=core"
if exist "%CONFIG_DIR%\active_profile.txt" (
    set /p ACTIVE_PROFILE=<"%CONFIG_DIR%\active_profile.txt"
)

set "HOST=%ELYHA_HOST%"
if "%HOST%"=="" (
    if exist "%CONFIG_DIR%\%ACTIVE_PROFILE%.json" (
        for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$cfg=Get-Content -Raw -Path '%CONFIG_DIR%\%ACTIVE_PROFILE%.json' | ConvertFrom-Json; if($cfg.web_host){$cfg.web_host}"`) do set "HOST=%%i"
    )
)
if "%HOST%"=="" set "HOST=127.0.0.1"

set "PORT=%ELYHA_PORT%"
if "%PORT%"=="" (
    if exist "%CONFIG_DIR%\%ACTIVE_PROFILE%.json" (
        for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$cfg=Get-Content -Raw -Path '%CONFIG_DIR%\%ACTIVE_PROFILE%.json' | ConvertFrom-Json; if($cfg.web_port){$cfg.web_port}"`) do set "PORT=%%i"
    )
)
if "%PORT%"=="" set "PORT=8765"

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

echo [ElyHa] Launching Web GUI with db: %DB_PATH%
echo [ElyHa] Open: http://%HOST%:%PORT%/web
echo [ElyHa] Active config profile: %ACTIVE_PROFILE%

where uv >nul 2>nul
if %errorlevel%==0 (
    if "%UV_CACHE_DIR%"=="" set "UV_CACHE_DIR=.uv-cache"
    echo [ElyHa] uv environment: %UV_PROJECT_ENVIRONMENT%
    set "ELYHA_DB_PATH=%DB_PATH%"
    uv run uvicorn elyha_api.app:app --host %HOST% --port %PORT%
) else (
    echo [ElyHa] uv not found, fallback to python -m uvicorn.
    set "ELYHA_DB_PATH=%DB_PATH%"
    python -m uvicorn elyha_api.app:app --host %HOST% --port %PORT%
)

if errorlevel 1 (
    echo.
    echo [ElyHa] Failed to launch Web GUI. Check Python/uv and dependencies.
)

pause
endlocal
