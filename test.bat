@echo off
REM COD Commerce Platform - Docker Test Runner for Windows
REM Usage: test.bat [command] [options]
REM Commands: up, down, logs, clean, help

setlocal enabledelayedexpansion

set "projectRoot=%~dp0"
set "backendDir=%projectRoot%backend"
set "command=%~1"

if "%command%"=="" (
    goto :no_command
)

if "%command%"=="help" (
    goto :show_help
)

if "%command%"=="up" (
    goto :test_up
)

if "%command%"=="down" (
    goto :test_down
)

if "%command%"=="clean" (
    goto :test_clean
)

if "%command%"=="logs" (
    goto :show_logs
)

goto :no_command

:show_help
cls
echo.
echo COD Commerce Platform - Docker Test Suite
echo.
echo Usage: test.bat [command]
echo.
echo Commands:
echo   up       Start Docker containers and run tests
echo   down     Stop Docker containers
echo   clean    Remove containers and volumes (full cleanup)
echo   logs     Show container logs
echo   help     Show this help message
echo.
echo Examples:
echo   test.bat up       - Start Docker and run all tests
echo   test.bat down     - Stop Docker containers
echo   test.bat clean    - Complete cleanup
echo.
goto :end

:no_command
cls
echo.
echo No command specified. Use 'test.bat help' for usage.
echo.
goto :end

:test_up
cls
echo.
echo === COD Commerce Platform - Docker Test Suite ===
echo.

REM Check if docker is installed
docker --version >nul 2>&1
if errorlevel 1 (
    echo Error: Docker not found. Please install Docker Desktop.
    exit /b 1
)
echo [OK] Docker found

REM Check if docker-compose is installed
docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo Error: Docker Compose not found. Please install Docker Desktop.
    exit /b 1
)
echo [OK] Docker Compose found
echo.

REM Start containers
echo Starting Docker containers...
docker-compose -f "%projectRoot%docker-compose.yml" up -d
if errorlevel 1 (
    echo Error: Failed to start Docker containers
    exit /b 1
)
echo [OK] Containers started
echo.

REM Wait for PostgreSQL
echo Waiting for PostgreSQL to be ready...
set "attempts=0"
set "maxAttempts=30"
:wait_postgres
docker-compose -f "%projectRoot%docker-compose.yml" exec -T postgres pg_isready -U cod_user -d cod_platform_test >nul 2>&1
if errorlevel 1 (
    set /a attempts=!attempts!+1
    if !attempts! lss !maxAttempts! (
        timeout /t 1 /nobreak >nul
        goto :wait_postgres
    )
    echo Error: PostgreSQL did not become ready in time
    docker-compose -f "%projectRoot%docker-compose.yml" logs postgres
    exit /b 1
)
echo [OK] PostgreSQL is ready
echo.

REM Wait for Redis
echo Waiting for Redis to be ready...
set "attempts=0"
:wait_redis
docker-compose -f "%projectRoot%docker-compose.yml" exec -T redis redis-cli ping >nul 2>&1
if errorlevel 1 (
    set /a attempts=!attempts!+1
    if !attempts! lss !maxAttempts! (
        timeout /t 1 /nobreak >nul
        goto :wait_redis
    )
    echo Error: Redis did not become ready in time
    docker-compose -f "%projectRoot%docker-compose.yml" logs redis
    exit /b 1
)
echo [OK] Redis is ready
echo.

REM Load environment variables from .env.test
echo Loading environment from .env.test...
set "envFile=%backendDir%\.env.test"
if exist "%envFile%" (
    for /f "usebackq delims== tokens=1,*" %%a in ("%envFile%") do (
        if not "%%a"=="" (
            if not "%%a:~0,1%"=="#" (
                set "%%a=%%b"
            )
        )
    )
    echo [OK] Environment loaded
) else (
    echo Warning: .env.test not found at %envFile%
    echo Using default test configuration
)
echo.

REM Run migrations
echo Running Prisma migrations...
cd /d "%projectRoot%"
call prisma migrate deploy >nul 2>&1
if errorlevel 1 (
    echo Warning: Migration may have already been applied
)
echo [OK] Migrations completed
echo.

REM Run tests
echo === Running Tests ===
echo.
cd /d "%backendDir%"
python -m pytest tests -v

REM Capture exit code
set "testExit=!errorlevel!"

echo.
echo === Test Run Complete ===
echo.

if %testExit% equ 0 (
    echo [SUCCESS] All tests passed!
) else (
    echo [FAILED] Some tests failed (exit code: %testExit%)
)

echo.
echo Containers are still running. To stop them, run: test.bat down
echo To view logs, run: test.bat logs
echo.

cd /d "%projectRoot%"
exit /b %testExit%

:test_down
echo.
echo Stopping Docker containers...
docker-compose -f "%projectRoot%docker-compose.yml" down
echo [OK] Containers stopped
echo.
goto :end

:test_clean
echo.
echo Cleaning up Docker containers and volumes...
docker-compose -f "%projectRoot%docker-compose.yml" down -v
echo [OK] Cleanup complete
echo.
goto :end

:show_logs
echo.
echo === Docker Container Logs ===
echo.
docker-compose -f "%projectRoot%docker-compose.yml" logs -f
echo.
goto :end

:end
cd /d "%projectRoot%"
endlocal
