# 🥔 小土豆 — A股智能桌面宠物

**A股智能桌面宠物 (AI-Powered A-Stock Desktop Pet)**

[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

> 作者: 自由的风

小土豆是一个 AI 驱动的 A股桌面宠物，住在你的桌面上，帮你盯盘、分析、甚至自主操盘。她有 Live2D 外表、DeepSeek 大脑、严格的风控纪律，和一颗保守但专业的心。

## ✨ 功能特性

- 🐱 **Live2D 桌面角色** — 6款模型可选（含表情映射），待在桌面上陪你盯盘
- 💬 **AI 对话** — 基于 DeepSeek 大模型，口语化交流，自然理解股票术语
- 🤖 **自主操盘** — 交易日7阶段全自动：盘前→开盘→风控→执行→午间→尾盘→盘后复盘
- 📊 **专业复盘** — 每日盘后深度复盘：胜率、盈亏比、最大回撤、逐笔对错、AI反思
- 📰 **实时资讯** — Google News RSS 抓取A股资讯，AI关联分析个股
- 🔄 **4层 LLM 故障转移** — DeepSeek → SiliconFlow → Liner → OpenAI，额度用完自动切换
- 🖥️ **Bytebot 远程操控** — 内置Bytebot Agent(9991) + Bytebot Desktop(9990)，语音指令操控电脑
- 🛡️ **严格风控系统** — 止损必设、用户定金额、AI定止损止盈、熔断机制、仓位管理
- 🔐 **密钥保险箱** — AES-256-GCM 加密存储，前端7层正则遮蔽，绝不泄漏密钥
- 🎙️ **语音交互** — SiliconFlow TTS/STT，支持语音对话
- 📱 **多渠道通知** — Telegram / 飞书 / 钉钉推送交易提醒
- 🧠 **30天记忆** — 持久化记忆系统，记住用户偏好和对话
- 🔄 **6Agent博弈分析** — 多维A股分析引擎（技术面+基本面+消息面三层逻辑）

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────┐
│              Electron 桌面壳 (一键安装)              │
│  ┌──────────────┐  ┌──────────────────────────────┐ │
│  │   Live2D     │  │    Vite + React 前端          │ │
│  │   桌面宠物    │  │    对话 / 行情 / 风控 / 模型  │ │
│  └──────┬───────┘  └──────────┬───────────────────┘ │
│         │    WebSocket (ws)   │                      │
│  ┌──────┴────────────────────┴───────────────────┐  │
│  │         FastAPI 后端 (Python :8000)            │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────┐ │  │
│  │  │ AI 服务   │ │ 交易引擎 │ │   风控系统      │ │  │
│  │  │ 4层故障转移│ │ 7阶段调度 │ │ 12条规则       │ │  │
│  │  └──────────┘ └──────────┘ └────────────────┘ │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────┐ │  │
│  │  │密钥保险箱 │ │Bytebot   │ │   专业复盘      │ │  │
│  │  │ AES-256   │ │Agent内置 │ │  胜率/盈亏比    │ │  │
│  │  └──────────┘ └──────────┘ └────────────────┘ │  │
│  └────────────────────────────────────────────────┘  │
│         │ SQLite (本地) / CockroachDB (云端)         │
└─────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 方式一：一键安装（推荐）

1. 下载 `小土豆 AI操盘桌宠 Setup 1.0.0.exe`
2. 双击安装，自动启动
3. 启动后粘贴 DeepSeek API Key → 完成

### 方式二：开发者模式

```bash
# 1. 克隆仓库
git clone https://github.com/lopaycn-boop/a-stock-desktop-pet.git
cd a-stock-desktop-pet

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装前端依赖
cd desktop_pet/frontend && npm install && cd ../..

# 4. 一键启动脚本 (推荐)
# Windows:
desktop_pet\frontend\Start.vbs
# 或手动启动:
python -m potato                    # 后端 (:8000)
cd desktop_pet/frontend && npm run dev  # 前端 (:5173)

# 5. Electron 开发模式:
cd desktop_pet/electron && npm install && npm start
```

### 方式三：Docker + Electron

```bash
# 1. 启动 Bytebot Desktop (可选，用于电脑操控)
docker run -d -p 9990:9990 bytebot/desktop

# 2. 启动主服务
pip install -r requirements.txt
python -m potato
```

## ⚙️ 配置

### API Keys（至少配置一个）

| 变量 | 说明 | 获取地址 |
|------|------|----------|
| `DEEPSEEK_API_KEY` | DeepSeek 大模型 (**推荐**) | [platform.deepseek.com](https://platform.deepseek.com) |
| `SILICON_API_KEY` | SiliconFlow TTS/STT | [cloud.siliconflow.cn](https://cloud.siliconflow.cn) |
| `LINER_API_KEY` | Liner AI (故障转移) | [platform.liner.com](https://platform.liner.com) |
| `OPENAI_API_KEY` | OpenAI (故障转移) | [platform.openai.com](https://platform.openai.com) |

首次启动后，直接在聊天窗口粘贴 API Key 即可，小土豆会自动加密存储并刷新配置。

### 自主操盘规则

| 规则 | 说明 |
|------|------|
| 唯一人控项 | 资金金额（用户说多少就是多少） |
| 止损 | AI 根据市场波动自动设定（默认 5%） |
| 止盈 | AI 自动设定（默认 10%） |
| 最多持仓 | AI 决定（建议不超过 3 只） |
| 风控未确认 | 只禁交易，不禁分析和复盘 |
| 交易日自动启动 | 不需要手动按钮，检测到工作日自动开跑 |

### 安全配置

| 变量 | 说明 |
|------|------|
| `PET_WS_TOKEN` | WebSocket 远程访问令牌（生产环境必须设置） |
| `VAULT_ENCRYPTION_KEY` | 密钥保险箱主密钥（生产环境必须更换） |
| `VAULT_SALT` | 加密盐值 |

更多配置参见 `.env.example`。

## 📊 操盘流程

```
交易日自动运行（不需手动）：

09:00 盘前扫描 — AI 抓取 A股资讯 + 筛选标的 + 深度分析
09:25 开盘分析 — AI 选股（三层逻辑）+ 自动执行交易信号
09:30-11:30 盘中监控 — 实时盯盘止损/止盈
11:30 午间复盘 — 持仓 P&L 检查 + 自动止损止盈
14:30 尾盘评估 — 自动执行触发信号 + 持仓决策
15:10 盘后复盘 — 胜率/盈亏比/AI反思/改进建议
```

## 🛡️ 风控系统

| 编号 | 规则 | 说明 |
|------|------|------|
| 0 | 风控确认 | 用户未确认限额 → 全部交易拦截 |
| 1 | 熔断机制 | 连续 3 次亏损 → 暂停交易 |
| 2 | 单笔限额 | 不超过用户设定金额 |
| 3 | 日限额 | 不超过用户设定日限额 |
| 4 | 最多持仓 | 用户设定（建议 3 只） |
| 5 | 最低置信度 | confidence < 0.65 不推荐买入 |
| 6 | 黑名单 | ST/N 股票禁止交易 |
| 7 | 尾盘限制 | 14:45 后禁止新开仓 |
| 8 | 日亏损限制 | 日亏损超过限额自动停止 |
| 9 | 交易时间 | 仅限 A股交易时间 |
| 10 | 价格验证 | 下单前比对实时行情（偏差 > 3% 拦截） |

## 🎭 Live2D 模型

| 模型 | 状态 | 说明 |
|------|------|------|
| 春 (Haru) | ✅ 内置 | 默认模型，8 种表情 |
| 桃濑日和 (Hiyori) | ✅ 内置 | 物理模拟 + 眨眼 |
| 虹色Mao | 📥 需下载 | 融合变形特效 |
| 马克君 (Mark) | 📥 需下载 | 新手友好 |
| 伊普西隆 (Epsilon) | 📥 需下载 | 表情特效 |
| 雫 (Shizuku) | 📥 需下载 | 手势细腻 |

未安装模型会在选择器中标记"未安装"，不影响使用。从 [Live2D 官网](https://www.live2d.com/en/learn/sample/) 下载免费模型后放入 `desktop_pet/frontend/public/models/` 即可。

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 桌面壳 | Electron 28 |
| 前端 | Vite + React + Live2D |
| 后端 | Python + FastAPI + WebSocket |
| 大模型 | DeepSeek / SiliconFlow / Liner / OpenAI (4层故障转移) |
| 数据库 | SQLite (本地) / CockroachDB (云端) |
| 加密 | AES-256-GCM (cryptography) |
| 通知 | Telegram / 飞书 / 钉钉 |
| 桌面操控 | Bytebot Agent(内置) / Bytebot Desktop(Docker) / Playwright / pyautogui |
| 交易引擎 | 7 阶段调度器 + 12 条风控规则 + 专业复盘系统 |

## 📂 项目结构

```
a-stock-desktop-pet/
├── desktop_pet/
│   ├── backend/           # FastAPI 后端
│   │   ├── main.py        # WS 端点 + AI 大脑 + 7阶段调度
│   │   ├── bytebot_agent.py  # 内置 Bytebot Agent (:9991)
│   │   ├── bytebot_client.py # Bytebot REST 客户端
│   │   └── ...
│   ├── electron/          # Electron 桌面壳
│   │   ├── main.js        # 托盘 + 自动启动 + 管理后端进程
│   │   └── package.json   # electron-builder 打包配置
│   └── frontend/          # Vite + React 前端
│       └── src/
│           ├── pages/MainPage.jsx     # 主界面 + WS + 密钥遮蔽
│           └── components/Live2D/      # Live2D 模型渲染 + 模型选择器
├── potato/                # 核心引擎
│   ├── trading/
│   │   ├── scheduler.py  # 7 阶段调度器
│   │   ├── analyzer.py    # AI 选股引擎 + 技术指标
│   │   ├── executor.py    # 交易执行器
│   │   ├── journal.py     # 专业复盘系统
│   │   └── risk.py        # 12 条风控规则
│   ├── intel.py           # 资讯抓取 (Google News RSS)
│   ├── llm.py             # 4 层 LLM 故障转移
│   ├── vault.py            # AES-256-GCM 密钥保险箱
│   └── ...
├── schema/                # 数据库 Schema
├── .env.example           # 环境变量模板
├── LICENSE                 # Apache-2.0
└── README.md
```

## 📄 License

[Apache-2.0](LICENSE) — Copyright 2025 自由的风