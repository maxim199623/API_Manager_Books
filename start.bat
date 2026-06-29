@echo off
setlocal

cd /d "%~dp0"

where poetry >nul 2>nul
if errorlevel 1 (
    echo Poetry is not installed or not available in PATH.
    exit /b 1
)

if exist ".env.prod.local" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env.prod.local") do (
        if not "%%A"=="" if not "%%B"=="" set "%%A=%%B"
    )
)

if not "%APP_ENV%"=="prod" (
    echo APP_ENV must be set to prod.
    exit /b 1
)

if "%TLS_CERT_FILE%"=="" (
    echo TLS_CERT_FILE is required for production start.
    exit /b 1
)

if "%TLS_KEY_FILE%"=="" (
    echo TLS_KEY_FILE is required for production start.
    exit /b 1
)

call poetry install --only main
if errorlevel 1 exit /b %errorlevel%

call poetry run api-manager-books
exit /b %errorlevel%
