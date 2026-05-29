# 🥔 小土豆 — A股智能桌面宠物

**A股智能桌面宠物 (AI-Powered A-Stock Desktop Pet)**

[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

> 作者: 自由的风

小土豆是一个 AI 驱动的 A股桌面宠物，住在你的桌面上，帮你盯盘、分析、甚至自主操盘。她有 Live2D 外表、DeepSeek 大脑、严格的风控纪律，和一颗保守但专业的心。

## ✨ 功能特性

- 🐱 **Live2D 桌面角色** — 可爱的土豆宠物，待在桌面上陪你盯盘
- 💬 **AI 对话** — 基于 DeepSeek 大模型，口语化交流，自然理解股票术语
- 🤖 **自主操盘** — AI 按交易时间自动分析→选股→风控→执行，全程可视化
- 📊 **专业复盘** — 每日盘后深度复盘：胜率、盈亏比、逐笔对错分析
- 🔄 **4层 LLM 故障转移** — DeepSeek → SiliconFlow → Liner → OpenAI，额度用完自动切换
- 🖥️ **Bytebot 远程操控** — 通过 Bytebot 桌面代理远程操控电脑（开软件、浏览网页等）
- 🛡️ **严格风控系统** — 止损必设、风控参数用户确认、熔断机制、仓位管理
- 🔐 **密钥保险箱** — AES-256-GCM 加密存储 API Key、交易账号等敏感信息
- 🎙️ **语音交互** — SiliconFlow TTS/STT，支持语音对话
- 📱 **多渠道通知** — Telegram / 飞书 / 钉钉推送交易提醒

## 🏗️ 架构

```
┌─────────────────────────────────────────────────┐
│              Electron 桌面壳                      │
│  ┌──────────────┐  ┌──────────────────────────┐  │
│  │   Live2D     │  │    Vite + Vue 前端        │  │
│  │   桌面宠物    │  │    对话 / 行情 / 风控面板  │  │
│  └──────┬───────┘  └──────────┬───────────────┘  │
│         │    WebSocket (ws)   │                   │
│  ┌──────┴────────────────────┴───────────────┐   │
│  │         FastAPI 后端 (Python)              │   │
│  │  ┌─────────┐ ┌──────────┐ ┌────────────┐  │   │
│  │  │ AI 服务  │ │ 交易引擎 │ │  风控系统   │  │   │
│  │  │4层故障转移│ │ 调度器   │ │  熔断/止损  │  │   │
│  │  └─────────┘ └──────────┘ └────────────┘  │   │
│  │  ┌─────────┐ ┌──────────┐ ┌────────────┐  │   │
│  │  │密钥保险箱│ │Bytebot   │ │  记忆系统   │  │   │
│  │  │AES-256   │ │桌面代理   │ │  30天持久化 │  │   │
│  │  └─────────┘ └──────────┘ └────────────┘  │   │
│  └───────────────────────────────────────────┘   │
│         │ SQLite (本地) / CockroachDB (云端)      │
└─────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+ (前端构建)
- DeepSeek API Key (至少一个 LLM API Key)

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/lopaycn-boop/a-stock-desktop-pet.git
cd a-stock-desktop-pet

# 2. 一键安装 (推荐)
bash setup.sh

# 或手动安装:
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 4. 启动后端
python -m desktop_pet.backend.main

# 5. 启动前端 (另一个终端)
cd desktop_pet/frontend
npm install
npm run dev
```

## ⚙️ 配置

### API Keys（必须）

| 变量 | 说明 | 获取地址 |
|------|------|----------|
| `DEEPSEEK_API_KEY` | DeepSeek 大模型 (推荐) | [platform.deepseek.com](https://platform.deepseek.com) |
| `SILICON_API_KEY` | SiliconFlow TTS/STT | [cloud.siliconflow.cn](https://cloud.siliconflow.cn) |
| `OPENAI_API_KEY` | OpenAI (故障转移) | [platform.openai.com](https://platform.openai.com) |

### 风控配置（可选）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POTATO_TRADING_MODE` | `dry_run` | `live` = 实盘, `dry_run` = 模拟 |
| `POTATO_MAX_SINGLE_CNY` | 300 | 单笔最大金额 (CNY) |
| `POTATO_MAX_DAILY_CNY` | 1500 | 日最大交易额 (CNY) |
| `PET_WS_TOKEN` | (空) | WebSocket 认证令牌（生产环境必须设置） |
| `VAULT_SALT` | (默认) | 加密盐值（生产环境请更换） |

更多配置参见 `.env.example`。

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 桌面壳 | Electron |
| 前端 | Vite + Vue + Live2D |
| 后端 | Python + FastAPI + WebSocket |
| 大模型 | DeepSeek / SiliconFlow / Liner / OpenAI (4层故障转移) |
| 数据库 | SQLite (本地) / CockroachDB (云端) |
| 加密 | AES-256-GCM (cryptography) |
| 通知 | Telegram / 飞书 / 钉钉 |
| 桌面操控 | Bytebot / Playwright / pyautogui |

## 📸 截图

> 截图占位 — 欢迎贡献截图！

## 📄 License

[Apache-2.0](LICENSE) — Copyright 2025 自由的风

## 🤝 贡献

欢迎贡献！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。
