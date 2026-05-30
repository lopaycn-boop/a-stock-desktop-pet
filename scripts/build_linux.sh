#!/bin/bash
# Build Linux tar.gz for 小土豆 AI操盘桌宠
# Run this on a Linux machine with Node.js and Python 3.10+

set -e
cd "$(dirname "$0")"
PROJECT_ROOT="$(cd ../.. && pwd)"

echo "=== Installing dependencies ==="
cd "$PROJECT_ROOT/desktop_pet/frontend"
npm install
cd "$PROJECT_ROOT/desktop_pet/electron"
npm install

echo "=== Building frontend ==="
cd "$PROJECT_ROOT/desktop_pet/frontend"
npm run build

echo "=== Obfuscating JS ==="
cd "$PROJECT_ROOT"
node obfuscate.js

echo "=== Building Linux app ==="
cd "$PROJECT_ROOT/desktop_pet/electron"
npx electron-builder --linux tar.gz --x64

echo "=== Done! ==="
ls -lh dist/*.tar.gz dist/*.AppImage 2>/dev/null || echo "Check dist/ for output files"