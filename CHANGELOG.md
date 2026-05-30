# Changelog

All notable changes to 小土豆 AI操盘桌宠 will be documented in this file.

## [1.6.0] - 2025-05-30

### New Features
- **Live2D Emotion Engine**: Pet now reacts with expressions — happy on trade success, sad on blocked, thinking when AI processes, surprised on alerts
- **Trade History Panel** (`📊 记录`): View recent trades, trigger daily review, load full history
- **Onboarding Wizard**: First-time user walkthrough — 5 steps explaining API keys, chat, trading, risk control, settings
- `useEmotionEngine.js` maps message content → emotion → model-specific expression with 4s auto-reset

### UX
- Quick action bar: added `📊 记录` button for trade history
- Live2D reacts to neuroState changes (thinking=思索表情, speaking=neutral, recording=surprised)
- Settings version label updated to v1.6.0

### Technical
- `inferEmotionFromMessage()` extracts emotion from trade emojis and system messages
- `emotionToExpression()` / `stateToExpression()` bridge emotions to model expression IDs
- 204 tests passing
- 42 features total

## [1.5.0] - 2025-05-30

### New Features
- **Risk Control UI**: Stop-loss (3-10%), take-profit (5-20%), max positions (1-5), mode (conservative/moderate/aggressive) — settings panel sends WS `update_risk` commands
- **Chat Export**: "📥 导出聊天记录" button in settings saves conversation as timestamped `.txt` file
- **Sound Volume Control**: Settings slider controls trade signal, risk alert, and chat notification volume via localStorage
- **TTS Mute**: Settings toggle mutes TTS voice output (shows text subtitle only)

### UX Improvements
- Settings panel now wired to actual behavior (opacity → Electron, always-on-top → Electron, auto-start → Electron, volume → useSounds, TTS mute → useAudioQueue)
- Settings persist across restarts via localStorage

### Technical
- `useSounds.js` reads volume/mute from localStorage settings
- `useAudioQueue.js` checks `isTtsMuted()` before playing audio, shows text-only when muted
- `SettingsPanel.jsx` adds risk control section with `<select>` dropdowns
- 204 tests passing

## [1.4.0] - 2025-05-30

### New Features
- **Settings Panel** (`⚙️ 设置`): Volume slider, TTS mute, desktop notifications toggle, wake word toggle, always-on-top, opacity slider, auto-start toggle
- **Connection Status Banner**: Sticky red banner when WebSocket disconnected
- **Typing Indicator**: "思考中..." bubble with loading dots in chat when AI is processing
- **System Message Themes**: Trade signals (blue), errors (red), successes (green), warnings (amber) — visual classes `.trade`, `.error`, `.success`, `.warning`

### UX Improvements
- **Quick Action Grouping**: Added `⚙️ 设置` and `🆙 更新` buttons
- Messages have subtle timestamp (HH:MM) above content
- Click any message to copy text

### Technical
- `SettingsPanel.jsx` with localStorage persistence
- Semantic CSS classes for system messages
- 204 tests passing

## [1.3.0] - 2025-05-30

### UX Improvements
- **Message Timestamps**: Every chat message now shows a time label (HH:MM)
- **Click to Copy**: Click any message to copy its text to clipboard
- **Keyboard Shortcuts**: Esc closes chat, Ctrl+Enter sends, Ctrl+1-9 triggers quick actions
- **Sound Effects**: Trade signals play a chime, blocked trades play a risk alert tone, via Web Audio API (no files needed)
- **Window Position Memory**: App remembers last window position/size across restarts

### Internal
- Added `useSounds.js` hook with `playTradeSignal()`, `playRiskAlert()`, `playChatNotification()`
- Added `KeyboardShortcuts` component (invisible, event-only)
- Added `get-bounds` IPC handler in Electron
- Window bounds saved to `userData/window-bounds.json`
- 204 tests passing

## [1.2.0] - 2025-05-30

### New Features
- **Desktop Notifications**: Trade signals, risk alerts, circuit breakers, quota exhaustion, backend/agent crashes now trigger native OS notifications via Browser Notification API
- **Wake Word Activation**: Voice wake word ("小土豆" / "土豆") opens chat automatically — toggle button in chat header
- **Auto-Update**: `electron-updater` integration with GitHub Releases — checks for updates on startup, prompts download, one-click restart
- **Check Updates Button**: "🆙 更新" quick action button in chat toolbar
- **System Event Notifications**: Backend crash, agent crash, suspend/resume, and update progress events show in chat

### Cleanup
- Removed unused `MessageList.jsx`, `InputArea.jsx`, `VoiceInput.jsx` components (MainPage inlines all functionality)
- Removed empty `components/Chat/` directory

