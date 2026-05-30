# 🥔 小土豆 — A股智能桌面宠物

**A股智能桌面宠物 (AI-Powered A-Stock Desktop Pet)**

[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

> 作者: 自由的风

小土豆是一个 AI 驱动的 A股桌面宠物，住在你的桌面上，帮你盯盘、分析、甚至自主操盘。她有 Live2D 外表、DeepSeek 大脑、严格的风控纪律，和一颗保守但专业的心。

## ✨ 功能特性

- 🐱 **Live2D 桌面角色** — 6款模型全部可用（8种表情/情绪映射），待在桌面上陪你盯盘
- 💬 **AI 对话** — 基于 DeepSeek 大模型，口语化交流，自然理解股票术语
- 🤖 **自主操盘** — 交易日7阶段全自动：盘前→开盘→风控→执行→午间→尾盘→盘后复盘
- 📊 **专业复盘** — 每日盘后深度复盘：胜率、盈亏比、最大回撤、逐笔对错、AI反思
- 📰 **实时资讯** — Google News RSS 抓取A股资讯，AI关联分析个股
- 🔄 **5层 LLM 故障转移** — DeepSeek → SiliconFlow → Liner → Base44 Agent → OpenAI，额度用完自动切换
- 📊 **东方财富 AI SaaS** — 8大AI接口（金融问答/业绩点评/行业研究/跟踪报告/可比公司/热点发现/数据搜索/资讯搜索）+ 金融情感分析 + 异动监控 + 龙虎榜 + 筹码分布 + 实时行情
- 🎯 **问财智能选股** — 自然语言选股/宏观分析/资讯搜索，API优先+免费网页回退
- 🔬 **PlanExecute 多步分析** — Plan→Execute→Synthesize 三阶段深度分析引擎，质量更高
- 🕹️ **Demo Mode** — 无API Key也能体验，6类智能模拟响应（行情/分析/热点/情绪/研报/闲聊）
- 🖥️ **Bytebot 远程操控** — 内置Bytebot Agent(9991) + Bytebot Desktop(9990)，语音指令操控电脑
- 🛡️ **严格风控系统** — 止损必设、用户定金额、AI定止损止盈、熔断机制、仓位管理（15条规则+AI确认门控）
- 🔐 **密钥保险箱** — Fernet(AES-128-CBC+HMAC-SHA256) 加密存储，前端7层正则遮蔽，绝不泄漏密钥
- 🔒 **AI确认门控** — 买入置信度<65%自动拦截，实盘切换需风控确认，低置信度只禁交易不禁分析
- 💳 **统一计费** — 5家LLM服务商统一计费面板，用户只见总价格，2x加价模型对用户完全透明
- 🔄 **一键续费** — 余额充足自动扣款，余额不足显示USDT-TRC20二维码+收款地址，扫码即付
- 🔒 **源码保护** — AI不泄露源代码/架构/定价模型，输入拦截+输出脱敏+规则三重防护
- 🌐 **浏览器域名白名单** — 仅允许16个金融域名，非白名单请求直接阻止
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
│  │         FastAPI 后端 (Python :8000+)           │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────┐ │  │
│  │  │ AI 服务   │ │ 交易引擎 │ │   风控系统      │ │  │
│  │  │ 5层故障转移│ │ 7阶段调度 │ │ 15条规则       │ │  │
│  │  └──────────┘ └──────────┘ └────────────────┘ │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────┐ │  │
│  │  │密钥保险箱 │ │Bytebot   │ │   专业复盘      │ │  │
│  │  │ AES-128   │ │Agent内置 │ │  胜率/盈亏比    │ │  │
│  │  └──────────┘ └──────────┘ └────────────────┘ │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────┐ │  │
│  │  │ 统一计费  │ │ 券商适配 │ │ 源码+密钥保护   │ │  │
│  │  │ QR续费    │ │dry/live │ │ 3层防护         │ │  │
│  │  └──────────┘ └──────────┘ └────────────────┘ │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────┐ │  │
│  │  │ 东方财富  │ │ 问财选股 │ │  PlanExecute    │ │  │
│  │  │ 8AI+情感  │ │ 自然语言 │ │  多步深度分析    │ │  │
│  │  └──────────┘ └──────────┘ └────────────────┘ │  │
│  └────────────────────────────────────────────────┘  │
│         │ SQLite (本地) / CockroachDB (云端)         │
└─────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 方式一：一键安装（推荐）

1. 下载 `小土豆 AI操盘桌宠 Setup 1.0.2.exe`
2. 双击安装，自动启动
3. 启动后粘贴 DeepSeek API Key → 完成
4. (可选) 粘贴东方财富/问财API Key 解锁更多数据源

> 无Key时自动进入Demo模式，仍可体验6类智能模拟响应

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
python -m potato                    # 后端 (自动选择可用端口)
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
| `DEEPSEEK_API_KEY` | DeepSeek 大模型 (**推荐，必须**) | [platform.deepseek.com](https://platform.deepseek.com) |
| `EM_API_KEY` | 东方财富 AI SaaS (可选) | [东方财富开放平台](https://open.eastmoney.com) |
| `IWENCAI_API_KEY` | 问财智能选股 API (可选) | [问财](https://www.iwencai.com) |
| `SILICON_API_KEY` | SiliconFlow (故障转移) | [cloud.siliconflow.cn](https://cloud.siliconflow.cn) |
| `LINER_API_KEY` | Liner AI (故障转移) | [liner.ai](https://liner.ai) |
| `OPENAI_API_KEY` | OpenAI (故障转移) | [platform.openai.com](https://platform.openai.com) |
| `BASE44_API_KEY` | Base44 Agent (故障转移) | [app.base44.com](https://app.base44.com) |

> 东方财富和问财API为可选项。无Key时东方财富基础行情数据仍可用，问财会自动回退到免费网页版。**无任何Key时进入Demo模式**，提供智能模拟响应。

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

### 计费配置

| 变量 | 说明 |
|------|------|
| `PLATFORM_WALLET_ADDRESS` | 平台数字币收款地址（默认已内置 TLyD5v9eTDp3mMzpYT3kprF6WdsUc3W99d） |

> 收款地址在数据库中持久化存储，重装也不会丢失。用户只需说"续费"或点🔄续费按钮即可查看。

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
| 5 | 止损门控 | AI 自动设定止损价（默认 5%），触发即卖出 |
| 6 | 最低置信度 | confidence < 0.65 不推荐买入 |
| 7 | 黑名单 | ST/N 股票禁止交易 |
| 8 | 尾盘限制 | 14:45 后禁止新开仓 |
| 9 | 日亏损限制 | 日亏损超过限额自动停止 |
| 10 | 交易时间 | 仅限 A股交易时间 |
| 11 | 价格验证 | 下单前比对实时行情（偏差 > 3% 拦截） |
| 12 | 异常波动 | 涨跌停板附近禁止交易 |
| 13 | AI确认门控 | 买入置信度<65%自动拦截，实盘切换需风控确认 |
| 14 | 浏览器白名单 | 仅允许16个金融域名，非白名单请求阻止 |

## 🎭 Live2D 模型

| 模型 | 状态 | 说明 |
|------|------|------|
| 春 (Haru) | ✅ 内置 | 默认模型，8 种表情+情绪映射 |
| 桃濑日和 (Hiyori) | ✅ 内置 | 物理模拟 + 眨眼 |
| 虹色Mao | ✅ 内置 | 融合变形特效，8 种表情 |
| 马克君 (Mark) | ✅ 内置 | 新手友好，物理模拟 |
| ナトリ (Natori) | ✅ 内置 | 6种情绪表达 + 物理模拟 |
| 米 (Rice) | ✅ 内置 | 简洁可爱，物理模拟 |

所有 6 款模型均已内置，开箱即用。模型来自 [Live2D Cubism SDK](https://www.live2d.com/en/learn/sample/) 免费素材（Free Material License Agreement）。

## 💹 交易模式

### 模拟交易（默认 — 安全）

默认 `dry_run` 模式，所有交易均为模拟执行，**不会下真实订单**。适合验证策略、熟悉流程。

### 实盘交易（需配置券商）

切换到 `live` 模式后，小土豆通过 [easytrader](https://github.com/shidenggui/easytrader) 连接本地券商客户端下单：

| 环境变量 | 说明 |
|----------|------|
| `TRADING_MODE=live` | 切换到实盘模式 |
| `BROKER_ID=eastmoney` | 券商标识: `eastmoney`(东方财富) / `ths`(同花顺) / `htsec`(华泰XTP) |
| `EASTMONEY_ACCOUNT` | 东方财富账号 |
| `EASTMONEY_PASSWORD` | 东方财富密码 |

**实盘交易前提条件：**
1. 券商桌面客户端已安装、启动并登录
2. `TRADING_MODE=live` 已设置
3. 风控已确认（用户已设定资金金额）
4. 建议先用 dry_run 模式验证策略

```bash
# 切换到实盘模式
set TRADING_MODE=live
set BROKER_ID=eastmoney

# 或在聊天中告诉小土豆
"切换到实盘模式"
```

## 💳 计费系统

小土豆的计费系统对用户完全透明——只显示总价，不暴露任何分账细节。

### 续费流程

```
用户点击 🔄续费 或说"续费"
  ├─ 余额充足 → ✅ 自动扣款，"续费成功！"
  └─ 余额不足 → 显示USDT-TRC20收款二维码+地址
                 用户扫码付款后点 ✅已付款
                 系统确认充值 → 自动续费
```

### 计费面板

- 💳 计费按钮 → 查看各服务状态和总费用
- 💴 充值按钮 → 充值 ¥50 / ¥100
- 余额不足时自动提示续费

### 安全保护

- 收款地址仅在续费时显示，不在普通对话中暴露
- AI 严禁透露成本拆分、利润比例、费率结构
- 三层防护：AI提示词规则 + 输入拦截正则 + 输出脱敏正则
- 密钥保险箱值永不输出原文（只显示 sk-***xxxx 脱敏版本）

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 桌面壳 | Electron 28 |
| 前端 | Vite + React + Live2D |
| 后端 | Python + FastAPI + WebSocket |
| 大模型 | DeepSeek / SiliconFlow / Liner / Base44 Agent / OpenAI (5层故障转移) + Demo Mode |
| 数据源 | 东方财富AI SaaS (8API) + 问财智能选股 + 新浪财经实时行情 |
| 分析引擎 | PlanExecute多步分析 + 6Agent博弈分析 + 金融情感分析 |
| 数据库 | SQLite (本地) / CockroachDB (云端) |
| 加密 | Fernet(AES-128-CBC+HMAC-SHA256) (cryptography) |
| 计费 | 统一计费模块 (billing.py) + QR码续费 + 2x加价模型 |
| 通知 | Telegram / 飞书 / 钉钉 |
| 桌面操控 | Bytebot Agent(内置) / Bytebot Desktop(Docker) / Playwright / pyautogui |
| 交易引擎 | 7 阶段调度器 + 15 条风控规则 + AI确认门控 + 专业复盘系统 |
| 券商接口 | easytrader (东方财富/同花顺/华泰XTP) + dry_run 模拟 |

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
│           ├── pages/MainPage.jsx     # 主界面 + WS + 密钥遮蔽 + 计费面板
│           └── components/
│               ├── Live2D/            # Live2D 模型渲染 + 模型选择器
│               ├── DataPanel.jsx      # 数据源面板(问财+PlanExecute+东方财富)
│               ├── BillingPanel.jsx   # 计费面板模态框
│               ├── RenewalPanel.jsx   # 续费支付模态框(QR码+收款地址)
│               └── Sidebar.jsx        # 侧边栏+密钥快速粘贴(5个Key)
├── potato/                # 核心引擎
│   ├── trading/
│   │   ├── scheduler.py  # 7 阶段调度器
│   │   ├── analyzer.py    # AI 选股引擎 + 技术指标 + 东方财富数据注入
│   │   ├── plan_execute.py # PlanExecute 多步深度分析引擎
│   │   ├── executor.py    # 交易执行器 + 券商适配器
│   │   ├── broker.py      # 券商适配层 (dry_run/Live)
│   │   ├── journal.py     # 专业复盘系统
│   │   └── risk.py        # 15 条风控规则（含止损门控+AI确认门控）
│   ├── billing.py         # 统一计费模块(2x加价+QR续费+钱包地址持久化)
│   ├── eastmoney.py        # 东方财富 AI SaaS (8API+情感+异动+龙虎榜+筹码+行情)
│   ├── iwencai.py          # 问财智能选股 (2API+网页回退+自然语言查询)
│   ├── intel.py           # 资讯抓取 (Google News RSS)
│   ├── llm.py             # 5 层 LLM 故障转移 + async + Demo Mode
│   ├── vault.py            # Fernet(AES-128-CBC+HMAC-SHA256) 密钥保险箱
│   └── ...
├── schema/                # 数据库 Schema
├── .env.example           # 环境变量模板
├── LICENSE                 # Apache-2.0
└── README.md
```

## 🧪 测试

```bash
# 运行全部 181 个测试
python -m pytest tests/ -v

# 按模块运行
python -m pytest tests/test_trading_loop.py -v   # 7阶段交易闭环 (18 tests)
python -m pytest tests/test_demo_mode.py -v       # Demo模式 (15 tests)
python -m pytest tests/test_eastmoney.py -v       # 东方财富 (12 tests)
python -m pytest tests/test_iwencai.py -v         # 问财选股 (12 tests)
python -m pytest tests/test_plan_execute.py -v    # PlanExecute (16 tests)
python -m pytest tests/test_scheduler.py -v      # 调度器 (16 tests)
python -m pytest tests/test_async_llm.py -v      # Async LLM (8 tests)
python -m pytest tests/test_billing.py -v         # 计费 (25 tests)
python -m pytest tests/test_risk.py -v            # 风控 (14 tests)
python -m pytest tests/test_broker.py -v          # 券商 (21 tests)
python -m pytest tests/test_vault.py -v           # 密钥保险箱 (4 tests)
python -m pytest tests/test_e2e.py -v             # 端到端 (7 tests)
```

## 📄 License

[Apache-2.0](LICENSE) — Copyright 2025 自由的风