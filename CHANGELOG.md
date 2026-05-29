# Changelog

All notable changes to 小土豆 AI操盘桌宠 will be documented in this file.

## [1.0.0] - 2025-05-30

### Core Features
- 🧠 **5-Layer LLM Router**: DeepSeek → Liner → SiliconFlow → Base44 → OpenAI with automatic failover
- 🧊 **Live2D Desktop Pet**: 6 models, 8 expressions, emotion mapping
- 💬 **AI Chat**: Natural language conversation with memory (30-day persistence)
- 📊 **East Money AI SaaS**: 8 APIs + sentiment analysis + anomaly monitor + dragon-tiger list + chip distribution + realtime quotes
- 🎯 **Iwencai Smart Stock Selection**: 2 APIs + web fallback + natural language queries + news search
- 🔬 **PlanExecute Multi-Step Analysis**: Plan → Execute → Synthesize 3-phase engine
- 🤖 **Autonomous Trading**: 7-phase scheduler with 15 risk control rules
- 📰 **Professional Journaling**: Daily P&L, win rate, AI reflection
- 🖥️ **Bytebot Desktop Agent**: Built-in agent (port 9991) + Desktop (port 9990)
- 🔐 **Vault Key Store**: Fernet AES-128 encryption for 7 API keys with alias support
- 💳 **2x Billing Model**: User pays 2x, 1x to API provider, 1x to platform wallet
- 📋 **Demo Mode**: 6-type smart mock responses when no API key configured
- 🛡️ **Security**: Key masking (7-layer regex), source code protection, browser domain whitelist, AI confirmation gate

### Trading System
- 7-phase auto trading loop: Pre-market → Analysis → Open → Monitor → Midday → Afternoon → Review
- Risk control: 5% stop-loss, 10% take-profit, max 3 positions, conservative mode by default
- AI confirmation gate: BUY below 65% confidence blocked, live mode requires risk confirmation
- Only user-controlled item: investment amount (no upper limit)

### Architecture
- Backend: FastAPI + WebSocket on port 8000
- Frontend: React + Vite + Live2D on port 5173
- Bytebot Agent: port 9991 (built into backend process)
- Bytebot Desktop: port 9990
- Electron wrapper with system tray, auto-start, always-on-top
- NSIS installer: one-click download and run

### API Endpoints
- `GET /health` — system status with vault keys, demo mode, active providers
- `GET /version` — version, author, build date, features list
- `GET /verify` — startup verification check (all modules importable, vault status)
- `WS /ws` — WebSocket for all real-time communication

### Testing
- 191 pytest all green
- Coverage: Demo Mode, Trading Loop, PlanExecute, Scheduler, EastMoney, Iwencai, Async LLM, Billing, Broker, Risk, Vault, Version, Verify Endpoint

### Security Audit
- ✅ C-2/C-3/C-4/H-3/H-4/H-6/M-1/M-5/M-7/M-8/M-10/L-7 all passed
- Billing atomic transactions, vault Fernet-only, path injection protection
- CORS restricted, amount validation, error message sanitization
- Browser domain whitelist (16 financial domains + localhost)
- AI action confirmation gate for low-confidence trades

[1.0.0]: https://github.com/lopaycn-boop/a-stock-desktop-pet/releases/tag/v1.0.0