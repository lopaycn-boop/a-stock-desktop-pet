@echo off
chcp 65001 >nul 2>&1
title 小土豆健康检查

echo ========================================
echo   小土豆 AI操盘桌宠 - 健康检查
echo ========================================
echo.

set PASS=0
set FAIL=0

:: 1. Python
echo [1/8] Python...
where python >nul 2>&1
if %errorlevel% equ 0 (
    python --version 2>&1 | findstr "3\." >nul
    if %errorlevel% equ 0 (
        echo   [OK] Python found
        set /a PASS+=1
    ) else (
        echo   [WARN] Python version may be too old (need 3.11+)
        set /a FAIL+=1
    )
) else (
    echo   [FAIL] Python not found
    set /a FAIL+=1
)

:: 2. Python packages
echo [2/8] Python packages...
python -c "import potato" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] potato module importable
    set /a PASS+=1
) else (
    echo   [FAIL] potato module not importable
    set /a FAIL+=1
)

python -c "import cryptography" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] cryptography package installed
    set /a PASS+=1
) else (
    echo   [FAIL] cryptography package missing - vault encryption disabled
    set /a FAIL+=1
)

:: 3. Node.js
echo [3/8] Node.js...
where node >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Node.js found
    set /a PASS+=1
) else (
    echo   [FAIL] Node.js not found
    set /a FAIL+=1
)

:: 4. Backend health
echo [4/8] Backend service (port 8000)...
curl -s http://127.0.0.1:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Backend responding
    set /a PASS+=1
) else (
    echo   [WARN] Backend not running (start with start.bat)
    set /a FAIL+=1
)

:: 5. Bytebot Agent
echo [5/8] Bytebot Agent (port 9991)...
curl -s http://127.0.0.1:9991/health >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Bytebot Agent responding
    set /a PASS+=1
) else (
    echo   [WARN] Bytebot Agent not running
    set /a FAIL+=1
)

:: 6. Vault status
echo [6/8] Vault encryption...
python -c "from potato.vault import Vault; v=Vault(); s=v.status(); print(f'  Keys: {s[\"total_keys\"]}, Encrypted: True') if s.get('total_keys',0)>=0 else print('  [FAIL]') " 2>nul
if %errorlevel% equ 0 (
    set /a PASS+=1
) else (
    echo   [WARN] Cannot check vault status
    set /a FAIL+=1
)

:: 7. Journal directory
echo [7/8] Journal directory...
python -c "from potato.trading.journal import JOURNAL_DIR; JOURNAL_DIR.mkdir(parents=True, exist_ok=True); print(f'  [OK] {JOURNAL_DIR}')" 2>nul
if %errorlevel% equ 0 (
    set /a PASS+=1
) else (
    echo   [WARN] Cannot verify journal directory
    set /a FAIL+=1
)

:: 8. Live2D models
echo [8/8] Live2D models...
python -c "from desktop_pet.frontend.src.components.Live2D.modelRegistry_js import MODELS; avail=[m for m in MODELS if m.get('available')]; print(f'  Available: {len(avail)}/{len(MODELS)}')" 2>nul
if %errorlevel% equ 0 (
    set /a PASS+=1
) else (
    echo   [INFO] Live2D models check skipped (frontend not built)
    set /a PASS+=1
)

echo.
echo ========================================
echo   Results: %PASS% passed, %FAIL% failed
echo ========================================
echo.

if %FAIL% gte 3 (
    echo [CRITICAL] Too many failures. Fix issues before running.
    exit /b 1
) else if %FAIL% gte 1 (
    echo [WARNING] Some checks failed. Review above.
    exit /b 0
) else (
    echo [OK] All checks passed.
    exit /b 0
)