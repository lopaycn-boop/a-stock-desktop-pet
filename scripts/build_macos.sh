#!/bin/bash
# Build macOS DMG for 小土豆 AI操盘桌宠
# Run this on a macOS machine with Node.js and Python 3.10+

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

echo "=== Building macOS app ==="
cd "$PROJECT_ROOT/desktop_pet/electron"
npx electron-builder --mac zip --x64

echo "=== Done! ==="
ls -lh dist/*.zip dist/*.dmg 2>/dev/null || echo "Check dist/ for output files"