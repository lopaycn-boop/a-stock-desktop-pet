@echo off
REM Build Windows NSIS installer for 小土豆 AI操盘桌宠
REM Run this on a Windows machine with Node.js and Python 3.10+

cd /d "%~dp0"
set PROJECT_ROOT=..\..

echo === Installing dependencies ===
cd /d "%PROJECT_ROOT%\desktop_pet\frontend"
call npm install
cd /d "%PROJECT_ROOT%\desktop_pet\electron"
call npm install

echo === Building frontend ===
cd /d "%PROJECT_ROOT%\desktop_pet\frontend"
call npm run build

echo === Obfuscating JS ===
cd /d "%PROJECT_ROOT%"
node obfuscate.js

echo === Building Windows installer ===
cd /d "%PROJECT_ROOT%\desktop_pet\electron"
call npx electron-builder --win --x64

echo === Done! ===
dir dist\*.exe
pause