### Technical
- `useDesktopNotification` hook: Browser Notification with click-to-focus, 8s auto-dismiss, auto-permission request
- `useWakeWord` hook now integrated into MainPage (previously orphaned)
- Electron `main.js`: `setupAutoUpdater()` with GitHub provider, download progress, quit-and-install
- `preload.js`: Added `checkForUpdates` IPC bridge
- Electron `package.json`: Added `publish` config for GitHub releases, version bumped to 1.2.0
- `version.py`: Bumped to 1.2.0, added 3 new features (desktop_notifications, wake_word, auto_update)
- 204 tests passing

## [1.1.0] - 2025-05-30

### New Feature: TrendRadar 舆情热点插件
- **trendradar_trending**: 多平台热点监控 — 微博/百度/知乎/抖音/头条/B站/36氪等15个平台实时热搜
- **trendradar_search**: 关键词搜索 — 跨平台搜索热点新闻，支持高/中相关度标记
- **trendradar_sentiment**: 舆情分析 — 金融相关热点自动识别、占比统计、各平台热度排名
- 公共NewsNow API数据源，无需额外API Key
- 5分钟本地缓存，减少重复请求
- WS实时推送 + 小土豆智能播报

### Bug Fixes
- Fix Electron spawn: restore `shell: true` (Windows中文路径需要)
- Fix `findPython`: add `shell: true` for Python version detection
- Add debug logging for backend spawn path resolution
- 204 pytest all green

## [1.0.2] - 2025-05-30

### Security Fixes
- **Critical**: Bind backend to `127.0.0.1` instead of `0.0.0.0` — no LAN exposure
- **High**: Disable Swagger/ReDoc docs (`docs_url=None, redoc_url=None`) — no API surface leak
- **High**: Remove `python` and `taskkill` from IPC command allowlist — prevents arbitrary code execution
- **High**: Set `shell: false` on backend and agent child process spawns — prevents shell injection
- **Medium**: Mask API keys in `/verify` output — redacts `sk-*`, `key=*`, `token=*` patterns
- **Medium**: Dynamic CORS whitelist — auto-matches actual backend port (8000-8009)

### Bug Fixes
- **Critical**: Add missing `import uvicorn` in `__main__` block — backend failed to start
- **Critical**: `BACKEND_PORT` changed from `const` to `let` — port fallback assignment was silently ignored
- **High**: Fix frontend WS race condition — port now injected in `did-finish-load` via CustomEvent, not after createWindow

### Features
- **Auto port fallback**: Backend finds available port 8000-8009 if preferred is occupied
- **Dynamic port detection**: Electron scans for backend port, frontend reconnects on `backend-port-ready`
- Backend startup banner now shows the actual port (reads `$PORT` env)

## [1.0.1] - 2025-05-30

### Security Fixes
- **Critical**: Fix source code disclosure blocklist bypass — blocked messages were still dispatched to AI (added `_blocked` flag)
- **Critical**: Fix `active_websockets` NameError causing backend crash on every graceful shutdown
- **High**: Add try/except to crash-prone WS handlers: `trade_auto_start/stop/status`, `voice_call_end`, `handle_set_voice`, `handle_list_voices`
- **High**: Fix XSS via `window.open()` on unvalidated `data:` URIs — removed `window.open()` on image click
- **High**: Validate `payload.image` prefix (must start with `data:image/` or `/9j/`)
- **Medium**: Cap user input at 10,000 chars, EM/IWencai queries at 1,000 chars, audio at 5MB
- **Medium**: Cap billing topup at 100,000 CNY, require explicit amount for confirm_payment (removed 72.5 CNY default)
- **Medium**: Whitelist `bytebot_desktop` params to prevent arbitrary kwargs injection
- **Medium**: Validate vault key names for path traversal characters (`/`, `\\`, `..`)
- **Low**: Replace multiple `str(e)` with `_safe_error(e)` to prevent internal info leaks

### Bug Fixes
- Fix frontend WS event type mismatch: `em_query` → added `em_financial_qa` case, `em_hotspot` → added `em_hotspot_discovery` case
- Remove ~500 chars of duplicated rules 28-40 in system prompt (saves LLM tokens)
- Add `active_websockets` tracking: append on accept, remove on disconnect/error
- Add WS disconnect/reconnect messages in chat UI
- Show `⚠️断开` status indicator in title bar when WS disconnected

### Features
- Add `/verify` HTTP endpoint for startup health checks
- Add `python -m potato.verify` CLI verification (checks all 17 modules, vault keys, demo mode)
- Add startup verification in Electron main.js (calls `/verify` after backend health check)
- Create CHANGELOG.md

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