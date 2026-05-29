#!/usr/bin/env bash
set -euo pipefail

echo "🥔 小土豆 — A股智能桌面宠物 安装脚本"
echo "========================================"

# Check Python 3.11+
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请安装 Python 3.11+"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]); then
    echo "❌ Python 版本过低 ($PY_VERSION)，需要 3.11+"
    exit 1
fi
echo "✅ Python $PY_VERSION"

# Create venv
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install requirements
if [ -f "requirements.txt" ]; then
    echo "📦 安装 Python 依赖..."
    pip install -r requirements.txt -q
else
    echo "⚠️  未找到 requirements.txt，跳过依赖安装"
fi

# Create data directory
mkdir -p data
echo "✅ data/ 目录已创建"

# Copy .env.example if .env doesn't exist
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "✅ .env 已从 .env.example 复制"
else
    echo "ℹ️  .env 已存在（或无 .env.example），跳过"
fi

echo ""
echo "========================================="
echo "🎉 安装完成！下一步："
echo ""
echo "  1. 编辑 .env 填入你的 API Key"
echo "     DEEPSEEK_API_KEY=sk-xxx  (必填)"
echo ""
echo "  2. 启动后端:"
echo "     source venv/bin/activate"
echo "     python -m desktop_pet.backend.main"
echo ""
echo "  3. 启动前端 (另一个终端):"
echo "     cd desktop_pet/frontend && npm install && npm run dev"
echo ""
echo "🥔 祝你用土豆赚大钱！"
