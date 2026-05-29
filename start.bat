@echo off
chcp 65001 >nul 2>&1
title 小土豆 AI操盘桌宠

echo ========================================
echo   小土豆 AI操盘桌宠 - 一键启动
echo ========================================
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.11+
    pause
    exit /b 1
)

:: Check if backend is already running
curl -s http://127.0.0.1:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Backend already running on :8000
    goto :start_frontend
)

:: Start backend
echo [1/2] Starting backend...
start /b python -m potato
timeout /t 3 /nobreak >nul

:: Wait for backend (max 60 retries = 60 seconds)
echo Waiting for backend...
set /a _retries=0
:wait_backend
curl -s http://127.0.0.1:8000/health >nul 2>&1
if %errorlevel% equ 0 goto :backend_ready
set /a _retries+=1
if %_retries% geq 60 (
    echo [ERROR] Backend failed to start within 60 seconds.
    echo          Check logs above for Python errors.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto :wait_backend
:backend_ready
echo [OK] Backend is ready on :8000

:start_frontend
:: Check if frontend is already running
curl -s http://127.0.0.1:5173 >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Frontend already running on :5173
    goto :done
)

:: Check node_modules
if not exist "desktop_pet\frontend\node_modules" (
    echo [2/2] Installing frontend dependencies...
    cd desktop_pet\frontend
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed. Check Node.js and network.
        cd ..\..
        pause
        exit /b 1
    )
    cd ..\..
)

:: Start frontend
echo [2/2] Starting frontend...
cd desktop_pet\frontend
start /b npm run dev
cd ..\..

:done
echo.
echo ========================================
echo   小土豆已启动！
echo   前端: http://localhost:5173
echo   后端: http://localhost:8000
echo   Bytebot Agent: http://localhost:9991
echo ========================================
echo.
echo Press Ctrl+C to stop...
pause >nul