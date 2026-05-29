@echo off
chcp 65001 >nul 2>&1
title 小土豆回滚工具

echo ========================================
echo   小土豆 AI操盘桌宠 - 回滚到上一版本
echo ========================================
echo.

:: Check git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git not found. Rollback requires git.
    pause
    exit /b 1
)

:: Show current state
echo [INFO] Current git state:
git log --oneline -5
echo.

:: Check for uncommitted changes
git diff --quiet HEAD 2>nul
if %errorlevel% neq 0 (
    echo [WARN] You have uncommitted changes. Stashing...
    git stash push -m "pre-rollback-stash-%date:/=-%-%time::=-%" 2>nul
)

:: Show previous commit
echo [INFO] Previous commit:
git log --oneline -1 HEAD~1
echo.

set /p CONFIRM="Rollback to this commit? (y/N): "
if /i not "%CONFIRM%"=="y" (
    echo [INFO] Rollback cancelled.
    git stash pop >nul 2>&1
    exit /b 0
)

:: Stop services
echo [1/3] Stopping services...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im node.exe >nul 2>&1

:: Rollback
echo [2/3] Rolling back to previous commit...
git revert --no-edit HEAD
if %errorlevel% neq 0 (
    echo [ERROR] Rollback failed. Check git conflicts.
    pause
    exit /b 1
)

:: Restore stashed changes if any
git stash pop >nul 2>&1

:: Verify
echo [3/3] Verifying rollback...
git log --oneline -3
echo.
echo [OK] Rollback complete. Restart services with start.bat
echo.
pause