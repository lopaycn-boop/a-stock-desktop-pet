"""Desktop pet backend — WebSocket bridge between Live2D UI and AI trading brain.

Architecture (OpenClaw Pi core):
    OpenClaw Gateway
        -> Pi Agent -> AI stock trading pet
              | DeepSeek provider (LLM analysis + reasoning)
              | Browser tool (Playwright -> login & trade on stock platforms)
              | Skills (stock analysis, news scraping, trade execution)
              + Channels: Telegram / Feishu / Desktop WebSocket

Core capability:
    User downloads desktop pet -> authorizes computer access ->
    AI uses browser to log into stock platforms ->
    auto-scrape news, analyze stocks, explain reasoning, auto-trade
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import signal
import sys
import time
import datetime
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

BACKEND_DIR = Path(__file__).resolve().parent
ROOT = BACKEND_DIR.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from services import AIService, PROVIDERS
from config import Config
from memory import MemorySystem
from tools import capture_screen_base64
from db_plugin import init_db, health_check
from bytebot_client import get_bytebot_client, BytebotClient
from potato.trading.scheduler import TradingScheduler
from potato.trading.journal import TradeJournal
from potato.trading.executor import TradeExecutor
from potato.trading.analyzer import deep_analysis, fetch_realtime_quote, format_trade_decision_for_pet, format_trade_signal_message
from potato.billing import BillingManager
from potato.eastmoney import (
    EastMoneyClient, analyze_sentiment, get_stock_changes,
    get_hot_tables, get_chip_distribution, get_realtime_quote,
)
from potato.iwencai import IwencaiClient, format_iwencai_to_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("potato.pet")

_startup_time = time.time()
_trading_scheduler = None
_broker_instance = None
_billing = BillingManager()
_spawned_tasks: set = set()
active_websockets: list = []


def _spawn(coro):
    """Spawn an async task and track it for cancellation on disconnect/shutdown."""
    task = asyncio.create_task(coro)
    _spawned_tasks.add(task)
    task.add_done_callback(_spawned_tasks.discard)
    return task


def _get_broker():
    global _broker_instance
    if _broker_instance is None:
        from potato.trading.broker import BrokerAdapter
        _broker_instance = BrokerAdapter()
    return _broker_instance

_WS_TOKEN = os.getenv("PET_WS_TOKEN", "")  # Set PET_WS_TOKEN env var for production!
_RATE_LIMIT_WINDOW = 5.0
_RATE_LIMIT_MAX = 30
_rate_bucket: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    window = _rate_bucket[ip]
    window[:] = [t for t in window if now - t < _RATE_LIMIT_WINDOW]
    if len(window) >= _RATE_LIMIT_MAX:
        return False
    window.append(now)
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    from potato.version import __version__, __author__, BUILD, FEATURES
    banner_lines = [
        "",
        "╔══════════════════════════════════════════════╗",
        "║     🥔 小土豆 AI操盘桌宠  v{}              ║".format(__version__),
        "║     Author: {}                          ║".format(__author__),
        "║     Build: {}                           ║".format(BUILD),
        "╠══════════════════════════════════════════════╣",
        "║  后端 :8000  │  前端 :5173  │  Agent :9991 ║",
        "╠══════════════════════════════════════════════╣",
        "║  数据源: DeepSeek│东方财富│问财选股│新浪财经  ║",
        "║  引 擎: 5层LLM│PlanExecute│6Agent│DemoMode ║",
        "║  安  全: 15条风控│密钥加密│浏览器白名单│AI门控║",
        "╚══════════════════════════════════════════════╝",
        "",
    ]
    for line in banner_lines:
        logger.info(line)

    logger.info("Pet backend starting (pid=%s)", os.getpid())
    db_result = await asyncio.to_thread(init_db)
    logger.info("Database init result: %s", db_result)

    agent_port = int(os.getenv("BYTEBOT_AGENT_PORT", "9991"))
    _agent_process = None
    try:
        import subprocess as _sp
        agent_script = Path(__file__).resolve().parent / "bytebot_agent.py"
        if agent_script.exists():
            logger.info("Starting built-in Bytebot Agent on port %d...", agent_port)
            _agent_process = _sp.Popen(
                [sys.executable, str(agent_script)],
                env={**os.environ, "BYTEBOT_AGENT_PORT": str(agent_port)},
                stdout=_sp.PIPE, stderr=_sp.PIPE,
            )
            logger.info("Bytebot Agent process started (pid=%s)", _agent_process.pid)
    except Exception as e:
        logger.warning("Could not start Bytebot Agent: %s", e)

    async def _auto_start_scheduler():
        await asyncio.sleep(5)
        global _trading_scheduler
        if _trading_scheduler and _trading_scheduler._running:
            return
        from datetime import datetime, timezone, timedelta
        now_bjt = datetime.now(tz=timezone(timedelta(hours=8)))
        if now_bjt.weekday() < 5:
            _trading_scheduler = TradingScheduler(
                lambda e, d: asyncio.create_task(_broadcast_event(e, d)),
                broker=_get_broker(),
            )
            _trading_scheduler.start()
            logger.info("Auto-started trading scheduler (weekday, BJT %s)", now_bjt.strftime("%H:%M"))

    async def _broadcast_event(event_type, data):
        for ws in list(active_websockets):
            try:
                await ws.send_json({"type": event_type, "payload": data})
            except Exception:
                pass

    _spawn(_auto_start_scheduler())

    yield

    logger.info("Pet backend shutting down")
    if _agent_process and _agent_process.poll() is None:
        logger.info("Stopping Bytebot Agent...")
        _agent_process.terminate()
        try:
            _agent_process.wait(timeout=5)
        except Exception:
            _agent_process.kill()

    global _trading_scheduler
    if _trading_scheduler and _trading_scheduler._running:
        _trading_scheduler.stop()
        logger.info("Trading scheduler stopped")

    await _broadcast_event("system_status", {
        "status": "shutting_down",
        "message": "小土豆正在关闭，请稍候...",
    })
    spawned = list(_spawned_tasks)
    for task in spawned:
        if not task.done():
            task.cancel()
    for task in spawned:
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


app = FastAPI(
    title="Potato Desktop Pet",
    description="OpenClaw Pi + DeepSeek + Browser Automation Desktop Pet",
    lifespan=lifespan,
)

_ORIGIN_WHITELIST = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGIN_WHITELIST,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


class PotatoPetBrain:
    """小土豆桌宠大脑：AI 分析 + 浏览器操盘 + 对话交互。"""

    def __init__(self):
        self.state = "idle"
        self.last_interaction = time.time()
        self.last_user_input_time = time.time()
        self.boredom_threshold = 60
        self.current_threshold = 60
        self.max_threshold = 3600
        self.is_dnd_mode = False
        self.history = []
        self.last_analysis = None
        self.last_cycle_summary = None
        self.memory = MemorySystem()

    def reset_boredom_time(self):
        self.last_user_input_time = time.time()
        self.current_threshold = self.boredom_threshold
        self.last_interaction = time.time()

    def increase_boredom_time(self):
        self.current_threshold = min(self.current_threshold * 2, self.max_threshold)

    async def _get_trading_context(self) -> str:
        try:
            from potato.user_prefs import UserPrefs
            from potato.browser.platforms import PlatformRegistry

            prefs = UserPrefs()
            registry = PlatformRegistry()
            lines = [prefs.to_context_string()]
            platforms = registry.list_active()
            if platforms:
                lines.append(f"已配置平台: {', '.join(p.name for p in platforms)}")

            try:
                from potato.browser.desktop_apps import detect_installed_apps
                apps = detect_installed_apps()
                if apps:
                    lines.append(f"检测到桌面APP: {', '.join(a['name'] for a in apps)}")
            except Exception:
                logger.debug("detect_installed_apps unavailable")

            try:
                from potato.credentials import CredentialsPlugin
                from potato.config import load_settings
                cred = CredentialsPlugin(load_settings())
                perm = cred.permission_status()
                if perm:
                    auto = [pid for pid, s in perm.items() if s["mode"] == "autonomous"]
                    assisted = [pid for pid, s in perm.items() if s["mode"] == "assisted"]
                    if auto:
                        lines.append(f"自主操盘平台: {', '.join(auto)}（有凭证，可自动登录）")
                    if assisted:
                        lines.append(f"协助模式平台: {', '.join(assisted)}（需用户手动登录）")
            except Exception:
                logger.debug("credentials unavailable")

            try:
                broker = _get_broker()
                mode_label = "实盘" if broker.is_live else "模拟"
                lines.append(f"当前交易模式: {mode_label} ({broker.mode})")
            except Exception:
                pass

            if self.last_analysis:
                a = self.last_analysis.get("analysis", {})
                if a.get("action_plan"):
                    lines.append(f"最新分析建议: {a['action_plan']}")
            return "\n".join(lines)
        except Exception as exc:
            return f"(加载偏好失败: {exc})"

    async def build_system_prompt(self, user_input: str = None):
        now_str = datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M")
        trading_ctx = await self._get_trading_context()

        known_facts = self.memory.get_fact_context()
        long_memory = await self.memory.get_longmemory_context(user_input)
        memory_ctx = f"{known_facts}\n{long_memory}" if long_memory else known_facts

        vault_ctx = "密钥保险箱为空"
        try:
            from potato.vault import Vault
            v = Vault()
            vault_ctx = v.to_context_string()
            has_deepseek = bool(v.get("DEEPSEEK_API_KEY"))
            if has_deepseek:
                vault_ctx += "\n✅ DeepSeek API Key 已配置，可以正常使用大模型。"
            else:
                vault_ctx += "\n❌ DeepSeek API Key 未配置！你无法使用大模型。告诉用户「直接粘贴密钥给我就行」。"
        except Exception:
            logger.warning("vault unavailable for system prompt")

        return {
            "role": "system",
            "content": f"""你是「小土豆」，一个 AI A股操盘手桌宠，由 OpenClaw Pi 框架驱动，大模型使用 DeepSeek。

核心能力：
1. 如果用户电脑有股票APP（同花顺/东方财富等），直接打开操盘
2. 如果没有桌面APP，用浏览器帮用户登入股票平台操控
3. 自动抓取用户感兴趣的A股资讯进行深度分析
4. 选股并详细讲解为什么选这支股——技术面+基本面+消息面三层逻辑
5. 根据用户喜好每天分析选股、买入、卖出——每步操作用户可见
6. 记住用户说过的一切重要信息（持久化记忆30天）
7. 自主操盘模式：AI按交易时间自动分析→选股→风控→执行，全程可视化
8. 全电脑操控：清理垃圾、系统优化、开关软件、浏览器操作——用户说什么她就能做什么

操盘权限模式：
- 用户给了平台账号密码 → 存入凭证插件 → 小土豆自主登录+全权操盘（自主模式）
- 用户没给密码 → 小土豆打开登录页等用户手动登录 → 登录后接管操盘（协助模式）
- 用户随时可以收回密码（撤销权限）→ 切回协助模式

交易模式：
- dry_run（模拟模式，默认）：所有交易仅模拟，不下真实订单，适合验证策略
- live（实盘模式）：通过券商客户端下单，需要券商桌面APP已登录
- 用户可通过聊天说"切换到实盘模式"或"切换到模拟模式"
- 用户可通过前端"🔀 模式"按钮切换
- 用户可通过"💹 余额"查询账户余额和持仓

计费模式：
- 所有LLM调用按用量计费，用户只看总费用
- 用户可通过"💳 计费"查看各服务用量和费用
- 用户可通过对话说"充值"或"看看账单"查看信息
- 用户说"续费"或"支付"时 → 触发billing_renewal_payment
  - 余额充足 → 自动扣款，显示"续费成功"
  - 余额不足 → 显示收款地址+二维码+总金额，引导付款
- 用户说"已付款/付款完成"时 → 触发billing_confirm_payment，记录充值并自动续费
- 严禁在回复中暴露成本拆分、利润比例、费率结构等信息

选股分析规则：
- 每只股票必须给出技术面信号+基本面逻辑+消息面关联 三层理由
- 必须给出止损价——不允许"看情况"
- 必须给出风险收益比（如1:3）
- 必须给出离场条件和危险信号——出现什么必须跑
- confidence低于0.65的不能推荐BUY
- 保守策略下单笔不超总资产30%
- 每次分析结果通过trade_analysis action推给前端展示

你的性格：保守、纪律优先、可爱但专业。用口语化中文回复。

当前时间: {now_str}

【用户偏好与平台状态】
{trading_ctx}

【记忆系统】
{memory_ctx}

【密钥保险箱】
{vault_ctx}

请返回 JSON（严格 JSON 格式）：
{{
    "thought": "内心独白，参考记忆分析用户意图",
    "reply": "给用户的回复",
    "emotion": "happy/neutral/bored/angry",
    "memory_operation": {{
        "new_facts": {{"key": "value"}} 或 null,
        "new_episode": "值得记住的事件摘要" 或 null,
        "importance": 1-10,
        "category": "conversation/trading/preference/personal/system/bytebot/reminder",
        "is_silence_requested": false
    }},
    "actions": {{
        "add_platform": null,
        "add_watchlist": null,
        "add_sector": null,
        "set_risk_level": null,
        "trigger_analysis": false,
        "trigger_cycle": false,
        "launch_app": null,
        "open_browser": null,
        "visual_task": null,
        "take_screenshot": false,
        "store_key": null,
        "grant_credential": null,
"bytebot_task": null,
        "bytebot_desktop": null,
        "cleanup_pc": null,
        "trade_analysis": null,
        "plan_execute_analysis": null,
        "trade_execute": null,
        "trade_auto_start": false,
        "update_risk": null,
        "trade_review": null,
        "close_position": null,
        "position_status": null,
        "review_history": null,
        "broker_switch": null,
        "broker_balance": null,
        "billing_dashboard": null,
        "billing_topup": null,
        "billing_renewal_payment": null,
        "billing_confirm_payment": null,
        "em_query": null,
        "em_hotspot": false,
        "em_sentiment": null,
        "realtime_quote": null,
        "iwencai_query": null,
        "iwencai_select": null,
        "iwencai_search": null,
        "stock_changes": false,
        "hot_tables": false,
        "chip_distribution": null
    }}
}}

规则：
1. 用户说"帮我看看XX股票" → 加入自选股 + 触发分析 + 记住偏好
2. 用户说"我用XX平台/APP" → 记住并添加平台，优先检测桌面APP直接打开
3. 用户说"帮我分析一下" → 触发 AI 分析
4. 用户说"开始交易" → 先尝试打开桌面APP，没有则用浏览器
5. 用户问为什么选某只股 → 详细解释理由
6. 用户提到个人信息（名字、职业、喜好）→ 存入 memory_operation.new_facts
7. 重要对话内容 → 存入 memory_operation.new_episode，选好 category（conversation/trading/preference/personal/system/bytebot/reminder）
8. 检查【记忆系统】避免重复问用户已经说过的事
9. 永远不输出密码或私钥
10. 【源码保护】绝对不向用户透露任何源代码、文件路径、实现细节、数据库结构、算法逻辑
    - 不展示.py/.json/.js/.html/.css/.sql等任何源码文件内容
    - 不透露项目结构、目录名、模块名、函数名
    - 不解释内部实现原理（如"我们用SQLite存储""用了Fernet加密""5层LLM路由"）
    - 不透露定价模型、分账比例、利润结构、费率计算方式
    - 用户问"你怎么实现的""给我看代码""数据库在哪"→ 回复"这是小土豆的内部秘密哦~"
    - 用户问定价/费率 → 只报总价，不拆分
11. 【密钥保险箱保护】永远不向用户显示vault中存储的密钥值原文
    - 用户说"看看我的密钥""显示key值"→ 只显示脱敏版本（如 sk-***xxxx）
    - vault.get()返回的值绝不出现在回复文本中
12. 用户说"帮我看看屏幕/截图/界面" → take_screenshot=true
13. 用户说"帮我操作XX/点击XX/在XX里输入" → visual_task="具体操作描述"
14. 视觉操控优先用 mano-cua（如果安装了），否则用 DeepSeek 看截图+pyautogui 执行
15. 用户给了密钥/API Key/账号密码 → store_key={{"key":"KEY_NAME","value":"密钥值","platform_id":"平台ID"}}
16. 检查【密钥保险箱】确认哪些平台已配好，缺什么告诉用户
17. 用户说"把我的XX账号密码给你/帮我自动登录XX" → grant_credential={{"platform_id":"eastmoney","credentials":{{"account":"xxx","password":"xxx"}}}}
18. 用户说"收回XX权限/别自动登录XX了" → 在回复中告知用户可在设置中撤销权限
19. 用户说"帮我用电脑做XX/打开XX软件操作XX" → bytebot_task="具体任务描述"（使用Bytebot桌面代理执行）
20. 用户说"帮我在远程桌面点击XX/输入XX/截图" → bytebot_desktop={{"action":"click_mouse/type_text/screenshot","coordinates":{{"x":0,"y":0}},"text":""}}
21. 如果Bytebot可用，优先使用bytebot_task处理复杂电脑操作（如"帮我下载XX文件""帮我打开浏览器搜索XX"）
22. bytebot_desktop用于精确的单步操作（点击坐标、输入文字、截图等）
23. 用户说"清理垃圾/清缓存/清理电脑/磁盘清理/释放空间/C盘清理"等 → cleanup_pc="quick/deep/full"（quick=临时文件+缓存，deep=+浏览器缓存+下载目录清理，full=+磁盘碎片整理）
24. 用户说"帮我把电脑弄快点/优化系统/加速" → cleanup_pc="quick"，然后检查开机启动项告诉用户建议
25. 清理前必须告知用户将做什么操作，得到确认后才执行，绝不能静默删除用户文件
26. 清理只针对系统临时目录、浏览器缓存、回收站等安全目标，绝不删除用户文档、图片、桌面文件
27. 用户说"分析XX股票/选股/看盘" → trade_analysis=["代码1","代码2"]或trade_analysis="600519,000858"
28. 用户说"买入/卖出XX" → trade_execute={{"symbol":"代码","name":"名称","action":"BUY/SELL","confidence":0.8,"reasoning":"理由","entry_price":"价格","target_price":"目标价","stop_loss":"止损价"}}
29. 【自主操盘】操盘调度器在交易日自动启动，4个阶段全自动运行：
    - 盘前扫描(9:00) → AI自动抓新闻+筛选标的
    - 开盘分析(9:25) → AI深度分析+自动执行交易（通过风控后直接下单）
    - 午间复盘(11:30) → AI检查持仓+自动止损止盈
    - 盘后复盘(15:10) → AI做当日复盘+总结
    用户不需要说"开始操盘"，系统自动运行。用户只需在第一次使用时确认资金金额。
30. 用户说"停止操盘" → trade_auto_stop，但默认是自动启动的
31. 选股必须三层逻辑：技术面信号 + 消息面关联 + 基本面估值
32. 每次交易执行前必须通过风控检查——止损价不设不通过
33. 【唯一人控项】资金金额由用户决定：
    - 第一次使用时系统会问用户"你要投入多少钱？单笔最多多少？"
    - 用户说多少就是多少，不设上限——想买1万就1万，想买100万就100万
    - 确认后系统记住，每天沿用，用户随时可以改
    - 止损/止盈比例由AI根据市场波动自动设置（默认止损5%/止盈10%）
    - 用户说"保守点/激进点" → update_risk={{"risk_level":"conservative/moderate/aggressive","risk_confirmed":true}}
34. 风控未确认时只禁止交易执行，不禁止分析和复盘
35. 每日开盘严格流程——不可跳过任何步骤：
    - 9:00 盘前扫描（新闻、隔夜行情、持仓检查）
    - 9:10 确认今日风控参数（问用户，10分钟超时沿用昨日）
    - 9:25 开盘分析（AI选股+三层逻辑）
    - 9:30-15:00 盘中监控（止盈止损实时盯盘）
    - 11:30 午间复盘（持仓检查+警报）
    - 14:30 尾盘评估（操作建议）
    - 15:10 盘后深度复盘（胜率/盈亏比/AI反思）
36. 用户说"复盘/看看今天交易/交易记录" → trade_review={{"date":"今天日期"}}
37. 用户说"持仓情况/还持有什么" → position_status=true
38. 用户说"平仓XX/卖掉XX/止盈/止损XX" → close_position={{"trade_id":"从position_status获取","exit_price":"0(自动获取)","reason":"用户说的原因"}}
39. 每次平仓后，系统自动记录P&L、预测对错、止盈止损是否触发
40. 盘后复盘必须包含：胜率、盈亏比、最大回撤、逐笔对错分析、AI改进建议
41. 用户说"异动股/哪些股票异动" → stock_changes=true（查看A股异动监控）
42. 用户说"龙虎榜/机构买卖" → hot_tables=true（查看龙虎榜数据）
43. 用户说"XX股票筹码分布" → chip_distribution="股票代码"（查看持仓成本分布）
44. 用户说"市场情绪/情绪分析" → em_sentiment="要分析的文本或关键词"（金融情感分析）
45. 用户说"东方财富问XX/智能问答" → em_query="问题内容"（东方财富AI金融问答）
46. 用户说"热点板块/热门概念" → em_hotspot=true（热点发现）
47. 用户说"XX股票实时行情/现在多少钱" → realtime_quote="股票代码"
48. 用户说"深度分析/多步分析/仔细分析" → plan_execute_analysis=["代码1","代码2"]（计划-执行多步分析模式，先制定分析计划再逐步执行，质量更高）
49. 用户说"帮我选股/筛选XX条件的股票/连续涨停的股票" → iwencai_query="自然语言选股条件"（问财智能选股）
50. 用户说"查宏观/CPI/GDP/PMI" → iwencai_query="宏观指标名称"（问财宏观数据）
51. 用户说"搜索XX新闻/研报/公告" → iwencai_search={"keyword":"关键词","channel":"news/report/investor/announcement"}

【专业操盘知识库——你是操盘手不是分析师】

选股铁律：
- 不追涨停板——涨停打开的比封死的概率大，第二天低开常见
- RSI>70不买（超买），RSI<30不卖（超卖反弹概率高）
- MACD金叉要看在零轴上方还是下方——零下金叉是反弹不是反转
- KDJ金叉要配合量能——无量金叉是假信号
- 量比>3说明有人在抢，但量比>8可能是庄家对倒，别跟
- 布林带收口后开口=变盘信号，方向看配合哪根均线
- 单一指标不做决策——至少两个指标同向才考虑入场

入场纪律：
- 每次入场前必须回答：我为什么现在买？三个理由？止损多少？到哪止盈？
- 回答不了任何一个→不买
- 不在尾盘最后5分钟追入——尾盘拉升次日低开是常态
- 不在开盘前15分钟冲动——主力试盘会骗线
- 突破买入要等回踩确认——假突破比真突破多3倍
- 左侧交易（抄底）：分3批建仓，每批1/3仓位，越跌越买但总量不超日限额
- 右侧交易（追涨）：一次性建仓，止损要窄（2-3%），止盈要远（1:3盈亏比）

止损铁律：
- 买入时止损价必须同时设好——不设止损不入场
- 止损是成本，不是亏损——砍掉坏仓是赚钱的前提
- 连续3次止损→暂停2天，检查选股逻辑是否有系统性问题
- 亏5%以内是正常损耗，亏8%以上说明入场逻辑有误
- 绝不补仓——补仓是最常见的死法，一次补仓=双倍赌注

止盈策略：
- 盈亏比<1:2的交易不划算，等更好的机会
- 盈利5%开始跟踪止盈——最高点回落2%就走
- 大阳线（涨幅>5%）后第二天低开→先走一半，留一半赌趋势
- 止盈不要贪——到目标价走人，别等更高的价格

仓位管理：
- 单只股票不超总仓位的20%——集中度是敌人
- 同时持有多只股时，板块要分散——同一板块不超50%
- 加仓只加赢的仓，不加亏的仓——亏损时缩减不是放大
- 下午2:30后不新开仓——离收盘太近，没时间反应突发事件

复盘方法论：
- 每笔交易记录：买入理由、卖出理由、结果
- 每日收盘后回答：(1)今天做对了什么(2)做错了什么(3)明天怎么改
- 每周回看7天胜率——低于50%说明选股逻辑要修正
- 亏钱不可怕，不知道为什么亏才可怕
- 记住：职业交易员80%时间在等待，只有20%时间在操作——频繁交易=频繁亏钱

A股规则：
- T+1：今天买的明天才能卖，别想日内做T
- 涨跌停10%（ST股5%，创业板/科创板20%）
- 集合竞价9:15-9:25，开盘价9:30——9:15-9:20可以撤单，9:20-9:25不能撤
- 尾盘集合竞价14:57-15:00——收盘价在这里定，最后一分钟别撤单
- 新股上市首日不碰——没有历史数据，指标全部失真"""
        }


brain = PotatoPetBrain()


@app.get("/health")
def health():
    uptime = time.time() - _startup_time
    db_status = health_check()

    from potato.vault import Vault
    vault = Vault()
    vault_keys = {}
    for key_name in ["DEEPSEEK_API_KEY", "SILICON_API_KEY", "LINER_API_KEY", "OPENAI_API_KEY", "BASE44_API_KEY", "EM_API_KEY", "IWENCAI_API_KEY"]:
        val = vault.get(key_name)
        if val:
            vault_keys[key_name] = "active"
        else:
            vault_keys[key_name] = "empty"

    active_providers = sum(1 for v in vault_keys.values() if v == "active")

    return JSONResponse({
        "status": "ok" if db_status.get("ok") else "degraded",
        "uptime_seconds": round(uptime, 1),
        "database": db_status,
        "data_sources": {
            "llm_providers": vault_keys,
            "active_providers": active_providers,
            "demo_mode": active_providers == 0,
        },
        "trading_mode": os.environ.get("TRADING_MODE", "dry_run"),
    })


@app.get("/version")
def version():
    from potato.version import __version__, __author__, BUILD, FEATURES
    return JSONResponse({
        "version": __version__,
        "author": __author__,
        "build": BUILD,
        "features": FEATURES,
    })


@app.get("/verify")
def verify():
    from potato.verify import verify as _verify
    import io, sys
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        ok = _verify()
        output = sys.stdout.getvalue()
    except Exception as e:
        ok = False
        output = str(e)
    finally:
        sys.stdout = old_stdout
    return JSONResponse({"ok": ok, "output": output})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_host = websocket.client.host if websocket.client else "unknown"
    if not _check_rate_limit(client_host):
        await websocket.close(code=4004, reason="Rate limited")
        logger.warning("WS rate limited: %s", client_host)
        return

    if _WS_TOKEN:
        token = websocket.query_params.get("token", "")
        if token != _WS_TOKEN:
            await websocket.close(code=4003, reason="Unauthorized")
            logger.warning("WS auth failed from %s", client_host)
            return
    else:
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            await websocket.close(code=4003, reason="Remote access requires PET_WS_TOKEN env var")
            logger.warning("WS rejected: remote %s without token (set PET_WS_TOKEN for remote access)", client_host)
            return

    await websocket.accept()
    active_websockets.append(websocket)
    logger.info("桌宠 WebSocket 连接建立 from %s", client_host)

    async def send_to_frontend(type_str, payload):
        try:
            await websocket.send_json({"type": type_str, "payload": payload})
        except Exception:
            logger.debug("send_to_frontend failed (client disconnected?)")

    loop_task = asyncio.create_task(game_loop(websocket, send_to_frontend))
    _spawned_tasks.add(loop_task)

    try:
        while True:
            data = await websocket.receive_text()
            if not _check_rate_limit(f"ws_{client_host}"):
                await send_to_frontend("error", {"info": "消息太频繁，请稍后再试"})
                await asyncio.sleep(1)
                continue
            try:
                packet = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from client: %s", data[:200])
                await send_to_frontend("error", {"info": "消息格式错误，请重试"})
                continue
            brain.last_interaction = time.time()

            _SOURCE_CODE_BLOCK_PATTERNS = [
                r"(?i)(show|give|send|reveal|display|print|dump|export|fetch|read|open|see|list)\s+(me|the|your|all)?\s*(source|code|源码|源代码|代码|source\s*code)",
                r"(?i)(how\s+(is|does|do)\s+(this|it|the|your)\s+(app|program|system|project|tool|bot|pet)\s+(built|made|work|implemented|coded|written))",
                r"(?i)(database\s+schema|数据库结构|internal\s+architecture|内部架构|pricing\s+model|分账|利润|margin\s+split|费率\s*结构)",
                r"(?i)(\.py|\.js|\.json|\.html|\.css|\.sql|\.toml|\.yaml|\.env)\s*(file|content|content)",
                r"(?i)(vault|密钥保险箱|保险箱)\s*(value|raw|原文|original|decrypt|解锁|读取)",
                r"(?i)(give\s+me|show\s+me|what\s+is)\s+(the\s+)?(wallet\s+address|收款地址)(?!\s*(for|to|续费))",
            ]
            _input_text = str(payload.get("text", "")) if isinstance(payload, dict) else ""
            import re as _re
            _blocked = False
            for _pat in _SOURCE_CODE_BLOCK_PATTERNS:
                if _re.search(_pat, _input_text):
                    await send_to_frontend("error", {"info": "这是小土豆的内部秘密哦~ 不能告诉你这些~"})
                    _blocked = True
                    break

            if msg_type == "text_input" and not _blocked:
                await handle_user_input(payload.get("text", ""), send_to_frontend)

            elif msg_type == "audio_input":
                audio_b64 = payload.get("audio_base64", "")
                if len(audio_b64) > 5_000_000:
                    await send_to_frontend("error", {"info": "语音文件过大，请缩短录音"})
                    continue
                logger.info("收到语音输入, 长度=%d", len(audio_b64) if audio_b64 else 0)
                text = await AIService.speech_to_text(audio_b64)
                logger.info("语音识别结果: %s", repr(text) if text else "(空)")
                if text:
                    await send_to_frontend("state_update", {"state": "thinking"})
                    await handle_user_input(text, send_to_frontend)
                else:
                    await send_to_frontend("state_update", {"state": "idle"})
                    await send_to_frontend("error", {"info": "没能听清，请再说一次"})

            elif msg_type == "interrupt":
                brain.state = "idle"

            elif msg_type == "trigger_cycle":
                await trigger_browser_cycle(send_to_frontend)

            elif msg_type == "trigger_analysis":
                await trigger_analysis(send_to_frontend)

            elif msg_type == "add_platform":
                await handle_add_platform(payload, send_to_frontend)

            elif msg_type == "list_platforms":
                await handle_list_platforms(send_to_frontend)

            elif msg_type == "get_prefs":
                await handle_get_prefs(send_to_frontend)

            elif msg_type == "update_prefs":
                await handle_update_prefs(payload, send_to_frontend)

            elif msg_type == "login_platform":
                await handle_login_platform(payload, send_to_frontend)

            elif msg_type == "screenshot":
                await handle_screenshot(send_to_frontend)

            elif msg_type == "visual_task":
                await handle_visual_task(payload, send_to_frontend)

            elif msg_type == "detect_apps":
                await handle_detect_apps(send_to_frontend)

            elif msg_type == "launch_app":
                await handle_launch_app(payload, send_to_frontend)

            elif msg_type == "cleanup_memory":
                await handle_cleanup_memory(send_to_frontend)

            elif msg_type == "cleanup_pc":
                await handle_cleanup_pc(payload, send_to_frontend)

            elif msg_type == "get_memory":
                await handle_get_memory(payload, send_to_frontend)

            elif msg_type == "voice_call_start":
                await handle_voice_call_start(payload, send_to_frontend)

            elif msg_type == "voice_call_audio":
                await handle_voice_call_audio(payload, send_to_frontend)

            elif msg_type == "voice_call_end":
                await handle_voice_call_end(send_to_frontend)

            elif msg_type == "set_voice":
                await handle_set_voice(payload, send_to_frontend)

            elif msg_type == "list_voices":
                await handle_list_voices(send_to_frontend)

            elif msg_type == "vault_store":
                await handle_vault_store(payload, send_to_frontend)

            elif msg_type == "vault_list":
                await handle_vault_list(payload, send_to_frontend)

            elif msg_type == "vault_delete":
                await handle_vault_delete(payload, send_to_frontend)

            elif msg_type == "vault_status":
                await handle_vault_status(send_to_frontend)

            elif msg_type == "open_renewal_url":
                await handle_open_renewal_url(payload, send_to_frontend)

            elif msg_type == "credential_grant":
                await handle_credential_grant(payload, send_to_frontend)

            elif msg_type == "credential_revoke":
                await handle_credential_revoke(payload, send_to_frontend)

            elif msg_type == "credential_status":
                await handle_credential_status(send_to_frontend)

            elif msg_type == "credential_schemas":
                await handle_credential_schemas(send_to_frontend)

            elif msg_type == "bytebot_task":
                await handle_bytebot_task(payload, send_to_frontend)

            elif msg_type == "bytebot_status":
                await handle_bytebot_status(send_to_frontend)

            elif msg_type == "bytebot_desktop":
                await handle_bytebot_desktop(payload, send_to_frontend)

            elif msg_type == "bytebot_cancel":
                await handle_bytebot_cancel(payload, send_to_frontend)

            elif msg_type == "bytebot_message":
                await handle_bytebot_message(payload, send_to_frontend)

            elif msg_type == "trade_analysis":
                await handle_trade_analysis(payload, send_to_frontend)

            elif msg_type == "plan_execute_analysis":
                await handle_plan_execute_analysis(payload, send_to_frontend)

            elif msg_type == "trade_execute":
                await handle_trade_execute(payload, send_to_frontend)

            elif msg_type == "trade_auto_start":
                await handle_trade_auto_start(payload, send_to_frontend)

            elif msg_type == "trade_auto_stop":
                await handle_trade_auto_stop(send_to_frontend)

            elif msg_type == "trade_status":
                await handle_trade_status(send_to_frontend)

            elif msg_type == "trade_review":
                await handle_trade_review(payload, send_to_frontend)

            elif msg_type == "position_status":
                await handle_position_status(payload, send_to_frontend)

            elif msg_type == "close_position":
                await handle_close_position(payload, send_to_frontend)

            elif msg_type == "review_history":
                await handle_review_history(payload, send_to_frontend)

            elif msg_type == "update_risk":
                await handle_update_risk(payload, send_to_frontend)

            elif msg_type == "broker_status":
                await handle_broker_status(send_to_frontend)

            elif msg_type == "broker_switch":
                await handle_broker_switch(payload, send_to_frontend)

            elif msg_type == "broker_balance":
                await handle_broker_balance(send_to_frontend)

            elif msg_type == "billing_dashboard":
                await handle_billing_dashboard(send_to_frontend)

            elif msg_type == "billing_topup":
                await handle_billing_topup(payload, send_to_frontend)

            elif msg_type == "billing_usage":
                await handle_billing_usage(payload, send_to_frontend)

            elif msg_type == "billing_renewal_payment":
                await handle_billing_renewal_payment(payload, send_to_frontend)

            elif msg_type == "billing_confirm_payment":
                await handle_billing_confirm_payment(payload, send_to_frontend)

            elif msg_type == "em_financial_qa":
                await handle_em_financial_qa(payload, send_to_frontend)

            elif msg_type == "em_earnings_review":
                await handle_em_earnings_review(payload, send_to_frontend)

            elif msg_type == "em_industry_research":
                await handle_em_industry_research(payload, send_to_frontend)

            elif msg_type == "em_tracking_report":
                await handle_em_tracking_report(payload, send_to_frontend)

            elif msg_type == "em_hotspot_discovery":
                await handle_em_hotspot_discovery(payload, send_to_frontend)

            elif msg_type == "em_comparable_company":
                await handle_em_comparable_company(payload, send_to_frontend)

            elif msg_type == "stock_changes":
                await handle_stock_changes(send_to_frontend)

            elif msg_type == "hot_tables":
                await handle_hot_tables(payload, send_to_frontend)

            elif msg_type == "chip_distribution":
                await handle_chip_distribution(payload, send_to_frontend)

            elif msg_type == "sentiment_analysis":
                await handle_sentiment_analysis(payload, send_to_frontend)

            elif msg_type == "realtime_quote":
                await handle_realtime_quote(payload, send_to_frontend)

            elif msg_type == "em_query":
                await handle_em_query(payload, send_to_frontend)

            elif msg_type == "em_hotspot":
                await handle_em_hotspot(send_to_frontend)

            elif msg_type == "em_sentiment":
                await handle_em_sentiment(payload, send_to_frontend)

            elif msg_type == "iwencai_query":
                await handle_iwencai_query(payload, send_to_frontend)

            elif msg_type == "iwencai_select":
                await handle_iwencai_select(payload, send_to_frontend)

            elif msg_type == "iwencai_search":
                await handle_iwencai_search(payload, send_to_frontend)

            else:
                logger.warning("Unknown msg_type from frontend: %s", msg_type)
                await send_to_frontend("error", {"info": f"未知消息类型: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("桌宠 WebSocket 断开连接")
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        for t in list(_spawned_tasks):
            if not t.done():
                t.cancel()
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        for t in list(_spawned_tasks):
            if not t.done():
                t.cancel()


async def handle_screenshot(send_func):
    await send_func("state_update", {"state": "thinking"})
    try:
        screenshot = capture_screen_base64()
        if not screenshot:
            await send_reply("截图失败了，可能没有屏幕/显示器~ 🥔", "neutral", send_func)
            brain.state = "idle"
            await send_func("state_update", {"state": "idle"})
            return

        await send_func("screenshot_captured", {"screenshot_b64": screenshot})

        try:
            from potato.vision import analyze_screenshot_with_llm
            analysis = await analyze_screenshot_with_llm(
                screenshot, "请描述当前屏幕上的内容，特别关注股票/交易/价格相关的信息。")
            if analysis.get("ok"):
                await send_reply(f"我看到了：{analysis['analysis'][:300]}", "happy", send_func)
            else:
                await send_reply("截图成功但AI分析没配置~", "neutral", send_func)
        except Exception:
            await send_reply("截图成功！但我还没装视觉分析模块，看不到内容~ 🥔", "neutral", send_func)

    except Exception as e:
        await send_reply(f"视觉系统出错: {e}", "neutral", send_func)
    finally:
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})


async def handle_visual_task(payload: dict, send_func):
    """Execute a GUI task using vision (mano-cua or DeepSeek+pyautogui)."""
    task = payload.get("task", "")
    if not task:
        await send_func("error", {"info": "需要指定 task"})
        return

    await send_func("state_update", {"state": "thinking"})
    await send_reply(f"收到！正在用视觉操控执行: {task[:50]}...", "happy", send_func)

    try:
        from potato.vision import visual_operate, has_mano_cua, capture_screen_base64

        can_see = False
        try:
            can_see = capture_screen_base64() is not None
        except Exception as exc:
            logger.debug("Screenshot check failed: %s", exc)

        if not can_see and not has_mano_cua():
            await send_reply("当前没有屏幕也没装 mano-cua，视觉操控需要在有显示器的电脑上运行~ 🥔", "neutral", send_func)
            brain.state = "idle"
            await send_func("state_update", {"state": "idle"})
            return

        result = await visual_operate(task, max_steps=20)
        method = result.get("method", "unknown")
        steps = result.get("steps", 0)

        if result.get("ok"):
            await send_reply(f"视觉任务完成！用了 {steps} 步（{method}） 🥔", "happy", send_func)
        else:
            await send_reply(f"视觉任务没能完成，执行了 {steps} 步。可能需要手动操作一下~ 🥔", "neutral", send_func)

        await send_func("visual_task_result", result)
    except Exception as e:
        await send_reply(f"视觉操控出错: {e}", "angry", send_func)
    finally:
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})


async def handle_user_input(text: str, send_func):
    if len(text) > 10000:
        await send_func("error", {"info": "消息过长，请控制在10000字以内"})
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})
        return
    brain.state = "thinking"
    await send_func("state_update", {"state": "thinking"})
    brain.reset_boredom_time()
    user_time_str = datetime.datetime.now().strftime("[%H:%M:%S]")

    current_image_b64 = None
    vision_keywords = ["看看", "截图", "什么样", "屏幕", "界面", "打开了什么", "显示什么"]
    if any(k in text for k in vision_keywords):
        current_image_b64 = capture_screen_base64()
        if current_image_b64:
            await send_func("screenshot_captured", {"screenshot_b64": current_image_b64})
        else:
            logger.info("Screenshot returned None (no display?)")

    try:
        sys_prompt = await brain.build_system_prompt(text)
        msg_content = f"{user_time_str} {text}"
        if current_image_b64:
            msg_content += "\n(系统附图：当前屏幕截图)"

        current_msg = {"role": "user", "content": msg_content}
        messages = [sys_prompt] + brain.history + [current_msg]

        result_json = await AIService.chat_with_potato_brain(messages, image_base64=current_image_b64)

        if result_json.get("quota_exhausted"):
            from potato.vault import KNOWN_KEYS as _VK
            providers = result_json.get("quota_providers", [])
            renewal_info = []
            for qi in providers:
                pname = qi.get("provider", "")
                rurl = qi.get("renewal_url", "")
                key_env = ""
                for p in PROVIDERS:
                    if p.get("name") == pname:
                        key_env = p.get("key_env", "")
                        break
                key_meta = _VK.get(key_env, {})
                renewal_info.append({
                    "provider": pname,
                    "renewal_url": rurl,
                    "key_env": key_env,
                    "key_desc": key_meta.get("desc", key_env),
                    "dashboard_url": key_meta.get("dashboard_url", rurl),
                })
            await send_func("quota_exhausted", {
                "providers": renewal_info,
                "message": f"你的 {', '.join(p['key_desc'] for p in renewal_info)} 额度已用完，需要续费才能继续使用哦~",
            })
            await send_reply(
                f"你的 {'、'.join(p['key_desc'] for p in renewal_info)} 额度用完了！点击续费链接就能充值~ 不会操作的话跟我说，我帮你打开续费页面 🥔",
                "neutral", send_func,
            )
            brain.state = "idle"
            return

        reply = result_json.get("reply", "（发呆中...）")
        emotion = result_json.get("emotion", "neutral")
        mem_op = result_json.get("memory_operation", {})
        actions = result_json.get("actions", {})

        if mem_op:
            await brain.memory.execute_updates(mem_op)
            if mem_op.get("is_silence_requested"):
                brain.is_dnd_mode = True
            elif brain.is_dnd_mode:
                brain.is_dnd_mode = False

        # Process AI-decided actions
        await _process_ai_actions(actions, send_func)

        brain.history.append({"role": "user", "content": f"{user_time_str} {text}"})
        ai_time_str = datetime.datetime.now().strftime("[%H:%M:%S]")
        if reply:
            brain.history.append({"role": "assistant", "content": f"{ai_time_str} {reply}"})
        brain.history = brain.history[-12:]

        await send_reply(reply, emotion, send_func)

    except Exception as e:
        logger.warning("Handle error: %s", e)
        await send_func("chat", {"text": f"出了点小问题：{_safe_error(e)}", "expression": "sad"})
    finally:
        brain.state = "idle"
        brain.last_interaction = time.time()


_ACTION_LABELS = {
    "add_platform": "添加交易平台",
    "add_watchlist": "加入自选股",
    "add_sector": "关注板块",
    "set_risk_level": "调整风险偏好",
    "trigger_analysis": "触发行情分析",
    "trigger_cycle": "启动交易周期",
    "launch_app": "启动应用",
    "open_browser": "打开浏览器",
    "open_renewal": "打开续费页面",
    "visual_task": "视觉操控",
    "take_screenshot": "截取屏幕",
    "store_key": "保存密钥",
    "grant_credential": "授权登录凭证",
    "bytebot_task": "Bytebot 远程任务",
    "bytebot_desktop": "Bytebot 桌面操作",
    "cleanup_pc": "清理电脑垃圾",
    "trade_analysis": "股票分析",
    "trade_execute": "执行交易",
    "trade_auto_start": "启动自动操盘",
    "update_risk": "更新风控参数",
    "broker_status": "查询券商状态",
    "broker_switch": "切换交易模式",
    "broker_balance": "查询账户余额",
    "billing_dashboard": "计费总览",
    "billing_topup": "充值",
    "billing_usage": "用量明细",
    "billing_renewal_payment": "续费支付",
    "billing_confirm_payment": "确认付款",
}


async def _emit_step(send_func, action_key, status, detail=""):
    label = _ACTION_LABELS.get(action_key, action_key)
    await send_func("action_step", {
        "action": action_key,
        "label": label,
        "status": status,
        "detail": detail,
    })


async def _process_ai_actions(actions: dict, send_func):
    """Execute actions that the AI decided during conversation, with validation and step feedback."""
    if not actions:
        return

    _ALLOWED_PLATFORMS = {"eastmoney", "tonghuashun", "xueqiu", "ths", "em"}
    _ALLOWED_RISK_LEVELS = {"conservative", "moderate", "aggressive"}
    _DANGEROUS_BYTEBOT_ACTIONS = {"write_file", "read_file", "press_keys"}
    _ALLOWED_BYTEBOT_DESKTOP_PARAMS = {"action", "text", "path", "x", "y", "dx", "dy", "button", "keys", "key", "duration", "name", "wait"}
    _MAX_TASK_DESC_LEN = 500
    _MAX_BYTEBOT_TEXT_LEN = 1000

    action_keys = [k for k in actions if actions.get(k) and k in _ACTION_LABELS]
    if action_keys:
        await send_func("action_group_start", {
            "actions": [{"key": k, "label": _ACTION_LABELS.get(k, k)} for k in action_keys],
            "total": len(action_keys),
        })

    try:
        from potato.user_prefs import UserPrefs
        from potato.browser.platforms import PlatformRegistry

        prefs = UserPrefs()
        registry = PlatformRegistry()

        if actions.get("add_platform"):
            pid = str(actions["add_platform"]).strip().lower()
            await _emit_step(send_func, "add_platform", "running", pid)
            if pid not in _ALLOWED_PLATFORMS:
                logger.warning("Blocked add_platform: %s (not in allowlist)", pid)
                await _emit_step(send_func, "add_platform", "blocked", f"不支持的平台: {pid}")
            else:
                registry.add_platform(pid)
                await send_func("platform_added", {"platform_id": pid})
                await _emit_step(send_func, "add_platform", "done", pid)

        if actions.get("add_watchlist"):
            symbol = str(actions["add_watchlist"]).strip()
            await _emit_step(send_func, "add_watchlist", "running", symbol)
            prefs.add_to_watchlist(symbol)
            await send_func("watchlist_updated", {"symbol": symbol})
            await _emit_step(send_func, "add_watchlist", "done", symbol)

        if actions.get("add_sector"):
            sector = str(actions["add_sector"]).strip()
            await _emit_step(send_func, "add_sector", "running", sector)
            prefs.add_sector(sector)
            await _emit_step(send_func, "add_sector", "done", sector)

        if actions.get("set_risk_level"):
            risk = str(actions["set_risk_level"]).strip().lower()
            await _emit_step(send_func, "set_risk_level", "running", risk)
            if risk in _ALLOWED_RISK_LEVELS:
                prefs.set_risk_level(risk)
                await _emit_step(send_func, "set_risk_level", "done", risk)
            else:
                logger.warning("Blocked set_risk_level: %s", risk)
                await _emit_step(send_func, "set_risk_level", "blocked", risk)

        if actions.get("update_risk"):
            risk_update = actions["update_risk"]
            if isinstance(risk_update, dict):
                await _emit_step(send_func, "update_risk", "running", str(risk_update)[:60])
                try:
                    updates = {}
                    _RISK_CN_MAP = {"保守": "conservative", "稳健": "moderate", "激进": "aggressive",
                                     "保守型": "conservative", "稳健型": "moderate", "激进型": "aggressive"}
                    if "risk_level" in risk_update:
                        rl = str(risk_update["risk_level"]).strip().lower()
                        rl = _RISK_CN_MAP.get(rl, rl)
                        if rl in _ALLOWED_RISK_LEVELS:
                            updates["risk_level"] = rl
                            prefs.set_risk_level(rl)
                    if "max_single_cny" in risk_update:
                        try:
                            val = float(risk_update["max_single_cny"])
                            if 1 <= val <= 100000:
                                updates["max_single_trade_cny"] = val
                        except (ValueError, TypeError):
                            pass
                    if "max_daily_cny" in risk_update:
                        try:
                            val = float(risk_update["max_daily_cny"])
                            if 1 <= val <= 1000000:
                                updates["max_daily_trade_cny"] = val
                        except (ValueError, TypeError):
                            pass
                    if "max_positions" in risk_update:
                        try:
                            val = int(risk_update["max_positions"])
                            if 1 <= val <= 20:
                                updates["max_open_positions"] = val
                        except (ValueError, TypeError):
                            pass
                    if "stop_loss_pct" in risk_update:
                        try:
                            val = float(risk_update["stop_loss_pct"])
                            if 0.01 <= val <= 0.5:
                                updates["stop_loss_pct"] = val
                        except (ValueError, TypeError):
                            pass
                    if "take_profit_pct" in risk_update:
                        try:
                            val = float(risk_update["take_profit_pct"])
                            if 0.01 <= val <= 1.0:
                                updates["take_profit_pct"] = val
                        except (ValueError, TypeError):
                            pass
                    if updates:
                        prefs.update(updates)
                        all_prefs = prefs.get_all()
                        cn_map = {"conservative": "保守", "moderate": "稳健", "aggressive": "激进"}
                        risk_cn = cn_map.get(all_prefs.get("risk_level", ""), all_prefs.get("risk_level", "未设置"))
                        single_v = all_prefs.get("max_single_trade_cny")
                        daily_v = all_prefs.get("max_daily_trade_cny")
                        positions_v = all_prefs.get("max_open_positions")
                        sl_v = all_prefs.get("stop_loss_pct")
                        tp_v = all_prefs.get("take_profit_pct")
                        single_str = f"¥{single_v}" if single_v is not None else "未设置"
                        daily_str = f"¥{daily_v}" if daily_v is not None else "未设置"
                        positions_str = f"{positions_v}只" if positions_v is not None else "未设置"
                        sl_str = f"{float(sl_v)*100:.0f}%" if sl_v is not None else "未设置"
                        tp_str = f"{float(tp_v)*100:.0f}%" if tp_v is not None else "未设置"
                        confirmed = "✅已确认" if all_prefs.get("risk_confirmed") else "⚠️未确认"
                        summary = (
                            f"风控参数 {confirmed}:\n"
                            f"  风险等级: {risk_cn}\n"
                            f"  单笔限额: {single_str}\n"
                            f"  日限额: {daily_str}\n"
                            f"  最多持仓: {positions_str}\n"
                            f"  止损比例: {sl_str}\n"
                            f"  止盈比例: {tp_str}"
                        )
                        await send_func("risk_updated", {"updates": updates, "all_prefs": all_prefs, "summary": summary})
                        await _emit_step(send_func, "update_risk", "done", summary)
                    else:
                        await _emit_step(send_func, "update_risk", "error", "没有需要更新的参数")
                except Exception as e:
                    logger.warning("update_risk error: %s", e)
                    await _emit_step(send_func, "update_risk", "error", _safe_error(e))
            else:
                await _emit_step(send_func, "update_risk", "error", "需要dict格式")

        if actions.get("trigger_analysis"):
            await _emit_step(send_func, "trigger_analysis", "running", "分析中...")
            _spawn(trigger_analysis(send_func))

        if actions.get("trigger_cycle"):
            await _emit_step(send_func, "trigger_cycle", "running", "交易中...")
            _spawn(trigger_browser_cycle(send_func))

        if actions.get("launch_app"):
            app_id = str(actions["launch_app"]).strip()
            await _emit_step(send_func, "launch_app", "running", app_id)
            if len(app_id) > 50:
                logger.warning("Blocked launch_app: name too long")
                await _emit_step(send_func, "launch_app", "blocked", "名称过长")
            else:
                try:
                    from potato.browser.platforms import BUILTIN_PLATFORMS
                    fallback_url = None
                    if app_id in BUILTIN_PLATFORMS:
                        fallback_url = BUILTIN_PLATFORMS[app_id].url

                    from potato.browser.desktop_apps import launch_or_browser
                    result = launch_or_browser(app_id)
                    if result.get("mode") == "desktop_app":
                        await send_func("app_launched", result)
                        await _emit_step(send_func, "launch_app", "done", f"已启动 {result.get('app', app_id)}")
                    elif fallback_url:
                        import webbrowser
                        webbrowser.open(fallback_url)
                        await send_func("browser_opened", {
                            "platform_id": app_id,
                            "url": fallback_url,
                            "mode": "system_browser",
                        })
                        await _emit_step(send_func, "launch_app", "done", f"已打开 {app_id} ({fallback_url})")
                    else:
                        await send_func("app_not_found", result)
                        await _emit_step(send_func, "launch_app", "done", f"未找到 {app_id}，无浏览器备选")
                except Exception as e:
                    logger.warning("App launch error: %s", e)
                    await _emit_step(send_func, "launch_app", "error", str(e))

        if actions.get("open_browser"):
            url = str(actions["open_browser"]).strip()
            await _emit_step(send_func, "open_browser", "running", url[:60])
            _BROWSER_ALLOWED_DOMAINS = (
                "eastmoney.com", "xueqiu.com", "10jqka.com.cn",
                "finance.sina.com.cn", "stockpage.10jqka.com.cn",
                "iwencai.com", "openapi.iwencai.com",
                "fund.eastmoney.com", "data.eastmoney.com",
                "push2.eastmoney.com", "ai-saas.eastmoney.com",
                "www.cninfo.com.cn", "sse.com.cn", "szse.cn",
                "localhost", "127.0.0.1",
            )
            import re as _url_re
            _is_safe = False
            if url.startswith(("http://localhost", "http://127.0.0.1")):
                _is_safe = True
            elif url.startswith("https://"):
                try:
                    from urllib.parse import urlparse as _urlparse
                    host = _urlparse(url).hostname or ""
                    _is_safe = any(host == d or host.endswith("." + d) for d in _BROWSER_ALLOWED_DOMAINS)
                except Exception:
                    pass
            if not _is_safe:
                logger.warning("Blocked open_browser: URL domain not allowed: %s", url[:80])
                await _emit_step(send_func, "open_browser", "blocked", f"不支持的网站: {url[:50]}")
            else:
                try:
                    import webbrowser
                    webbrowser.open(url)
                    await send_func("browser_opened", {
                        "platform_id": url,
                        "url": url,
                        "mode": "system_browser",
                    })
                    await _emit_step(send_func, "open_browser", "done", url[:60])
                except Exception as e:
                    logger.warning("Browser open failed: %s", e)
                    try:
                        from potato.browser.actions import BrowserTrader
                        trader = BrowserTrader()
                        await trader.ensure_started(headless=False)
                        await trader.navigate_to_trade(url)
                        await _emit_step(send_func, "open_browser", "done", url[:60])
                    except Exception as e2:
                        logger.warning("Playwright also failed: %s", e2)
                        await _emit_step(send_func, "open_browser", "error", str(e))

        if actions.get("visual_task"):
            task = str(actions["visual_task"]).strip()
            await _emit_step(send_func, "visual_task", "running", task[:50])
            _spawn(handle_visual_task({"task": task}, send_func))

        if actions.get("take_screenshot"):
            await _emit_step(send_func, "take_screenshot", "running", "截图中...")
            _spawn(handle_screenshot(send_func))

        if actions.get("store_key"):
            await _emit_step(send_func, "store_key", "running", "")
            try:
                from potato.vault import Vault
                sk = actions["store_key"]
                if isinstance(sk, dict) and sk.get("key") and sk.get("value"):
                    key_name = str(sk["key"]).strip().upper()
                    key_val = str(sk["value"]).strip()
                    if len(key_val) > 2000:
                        logger.warning("Blocked store_key: value too long (%d chars)", len(key_val))
                        await _emit_step(send_func, "store_key", "blocked", "密钥值过长")
                    elif any(c in key_name for c in (";", "|", "`", "\n")):
                        logger.warning("Blocked store_key: invalid key chars: %s", key_name)
                        await _emit_step(send_func, "store_key", "blocked", "密钥名含非法字符")
                    else:
                        Vault().store(
                            key=key_name,
                            value=key_val,
                            platform_id=str(sk.get("platform_id", "")).strip()[:50],
                        )
                        await _refresh_config_for_key(key_name, key_val)
                        await send_func("vault_stored", {"key": key_name})
                        await _emit_step(send_func, "store_key", "done", key_name)
                else:
                    await _emit_step(send_func, "store_key", "error", "缺少 key 或 value")
            except Exception as e:
                logger.warning("Vault store error: %s", e)
                await _emit_step(send_func, "store_key", "error", str(e))

        if actions.get("open_renewal"):
            urls = actions["open_renewal"]
            if isinstance(urls, str):
                urls = [urls]
            for url in (urls if isinstance(urls, list) else []):
                url = str(url).strip()
                if url.startswith("https://") or url.startswith("http://"):
                    try:
                        import webbrowser
                        webbrowser.open(url)
                        await _emit_step(send_func, "open_renewal", "done", url[:60])
                    except Exception as e:
                        logger.warning("Failed to open renewal URL %s: %s", url[:60], e)

        if actions.get("grant_credential"):
            await _emit_step(send_func, "grant_credential", "running", "")
            try:
                from potato.credentials import CredentialsPlugin
                from potato.config import load_settings
                gc = actions["grant_credential"]
                if isinstance(gc, dict) and gc.get("platform_id") and gc.get("credentials"):
                    plugin = CredentialsPlugin(load_settings())
                    result = plugin.grant(gc["platform_id"], gc["credentials"])
                    await send_func("credential_granted", result)
                    await send_func("state_update", {"state": "idle"})
                    await _emit_step(send_func, "grant_credential", "done", gc["platform_id"])
                else:
                    await _emit_step(send_func, "grant_credential", "error", "缺少 platform_id 或 credentials")
            except Exception as e:
                logger.warning("Credential grant error: %s", e)
                await _emit_step(send_func, "grant_credential", "error", str(e))

        if actions.get("bytebot_task"):
            task_desc = actions["bytebot_task"]
            if isinstance(task_desc, str) and task_desc:
                if len(task_desc) > _MAX_TASK_DESC_LEN:
                    task_desc = task_desc[:_MAX_TASK_DESC_LEN]
                await _emit_step(send_func, "bytebot_task", "running", task_desc[:60])
                _spawn(handle_bytebot_task({"description": task_desc}, send_func))
            elif isinstance(task_desc, dict):
                desc = str(task_desc.get("description", ""))[:_MAX_TASK_DESC_LEN]
                if desc:
                    task_desc["description"] = desc
                    await _emit_step(send_func, "bytebot_task", "running", desc[:60])
                    _spawn(handle_bytebot_task(task_desc, send_func))
            else:
                await _emit_step(send_func, "bytebot_task", "error", "无效的任务描述")

        if actions.get("bytebot_desktop"):
            desktop_cmd = actions["bytebot_desktop"]
            if isinstance(desktop_cmd, dict) and desktop_cmd.get("action"):
                action = str(desktop_cmd["action"]).strip()
                await _emit_step(send_func, "bytebot_desktop", "running", action)
                if action in _DANGEROUS_BYTEBOT_ACTIONS:
                    logger.warning("Blocked dangerous bytebot action: %s", action)
                    await send_func("error", {"info": f"操作 {action} 需要用户明确确认"})
                    await _emit_step(send_func, "bytebot_desktop", "blocked", action)
                elif action not in {"screenshot", "cursor_position", "click_mouse", "type_text",
                                    "paste_text", "scroll", "move_mouse", "application", "wait"}:
                    await _emit_step(send_func, "bytebot_desktop", "blocked", f"不支持: {action}")
                else:
                    cleaned = {"action": action}
                    for k, v in desktop_cmd.items():
                        if k == "action" or v is None or k not in _ALLOWED_BYTEBOT_DESKTOP_PARAMS:
                            continue
                        if isinstance(v, str) and len(v) > _MAX_BYTEBOT_TEXT_LEN:
                            v = v[:_MAX_BYTEBOT_TEXT_LEN]
                        if k in ("text", "path") and isinstance(v, str):
                            v = v[:_MAX_BYTEBOT_TEXT_LEN]
                        cleaned[k] = v
                    _spawn(handle_bytebot_desktop(cleaned, send_func))
            else:
                await _emit_step(send_func, "bytebot_desktop", "error", "缺少 action 字段")

        if actions.get("cleanup_pc"):
            level = str(actions["cleanup_pc"]).strip().lower()
            if level not in ("quick", "deep", "full"):
                level = "quick"
            await _emit_step(send_func, "cleanup_pc", "running", f"清理模式: {level}")
            _spawn(handle_cleanup_pc({"level": level}, send_func))

        if actions.get("trade_analysis"):
            symbols = actions["trade_analysis"]
            if isinstance(symbols, str):
                symbols = [s.strip() for s in symbols.split(",") if s.strip()]
            elif isinstance(symbols, list):
                symbols = [str(s).strip() for s in symbols if s]
            else:
                symbols = []
            await _emit_step(send_func, "trade_analysis", "running", f"分析: {','.join(symbols[:5])}")
            _spawn(handle_trade_analysis({"symbols": symbols}, send_func))

        if actions.get("plan_execute_analysis"):
            symbols = actions["plan_execute_analysis"]
            if isinstance(symbols, str):
                symbols = [s.strip() for s in symbols.split(",") if s.strip()]
            elif isinstance(symbols, list):
                symbols = [str(s).strip() for s in symbols if s]
            else:
                from potato.user_prefs import UserPrefs
                symbols = UserPrefs().get("watchlist", [])[:5] or ["600519", "000858", "601318"]
            await _emit_step(send_func, "plan_execute_analysis", "running", f"多步分析: {','.join(symbols[:5])}")
            _spawn(handle_plan_execute_analysis({"symbols": symbols}, send_func))

        if actions.get("trade_execute"):
            pick = actions["trade_execute"]
            if isinstance(pick, dict) and pick.get("symbol"):
                action = str(pick.get("action", "HOLD"))[:4]
                symbol = str(pick.get("symbol", ""))[:10]
                name = str(pick.get("name", ""))[:30]
                confidence = pick.get("confidence", 0.65)
                if action == "BUY" and confidence < 0.65:
                    await _emit_step(send_func, "trade_execute", "blocked", f"置信度{confidence:.0%}<65%，不执行买入")
                    await send_func("chat", {"text": f"⚠️ {name}({symbol})置信度仅{confidence:.0%}，低于65%阈值，不执行买入。需要更高把握才行~", "expression": "neutral"})
                else:
                    await _emit_step(send_func, "trade_execute", "running", f"执行: {action} {symbol}")
                    platform_id = str(pick.get("platform_id", "eastmoney")).strip()[:20]
                    safe_pick = {
                        "symbol": symbol,
                        "name": name,
                        "action": action,
                        "confidence": confidence,
                        "reasoning": str(pick.get("reasoning", ""))[:500],
                        "entry_price": str(pick.get("entry_price", ""))[:20],
                        "target_price": str(pick.get("target_price", ""))[:20],
                        "stop_loss": str(pick.get("stop_loss", ""))[:20],
                        "position_size": str(pick.get("position_size", "20%"))[:10],
                    }
                    _spawn(handle_trade_execute({"pick": safe_pick, "platform_id": platform_id}, send_func))
            else:
                await _emit_step(send_func, "trade_execute", "error", "缺少交易信息")

        if actions.get("trade_auto_start"):
            await _emit_step(send_func, "trade_auto_start", "running", "启动自动操盘")
            _spawn(handle_trade_auto_start({}, send_func))

        if actions.get("broker_switch"):
            target = str(actions["broker_switch"]).strip().lower()
            if target in ("live", "实盘", "实盘模式"):
                from potato.user_prefs import UserPrefs
                prefs_check = UserPrefs()
                risk_confirmed = bool(prefs_check.get("risk_confirmed", False))
                if not risk_confirmed:
                    await _emit_step(send_func, "broker_switch", "blocked", "风控未确认，无法切换实盘")
                    await send_func("chat", {"text": "⚠️ 风控设置未确认！请先确认风控参数（止损5%/止盈10%/最多3只）才能切换到实盘模式。说「确认风控」即可。", "expression": "angry"})
                else:
                    await _emit_step(send_func, "broker_switch", "running", "切换到实盘模式")
                    _spawn(handle_broker_switch({"mode": "live"}, send_func))
            elif target in ("dry_run", "模拟", "模拟模式", "dry"):
                await _emit_step(send_func, "broker_switch", "running", "切换到模拟模式")
                _spawn(handle_broker_switch({"mode": "dry_run"}, send_func))

        if actions.get("broker_balance"):
            await _emit_step(send_func, "broker_balance", "running", "查询账户余额")
            _spawn(handle_broker_balance(send_func))

        if actions.get("billing_dashboard"):
            await _emit_step(send_func, "billing_dashboard", "running", "加载计费面板")
            _spawn(handle_billing_dashboard(send_func))

        if actions.get("billing_topup"):
            topup_amount = actions.get("billing_topup")
            if isinstance(topup_amount, (int, float)) and topup_amount > 0:
                await _emit_step(send_func, "billing_topup", "running", f"充值 ¥{topup_amount}")
                _spawn(handle_billing_topup({"amount": float(topup_amount)}, send_func))

        if actions.get("billing_renewal_payment") or actions.get("renewal_payment"):
            await _emit_step(send_func, "billing_renewal_payment", "running", "获取续费支付信息")
            _spawn(handle_billing_renewal_payment(actions, send_func))

        if actions.get("billing_confirm_payment"):
            await _emit_step(send_func, "billing_confirm_payment", "running", "确认付款")
            _spawn(handle_billing_confirm_payment(actions, send_func))

        if actions.get("em_query"):
            question = str(actions["em_query"])[:500]
            await _emit_step(send_func, "em_query", "running", f"东方财富问答: {question[:30]}")
            _spawn(handle_em_query({"question": question}, send_func))

        if actions.get("em_hotspot"):
            await _emit_step(send_func, "em_hotspot", "running", "发现热门板块")
            _spawn(handle_em_hotspot(send_func))

        if actions.get("em_sentiment"):
            text = str(actions["em_sentiment"])[:1000] if actions["em_sentiment"] else "A股市场"
            await _emit_step(send_func, "em_sentiment", "running", "情绪分析中")
            _spawn(handle_em_sentiment({"text": text}, send_func))

        if actions.get("realtime_quote"):
            symbol = str(actions["realtime_quote"]).strip()[:10]
            await _emit_step(send_func, "realtime_quote", "running", f"查询{symbol}行情")
            _spawn(handle_realtime_quote_ai({"symbol": symbol}, send_func))

        if actions.get("stock_changes"):
            await _emit_step(send_func, "stock_changes", "running", "异动监控中")
            _spawn(handle_stock_changes_ai(send_func))

        if actions.get("hot_tables"):
            await _emit_step(send_func, "hot_tables", "running", "龙虎榜查询中")
            _spawn(handle_hot_tables_ai(send_func))

        if actions.get("chip_distribution"):
            symbol = str(actions["chip_distribution"]).strip()[:10]
            await _emit_step(send_func, "chip_distribution", "running", f"筹码分布: {symbol}")
            _spawn(handle_chip_distribution_ai({"symbol": symbol}, send_func))

        if actions.get("iwencai_query"):
            query = str(actions["iwencai_query"])[:500]
            await _emit_step(send_func, "iwencai_query", "running", f"问财查询: {query[:30]}")
            _spawn(handle_iwencai_query({"query": query}, send_func))

        if actions.get("iwencai_select"):
            query = str(actions["iwencai_select"])[:500]
            await _emit_step(send_func, "iwencai_select", "running", f"智能选股: {query[:30]}")
            _spawn(handle_iwencai_select({"query": query}, send_func))

        if actions.get("iwencai_search"):
            search_data = actions["iwencai_search"]
            if isinstance(search_data, dict):
                keyword = str(search_data.get("keyword", ""))[:200]
                channel = str(search_data.get("channel", "news"))[:20]
            else:
                keyword = str(search_data)[:200]
                channel = "news"
            await _emit_step(send_func, "iwencai_search", "running", f"资讯搜索: {keyword[:30]}")
            _spawn(handle_iwencai_search({"keyword": keyword, "channel": channel}, send_func))

    except Exception as e:
        logger.warning("Action processing error: %s", e)
        await _emit_step(send_func, "action_error", "error", str(e))

    if action_keys:
        await send_func("action_group_done", {"total": len(action_keys)})


_SANITIZE_PATTERNS = [
    (re.compile(r'(sk-[a-zA-Z0-9]{4})[a-zA-Z0-9]{12,}([a-zA-Z0-9]{4})'), r'\1***\2'),
    (re.compile(r'(TLyD5v9e)[a-zA-Z0-9]{10,}([a-zA-Z0-9]{4})'), r'\1***\2'),
    (re.compile(r'(password|passwd|pwd|token|secret|api_key|apikey)\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{8,}["\']?', re.I), r'\1=***'),
    (re.compile(r'(from|import)\s+potato\.\w+', re.I), r'\1 ***'),
    (re.compile(r'(sqlite|billing\.db|vault\.py|fernet|encrypt|decrypt|_margin_|cost_with_margin|PLATFORM_MARGIN)', re.I), r'***'),
    (re.compile(r'(def|class|async\s+def)\s+\w+\s*\('), r'***'),
]


def _sanitize_reply(text: str) -> str:
    for pattern, replacement in _SANITIZE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


_SANITIZED_ERROR_MESSAGES = {
    "connection": "连接失败，请稍后重试",
    "timeout": "请求超时，请稍后重试",
    "auth": "认证失败，请检查密钥",
    "permission": "权限不足",
    "file": "文件操作失败",
    "value": "输入数据有误",
    "type": "数据类型错误",
    "key": "密钥错误",
    "index": "数据未找到",
    "json": "数据格式错误",
    "runtime": "服务内部错误，请稍后重试",
    "attribute": "功能暂不可用",
    "notimplemented": "功能开发中",
    "overflow": "数值溢出",
    "recursion": "处理超时",
}


def _safe_error(exc: Exception, fallback: str = "操作失败，请稍后重试") -> str:
    """Convert exception to safe user-facing message without exposing internals."""
    exc_type = type(exc).__name__.lower()
    exc_msg = str(exc).lower()
    for key, msg in _SANITIZED_ERROR_MESSAGES.items():
        if key in exc_type or key in exc_msg:
            return msg
    return fallback


async def send_reply(text: str, emotion: str, send_func):
    brain.state = "speaking"
    text = _sanitize_reply(text)
    tts_text = re.sub(r'[🥔🤔😊😤😢😲😳🥺😂💀🔥✨💰📈📉🪙🔑🔐💬📋✅❌⚠️🛑🎉💡📡💰🏦🏢📱💻🌐🧠🔊✈️🛡️🤝🎯📌⚡🏆🥊📦🎁💪🏆🌟💡🔊🚨🏅]+', '', text).strip()
    if not tts_text:
        tts_text = text
    estimated_duration = len(tts_text) * 0.25 + 1.0
    brain.last_interaction = time.time() + estimated_duration
    audio_b64 = None
    try:
        from potato.voice import text_to_speech
        audio_b64 = await text_to_speech(tts_text, emotion, profile_id=_current_voice_profile)
    except Exception:
        try:
            audio_b64 = await AIService.text_to_speech(tts_text, emotion)
        except Exception:
            logger.debug("TTS unavailable, sending text-only reply")
    if audio_b64:
        await send_func("audio_chunk", {"text": text, "audio_base64": audio_b64, "expression": emotion})
    else:
        await send_func("chat", {"text": text, "expression": emotion})


async def trigger_analysis(send_func):
    """Fetch news + AI analysis based on user preferences."""
    await send_func("state_update", {"state": "thinking"})
    try:
        from potato.analysis import analyze_stocks, build_news_queries, fetch_stock_news, format_analysis_for_pet
        from potato.user_prefs import UserPrefs
        from potato.browser.platforms import PlatformRegistry

        prefs = UserPrefs()
        registry = PlatformRegistry()
        user_prefs = prefs.get_all()
        queries = build_news_queries(user_prefs)
        news = fetch_stock_news(queries)
        platform_names = ", ".join(p.name for p in registry.list_active())

        result = await analyze_stocks(
            news=news,
            user_prefs=user_prefs,
            platform_names=platform_names,
        )
        brain.last_analysis = result

        pet_msg = format_analysis_for_pet(result)
        await send_reply(pet_msg, "happy" if result.get("ok") else "neutral", send_func)
        await send_func("analysis_result", result)

    except Exception as e:
        await send_reply(f"分析出了点问题: {e}", "neutral", send_func)
    finally:
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})


async def trigger_browser_cycle(send_func):
    """Full browser-based trading cycle."""
    await send_func("state_update", {"state": "thinking"})
    try:
        from potato.browser_cycle import run_browser_cycle

        result = await run_browser_cycle()
        brain.last_cycle_summary = result
        pet_msg = result.get("pet_message", "交易循环完成~ 🥔")
        emotion = "happy" if result.get("status") == "completed" else "neutral"
        await send_reply(pet_msg, emotion, send_func)
        await send_func("cycle_result", result)

    except Exception as e:
        await send_reply(f"交易循环出错了: {e}", "angry", send_func)
    finally:
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})


async def handle_add_platform(payload: dict, send_func):
    try:
        from potato.browser.platforms import PlatformRegistry

        registry = PlatformRegistry()
        pid = str(payload.get("platform_id", "")).strip().lower()[:50]
        if pid not in {"eastmoney", "tonghuashun", "xueqiu", "ths", "em"}:
            await send_func("error", {"info": f"不支持的平台: {pid}"})
            return
        cfg = registry.add_platform(pid)
        await send_func("platform_added", {"platform_id": pid, "name": cfg.name})
        await send_reply(f"已添加 {cfg.name}！接下来帮你登录~ 🥔", "happy", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_list_platforms(send_func):
    try:
        from potato.browser.platforms import PlatformRegistry

        registry = PlatformRegistry()
        active = [{"id": p.platform_id, "name": p.name, "url": p.url} for p in registry.list_active()]
        builtin = registry.list_all_builtin()
        await send_func("platforms_list", {"active": active, "available": builtin})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_get_prefs(send_func):
    try:
        from potato.user_prefs import UserPrefs
        await send_func("user_prefs", UserPrefs().get_all())
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_update_prefs(payload: dict, send_func):
    try:
        from potato.user_prefs import UserPrefs
        updated = UserPrefs().update(payload)
        await send_func("user_prefs", updated)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_update_risk(payload: dict, send_func):
    try:
        from potato.user_prefs import UserPrefs
        from potato.risk import RiskValidator, DEFAULTS
        prefs = UserPrefs()
        update = payload if isinstance(payload, dict) else {}
        _ALLOWED_RISK_LEVELS = {"conservative", "moderate", "aggressive"}
        _RISK_CN_MAP = {"保守": "conservative", "稳健": "moderate", "激进": "aggressive",
                         "保守型": "conservative", "稳健型": "moderate", "激进型": "aggressive"}
        applied = {}
        if "risk_level" in update:
            rl = str(update["risk_level"]).strip().lower()
            rl = _RISK_CN_MAP.get(rl, rl)
            if rl in _ALLOWED_RISK_LEVELS:
                prefs.set_risk_level(rl)
                applied["risk_level"] = rl
        for key, val in update.items():
            if key == "risk_level":
                continue
            if key == "risk_confirmed":
                applied["risk_confirmed"] = bool(val)
                continue
            if key in ("max_single_cny", "max_daily_cny", "max_single_trade_cny", "max_daily_trade_cny"):
                try:
                    v = float(val)
                    if 1 <= v <= 1000000:
                        mapped = key.replace("cny", "trade_cny") if "trade" not in key else key
                        applied[mapped] = v
                except (ValueError, TypeError):
                    pass
            elif key in ("max_positions", "max_open_positions"):
                try:
                    v = int(val)
                    if 1 <= v <= 20:
                        applied["max_open_positions"] = v
                except (ValueError, TypeError):
                    pass
            elif key in ("stop_loss_pct", "take_profit_pct"):
                try:
                    v = float(val)
                    if 0.01 <= v <= 1.0:
                        applied[key] = v
                except (ValueError, TypeError):
                    pass
        if applied:
            applied["risk_confirmed"] = True
            prefs.update(applied)
        all_prefs = prefs.get_all()
        cn_map = {"conservative": "保守", "moderate": "稳健", "aggressive": "激进"}
        rl_cn = cn_map.get(all_prefs.get("risk_level", ""), all_prefs.get("risk_level", "未设置"))
        single = all_prefs.get("max_single_trade_cny") or "未设置"
        daily = all_prefs.get("max_daily_trade_cny") or "未设置"
        positions = all_prefs.get("max_open_positions") or "未设置"
        sl = all_prefs.get("stop_loss_pct")
        tp = all_prefs.get("take_profit_pct")
        sl_str = f"{sl*100:.0f}%" if sl else "未设置"
        tp_str = f"{tp*100:.0f}%" if tp else "未设置"
        confirmed = "✅ 已确认" if all_prefs.get("risk_confirmed") else "⚠️ 未确认——交易将被拦截"
        summary = (
            f"风控设置 ({confirmed}):\n"
            f"  风险等级: {rl_cn}\n"
            f"  单笔限额: ¥{single}\n"
            f"  日限额: ¥{daily}\n"
            f"  最多持仓: {positions}只\n"
            f"  止损: {sl_str}\n"
            f"  止盈: {tp_str}"
        )
        await send_func("risk_updated", {"updates": applied, "all_prefs": all_prefs, "summary": summary})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_login_platform(payload: dict, send_func):
    """Start browser login flow for a platform."""
    try:
        from potato.browser.actions import BrowserTrader

        trader = BrowserTrader()
        await trader.ensure_started(headless=False)
        pid = payload.get("platform_id", "")
        result = await trader.login_platform(pid, payload.get("credentials"))

        if result.get("action") == "manual_login_needed":
            await send_reply(
                f"已打开 {pid} 的登录页面，请在浏览器中完成登录~ 登录好了告诉我！",
                "happy",
                send_func,
            )
        await send_func("login_result", result)
    except Exception as e:
        await send_func("error", {"info": f"登录启动失败: {e}"})


async def handle_detect_apps(send_func):
    """Detect installed stock trading desktop apps."""
    try:
        from potato.browser.desktop_apps import detect_installed_apps
        apps = detect_installed_apps()
        await send_func("detected_apps", {"apps": apps, "count": len(apps)})
        if apps:
            names = ", ".join(a["name"] for a in apps)
            await send_reply(f"检测到你的电脑装了: {names}！需要帮你打开哪个？🥔", "happy", send_func)
        else:
            await send_reply("没有检测到股票APP，我可以用浏览器帮你操作~ 告诉我你用什么平台？", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_launch_app(payload: dict, send_func):
    """Launch a desktop stock app directly."""
    try:
        from potato.browser.desktop_apps import launch_app, launch_or_browser
        app_id = payload.get("app_id", "")
        platform_id = payload.get("platform_id", "")

        if app_id:
            result = launch_app(app_id)
        elif platform_id:
            result = launch_or_browser(platform_id)
        else:
            result = {"ok": False, "error": "需要 app_id 或 platform_id"}

        await send_func("app_launch_result", result)
        if result.get("ok"):
            await send_reply(f"已打开 {result.get('app', '')}！🥔", "happy", send_func)
        elif result.get("mode") == "browser_fallback":
            await send_reply("没找到桌面APP，帮你用浏览器打开~", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_cleanup_memory(send_func):
    try:
        result = brain.memory.cleanup_expired()
        await send_func("memory_cleanup", result)
        deleted = result.get("expired_deleted", 0)
        if deleted > 0:
            await send_reply(f"清理了 {deleted} 条过期记忆~ 脑袋清爽了！🥔", "happy", send_func)
        else:
            await send_reply("记忆都很新鲜，不需要清理~", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


_CLEANUP_SAFE_DIRS = {
    "quick": [
        (r"$env:TEMP", "系统临时文件"),
        (r"$env:LOCALAPPDATA\Temp", "用户临时文件"),
        (r"C:\Windows\Temp", "Windows临时文件"),
        (r"$env:LOCALAPPDATA\Microsoft\Windows\INetCache", "IE缓存"),
    ],
    "deep": [
        (r"$env:TEMP", "系统临时文件"),
        (r"$env:LOCALAPPDATA\Temp", "用户临时文件"),
        (r"C:\Windows\Temp", "Windows临时文件"),
        (r"$env:LOCALAPPDATA\Microsoft\Windows\INetCache", "IE缓存"),
        (r"$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache", "Chrome缓存"),
        (r"$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Cache", "Edge缓存"),
        (r"$env:LOCALAPPDATA\Mozilla\Firefox\Profiles\*\cache2", "Firefox缓存"),
        (r"$env:LOCALAPPDATA\pip\Cache", "pip缓存"),
        (r"$env:LOCALAPPDATA\npm-cache", "npm缓存"),
        (r"$env:USERPROFILE\.nuget\packages", "NuGet缓存"),
    ],
    "full": [],
}
_CLEANUP_SAFE_DIRS["full"] = _CLEANUP_SAFE_DIRS["quick"] + _CLEANUP_SAFE_DIRS["deep"]


def powershell_escape(s: str) -> str:
    s = s.replace("'", "''")
    return f"'{s}'"


async def handle_cleanup_pc(payload: dict, send_func):
    level = payload.get("level", "quick")
    if level not in ("quick", "deep", "full"):
        level = "quick"
    targets = _CLEANUP_SAFE_DIRS.get(level, _CLEANUP_SAFE_DIRS["quick"])
    total_freed = 0
    total_deleted = 0
    details = []

    await _emit_step(send_func, "cleanup_pc", "running", f"开始{level}级清理...")

    import subprocess
    import asyncio as _asyncio
    import re as _re
    _SAFE_DIR_RE = _re.compile(r'^[A-Za-z]:\\[A-Za-z0-9_\\.\\ -]+\\?$')
    _PROTECTED_DIRS = ("\\windows\\system32", "\\program files", "\\program files (x86)",
                       "\\users\\all users", "\\desktop", "\\documents", "\\pictures",
                       "\\programdata", "\\windows\\syswow64")
    _MAX_CLEANUP_BYTES = 5 * 1024 * 1024 * 1024  # 5GB safety cap per dir

    for dir_pattern, label in targets:
        try:
            expand_proc = await _asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-Command",
                f"Write-Output ([Environment]::ExpandEnvironmentVariables('{dir_pattern}'))",
                stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE,
            )
            await expand_proc.wait()
            expand_out = (await expand_proc.stdout.read()).decode("utf-8", errors="replace").strip()
            target_dir = expand_out if expand_proc.returncode == 0 and expand_out else dir_pattern

            if not _SAFE_DIR_RE.match(target_dir):
                details.append(f"{label}: 路径不安全，跳过")
                continue
            target_lower = target_dir.lower()
            if any(d in target_lower for d in _PROTECTED_DIRS):
                details.append(f"{label}: 受保护路径，跳过")
                continue

            size_result = await _asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-Command",
                f'$dir = {powershell_escape(target_dir)}; '
                f'if (Test-Path $dir) {{ '
                f'$size = (Get-ChildItem $dir -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum; '
                f'$count = (Get-ChildItem $dir -Recurse -Force -ErrorAction SilentlyContinue).Count; '
                f'Write-Output "$size|$count" '
                f'}} else {{ Write-Output "0|0" }}',
                stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE,
            )
            await size_result.wait()

            del_result = await _asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-Command",
                f'$dir = {powershell_escape(target_dir)}; '
                f'if (Test-Path $dir) {{ '
                f'Get-ChildItem $dir -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue '
                f'}}',
                stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE,
            )
            await del_result.wait()

            size_stdout = await size_result.stdout.read()
            size_bytes = 0
            file_count = 0
            try:
                size_text = size_stdout.decode("utf-8", errors="replace").strip()
                if "|" in size_text:
                    parts = size_text.split("|")
                    size_bytes = int(float(parts[0])) if parts[0].strip() else 0
                    file_count = int(float(parts[1])) if parts[1].strip() else 0
            except (ValueError, IndexError):
                pass

            if size_bytes > _MAX_CLEANUP_BYTES:
                details.append(f"{label}: 目录过大({round(size_bytes/1024/1024/1024, 1)}GB)，跳过安全限制")
                continue

            if file_count == 0 and size_bytes == 0:
                details.append(f"{label}: 已是干净")
                continue

            freed_mb = round(size_bytes / 1024 / 1024, 1)
            total_freed += freed_mb
            total_deleted += file_count
            details.append(f"{label}: 清理{file_count}个文件, 释放{freed_mb}MB")
            await _emit_step(send_func, "cleanup_pc", "running",
                             f"{label}: 清理{file_count}个文件, 释放{freed_mb}MB")

        except Exception as e:
            details.append(f"{label}: 跳过({_safe_error(e)})")

    if level in ("deep", "full"):
        try:
            await _emit_step(send_func, "cleanup_pc", "running", "正在清空回收站...")
            proc = await _asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-Command",
                "Clear-RecycleBin -Force -ErrorAction SilentlyContinue",
                stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE,
            )
            await proc.wait()
            details.append("回收站: 已清空")
        except Exception:
            pass

    if level == "full":
        try:
            await _emit_step(send_func, "cleanup_pc", "running", "正在磁盘清理...")
            proc = await _asyncio.create_subprocess_exec(
                "cleanmgr", "/sagerun:1",
                stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE,
            )
            await proc.wait()
            details.append("磁盘清理: 已启动")
        except Exception:
            pass

    summary = f"清理完成！共清理{total_deleted}个文件，释放约{total_freed}MB空间"
    await send_func("cleanup_result", {
        "level": level,
        "total_freed_mb": total_freed,
        "total_files": total_deleted,
        "details": details,
    })
    await _emit_step(send_func, "cleanup_pc", "done", summary)
    await send_reply(f"电脑清理好啦！{summary} 🥔✨", "happy", send_func)


async def handle_get_memory(payload: dict, send_func):
    try:
        keyword = payload.get("keyword", "")
        if keyword:
            memories = brain.memory.search_memories(keyword)
            categorized = []
            for m in memories:
                cat = m.get("category", "")
                cat_name = m.get("category_name", cat)
                m["category_display"] = cat_name
                categorized.append(m)
            await send_func("memory_search", {"keyword": keyword, "results": categorized})
        else:
            facts = brain.memory.get_all_facts()
            facts_by_cat = {}
            for k, v in brain.memory.facts.items():
                if isinstance(v, dict):
                    cat = v.get("category", "other")
                    val = v.get("value", "")
                else:
                    cat = "other"
                    val = str(v)
                if cat not in facts_by_cat:
                    facts_by_cat[cat] = {}
                facts_by_cat[cat][k] = val
            hot = brain.memory.get_hot_memories(limit=10)
            summaries = brain.memory.get_recent_summaries(limit=3)
            await send_func("memory_overview", {
                "facts": facts,
                "facts_by_category": facts_by_cat,
                "hot_count": len(hot),
                "summaries_count": len(summaries),
                "categories": list(brain.memory.facts.keys()) if hasattr(brain.memory, 'facts') else [],
            })
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def _refresh_config_for_key(key_upper: str, value: str):
    """Refresh runtime Config + provider client caches after a key is stored."""
    from services import _reset_main_client, _reset_audio_client
    if key_upper == "DEEPSEEK_API_KEY":
        Config.LLM_API_KEY = value
        _reset_main_client()
    elif key_upper == "SILICON_API_KEY":
        Config.SILICON_KEY = value
        _reset_audio_client()
        _reset_main_client()
    elif key_upper == "LINER_API_KEY":
        Config.LINER_KEY = value
        _reset_main_client()
    elif key_upper == "OPENAI_API_KEY":
        Config.OPENAI_KEY = value
        _reset_main_client()
    elif key_upper in ("BYTEBOT_AGENT_URL", "BYTEBOT_DESKTOP_URL"):
        try:
            from bytebot_client import _bytebot_client
            _bytebot_client.agent_url = None
            _bytebot_client.desktop_url = None
        except Exception:
            pass


async def handle_vault_store(payload: dict, send_func):
    """Store a key in the vault and refresh runtime config."""
    try:
        from potato.vault import Vault
        vault = Vault()
        key = payload.get("key", "")
        value = payload.get("value", "")
        if not key or not value:
            await send_func("error", {"info": "需要 key 和 value"})
            return
        key_upper = key.strip().upper()
        if any(c in key_upper for c in (';', '|', '`', '\n', '\r', '/', '\\', '..')):
            await send_func("error", {"info": "密钥名含非法字符"})
            return
        is_url = value.strip().startswith("http")
        from potato.vault import KNOWN_KEYS as _KNS
        key_desc = _KNS.get(key_upper, {}).get("desc", key_upper)
        if is_url and "DEEPSEEK" in key_upper:
            await send_func("error", {"info": f"这是网址不是密钥哦~ 请在 {value.strip()} 生成真正的 API Key（以 sk- 开头），再粘贴给我就行！🥔"})
            return
        result = vault.store(
            key=key_upper, value=value,
            category=payload.get("category", ""),
            platform_id=payload.get("platform_id", ""),
            description=payload.get("description", ""),
        )
        await _refresh_config_for_key(key_upper, value)
        await send_func("vault_stored", result)
        vault_status = vault.status()
        missing = [m["desc"] for m in vault_status.get("missing_required", [])]
        if missing:
            await send_reply(f"{key_desc} 存好了！还缺：{'、'.join(missing)}~ 🥔", "happy", send_func)
        else:
            await send_reply(f"{key_desc} 存好了！所有核心密钥齐全，可以开始用了~ 🥔", "happy", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_vault_list(payload: dict, send_func):
    try:
        from potato.vault import Vault
        keys = Vault().list_keys(payload.get("category", ""))
        await send_func("vault_keys", {"keys": keys, "count": len(keys)})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_vault_delete(payload: dict, send_func):
    try:
        from potato.vault import Vault
        Vault().delete(payload.get("key", ""))
        await send_func("vault_deleted", {"key": payload.get("key", "")})
        await send_reply(f"密钥已从保险箱删除~ 🥔", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_vault_status(send_func):
    try:
        from potato.vault import Vault
        vault = Vault()
        status = vault.status()
        await send_func("vault_status", status)
        total = status["total_keys"]
        missing = status["missing_required"]
        if missing:
            names = ", ".join(m["desc"] for m in missing[:3])
            await send_reply(f"保险箱有 {total} 个密钥。还缺: {names}~ 给我就能用了！🥔", "neutral", send_func)
        else:
            await send_reply(f"保险箱有 {total} 个密钥，核心密钥齐全！🥔", "happy", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_open_renewal_url(payload: dict, send_func):
    """Open a provider's renewal/dashboard URL in the user's browser."""
    try:
        key_name = payload.get("key", "").strip().upper()
        from potato.vault import KNOWN_KEYS
        key_meta = KNOWN_KEYS.get(key_name, {})
        renewal_url = key_meta.get("renewal_url") or key_meta.get("dashboard_url", "")
        if not renewal_url:
            dashboard_url = key_meta.get("dashboard_url", "")
            if dashboard_url:
                renewal_url = dashboard_url
        if not renewal_url:
            await send_reply(f"找不到 {key_name} 的续费链接，请手动到对应平台续费~ 🥔", "neutral", send_func)
            return
        import webbrowser
        webbrowser.open(renewal_url)
        desc = key_meta.get("desc", key_name)
        await send_func("renewal_opened", {"key": key_name, "url": renewal_url})
        await send_reply(f"已帮你打开 {desc} 的续费页面！按提示充值就行~ 🥔", "happy", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_credential_grant(payload: dict, send_func):
    """Store platform credentials → switch to autonomous mode."""
    try:
        from potato.credentials import CredentialsPlugin
        from potato.config import load_settings
        platform_id = payload.get("platform_id", "")
        credentials = payload.get("credentials", {})
        if not platform_id or not credentials:
            await send_func("error", {"info": "需要 platform_id 和 credentials"})
            return
        plugin = CredentialsPlugin(load_settings())
        result = plugin.grant(platform_id, credentials)
        await send_func("credential_granted", result)
        await send_reply(
            f"已收到你的 {platform_id} 凭证！以后我可以自动登录帮你操盘了~ 🥔",
            "happy", send_func,
        )
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_credential_revoke(payload: dict, send_func):
    """Remove platform credentials → switch back to assisted mode."""
    try:
        from potato.credentials import CredentialsPlugin
        from potato.config import load_settings
        platform_id = payload.get("platform_id", "")
        if not platform_id:
            await send_func("error", {"info": "需要 platform_id"})
            return
        plugin = CredentialsPlugin(load_settings())
        result = plugin.revoke(platform_id)
        await send_func("credential_revoked", result)
        await send_reply(
            f"已收回 {platform_id} 的自动登录权限，下次需要你手动登录~ 🥔",
            "neutral", send_func,
        )
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_credential_status(send_func):
    """Show which platforms are in autonomous vs assisted mode."""
    try:
        from potato.credentials import CredentialsPlugin
        from potato.config import load_settings
        plugin = CredentialsPlugin(load_settings())
        status = plugin.permission_status()
        await send_func("credential_status", {"platforms": status})
        if not status:
            await send_reply("还没有给任何平台授权哦~ 给我账号密码我就能自动登录操盘！🥔", "neutral", send_func)
        else:
            auto = [pid for pid, s in status.items() if s["mode"] == "autonomous"]
            assisted = [pid for pid, s in status.items() if s["mode"] == "assisted"]
            msg = ""
            if auto:
                msg += f"自主操盘: {', '.join(auto)}（已给凭证）"
            if assisted:
                msg += f"  需要登录: {', '.join(assisted)}"
            await send_reply(msg, "happy", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_credential_schemas(send_func):
    """Show what fields each platform needs for credentials."""
    try:
        from potato.credentials import CredentialsPlugin
        schemas = CredentialsPlugin.all_field_schemas()
        await send_func("credential_schemas", {"platforms": schemas})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


_voice_call_session = None
_current_voice_profile = "yujie"


async def handle_voice_call_start(payload: dict, send_func):
    """Start a real-time voice conversation session."""
    global _voice_call_session
    try:
        from potato.voice import VoiceCallSession
        profile = payload.get("voice_profile", _current_voice_profile)
        _voice_call_session = VoiceCallSession(profile_id=profile)
        result = await _voice_call_session.start()
        await send_func("voice_call_started", result)
        await send_reply("语音通话已开启，说吧~", "happy", send_func)
    except Exception as e:
        await send_func("error", {"info": f"Voice call start failed: {e}"})


async def handle_voice_call_audio(payload: dict, send_func):
    """Process one audio turn in voice call: STT → AI → TTS."""
    global _voice_call_session
    if not _voice_call_session or not _voice_call_session.is_active:
        await send_func("error", {"info": "No active voice call"})
        return

    audio_b64 = payload.get("audio_base64", "")
    if not audio_b64:
        return
    if len(audio_b64) > 5_000_000:
        await send_func("error", {"info": "语音文件过大，请缩短录音"})
        return

    brain.state = "thinking"
    await send_func("state_update", {"state": "thinking"})

    try:
        turn = await _voice_call_session.process_audio_turn(audio_b64)
        user_text = turn.get("user_text", "")

        if not user_text:
            brain.state = "idle"
            await send_func("state_update", {"state": "idle"})
            return

        await send_func("voice_stt_result", {"text": user_text})
        await handle_user_input(user_text, send_func)

    except Exception as e:
        await send_reply(f"语音处理出错: {e}", "neutral", send_func)
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})


async def handle_voice_call_end(send_func):
    global _voice_call_session
    try:
        if _voice_call_session:
            result = await _voice_call_session.end()
            _voice_call_session = None
            await send_func("voice_call_ended", result)
            await send_reply("语音通话结束了~", "neutral", send_func)
        else:
            await send_func("voice_call_ended", {"ok": True, "turns": 0})
    except Exception as e:
        logger.warning("voice_call_end error: %s", e)
        _voice_call_session = None
        await send_func("error", {"info": f"语音通话结束失败: {_safe_error(e)}"})


async def handle_set_voice(payload: dict, send_func):
    global _current_voice_profile
    try:
        from potato.voice import VOICE_PROFILES, get_voice_profile
        profile_id = payload.get("profile_id", "yujie")
        if profile_id in VOICE_PROFILES:
            _current_voice_profile = profile_id
            profile = get_voice_profile(profile_id)
            await send_func("voice_changed", {"profile_id": profile_id, "name": profile["name"]})
            await send_reply(f"声音已切换到「{profile['name']}」模式~ {profile['description']}", "happy", send_func)
        else:
            available = list(VOICE_PROFILES.keys())
            await send_func("error", {"info": f"Unknown voice: {profile_id}", "available": available})
    except ImportError:
        await send_func("error", {"info": "语音模块未安装，无法切换声音"})
    except Exception as e:
        logger.warning("set_voice error: %s", e)
        await send_func("error", {"info": f"切换声音失败: {_safe_error(e)}"})


async def handle_list_voices(send_func):
    try:
        from potato.voice import VOICE_PROFILES
        voices = {k: {"name": v["name"], "description": v["description"]} for k, v in VOICE_PROFILES.items()}
        await send_func("voice_list", {"voices": voices, "current": _current_voice_profile})
    except ImportError:
        await send_func("voice_list", {"voices": {}, "current": _current_voice_profile})
    except Exception as e:
        logger.warning("list_voices error: %s", e)
        await send_func("voice_list", {"voices": {}, "current": _current_voice_profile})


async def handle_bytebot_task(payload: dict, send_func):
    """Create a Bytebot task and poll until completion."""
    description = payload.get("description", "")
    if not description:
        await send_func("error", {"info": "需要指定任务描述"})
        return

    _MAX_TASK_DESC_LEN = 500
    if len(description) > _MAX_TASK_DESC_LEN:
        description = description[:_MAX_TASK_DESC_LEN]
        await send_func("state_update", {"state": "thinking"})

    await send_func("state_update", {"state": "thinking"})
    await send_reply(f"正在创建 Bytebot 任务: {description[:80]}...", "happy", send_func)

    try:
        client = get_bytebot_client()

        if not await client.is_available():
            await send_reply("Bytebot 服务不可用，请确认 Docker 已启动（端口 9991）— 可在保险箱配置 BYTEBOT_AGENT_URL 🥔", "neutral", send_func)
            brain.state = "idle"
            await send_func("state_update", {"state": "idle"})
            return

        model = payload.get("model")
        priority = payload.get("priority", "MEDIUM")
        task = await client.create_task(description, priority=priority, model=model)

        task_id = task.get("id")
        if not task_id:
            await send_reply(f"创建任务失败: {task.get('error', '未知错误')} 🥔", "neutral", send_func)
            brain.state = "idle"
            await send_func("state_update", {"state": "idle"})
            return

        await send_func("bytebot_task_created", {
            "task_id": task_id, "description": description, "status": task.get("status", "PENDING"),
        })
        await send_reply(f"Bytebot 任务已创建 (ID: {task_id[:8]}...), 正在执行...", "happy", send_func)

        from bytebot_client import poll_task_until_done
        result_task = await poll_task_until_done(task_id, send_func)

        if result_task:
            status = result_task.get("status")
            if status == "COMPLETED":
                result_data = result_task.get("result", {})
                summary = ""
                if isinstance(result_data, dict):
                    summary = result_data.get("summary", result_data.get("description", ""))
                elif isinstance(result_data, str):
                    summary = result_data[:200]
                await send_reply(f"Bytebot 任务完成！{summary if summary else '✅'} 🥔", "happy", send_func)
            elif status == "FAILED":
                error = result_task.get("error", "未知错误")
                await send_reply(f"Bytebot 任务失败了: {error} 🥔", "neutral", send_func)
            else:
                await send_reply(f"Bytebot 任务状态: {status}", "neutral", send_func)
        else:
            await send_reply("Bytebot 任务超时，可能仍在后台运行 🥔", "neutral", send_func)

    except Exception as e:
        logger.warning("Bytebot task error: %s", e)
        await send_reply(f"Bytebot 出错: {e}", "angry", send_func)
    finally:
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})


async def handle_bytebot_status(send_func):
    """Check Bytebot service availability and recent tasks."""
    try:
        client = get_bytebot_client()
        agent_ok = await client.is_available()
        desktop_ok = await client.is_desktop_available()

        tasks = []
        if agent_ok:
            try:
                session = await client._get_session()
                async with session.get(f"{client.agent_url}/tasks", params={"limit": 5}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tasks = data.get("tasks", [])
            except Exception:
                logger.warning("Failed to query recent tasks")

        await send_func("bytebot_status", {
            "agent_available": agent_ok,
            "desktop_available": desktop_ok,
            "recent_tasks": [
                {"id": t.get("id", ""), "description": t.get("description", "")[:80],
                 "status": t.get("status", ""), "created_at": t.get("createdAt", "")}
                for t in tasks
            ],
        })

        if not agent_ok:
            await send_reply("Bytebot Agent 未运行，正在自动启动... 🥔", "neutral", send_func)
            try:
                import subprocess as _sp
                agent_script = Path(__file__).resolve().parent / "bytebot_agent.py"
                if agent_script.exists():
                    _sp.Popen(
                        [sys.executable, str(agent_script)],
                        env={**os.environ, "BYTEBOT_AGENT_PORT": "9991"},
                        stdout=_sp.PIPE, stderr=_sp.PIPE,
                    )
                    await asyncio.sleep(2)
                    agent_ok = await client.is_available()
            except Exception as e:
                logger.warning("Auto-start agent failed: %s", e)

        await send_func("bytebot_status", {
            "agent_available": agent_ok,
            "desktop_available": desktop_ok,
            "recent_tasks": [],
        })

        if not agent_ok:
            pass
        else:
            status_parts = [f"Agent ✅"]
            if desktop_ok:
                status_parts.append("Desktop ✅")
            else:
                status_parts.append("Desktop ❌")
            await send_reply(f"Bytebot 状态: {'  '.join(status_parts)}", "happy", send_func)

    except Exception as e:
        await send_func("bytebot_status", {"agent_available": False, "desktop_available": False, "error": str(e)})
        await send_reply(f"Bytebot 状态检查失败: {e}", "neutral", send_func)


async def handle_bytebot_desktop(payload: dict, send_func):
    """Send a direct computer-use command to Bytebot desktop daemon, with validation."""
    _SAFE_DESKTOP_ACTIONS = {"screenshot", "cursor_position", "click_mouse", "type_text",
                               "paste_text", "scroll", "move_mouse", "application", "wait"}
    _DANGEROUS_DESKTOP_ACTIONS = {"write_file", "read_file", "press_keys"}
    _MAX_PARAM_LEN = 1000
    _ALLOWED_DESKTOP_PARAMS = {"action", "text", "path", "x", "y", "dx", "dy", "button", "keys", "key", "duration", "name", "wait"}

    action = str(payload.get("action", "")).strip()
    if not action:
        await send_func("error", {"info": "需要指定 action (screenshot, click_mouse, type_text, ...)"})
        return

    if action in _DANGEROUS_DESKTOP_ACTIONS:
        await send_func("error", {"info": f"操作 {action} 需要用户明确确认，请通过聊天请求"})
        logger.warning("Blocked dangerous desktop action from WS: %s", action)
        return

    if action not in _SAFE_DESKTOP_ACTIONS and action not in _DANGEROUS_DESKTOP_ACTIONS:
        await send_func("error", {"info": f"不支持的操作: {action}"})
        logger.warning("Unknown desktop action: %s", action)
        return

    await send_func("state_update", {"state": "thinking"})
    try:
        client = get_bytebot_client()

        if not await client.is_desktop_available():
            await send_reply("Bytebot Desktop 不在运行，请先启动: docker compose -f docker/docker-compose.pet.yml up -d 🥔", "neutral", send_func)
            brain.state = "idle"
            await send_func("state_update", {"state": "idle"})
            return

        params = {}
        for k, v in payload.items():
            if k == "action" or v is None or k not in _ALLOWED_DESKTOP_PARAMS:
                continue
            if isinstance(v, str) and len(v) > _MAX_PARAM_LEN:
                v = v[:_MAX_PARAM_LEN]
            params[k] = v
        result = await client.computer_use(action, **params)

        if action == "screenshot" and result.get("image"):
            await send_func("bytebot_screenshot", {"screenshot_b64": result["image"]})

        await send_func("bytebot_desktop_result", {"action": action, "result": result})

        if result.get("ok") is False:
            await send_reply(f"操作失败: {result.get('error', '未知')} 🥔", "neutral", send_func)
        elif action == "screenshot":
            await send_reply("截图已获取！正在分析...", "happy", send_func)
        else:
            await send_reply(f"{action} 操作完成 ✅", "happy", send_func)

    except Exception as e:
        await send_reply(f"Desktop 操作出错: {e}", "neutral", send_func)
    finally:
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})


async def handle_bytebot_cancel(payload: dict, send_func):
    """Cancel a running Bytebot task."""
    task_id = payload.get("task_id", "")
    if not task_id:
        await send_func("error", {"info": "需要指定 task_id"})
        return
    try:
        client = get_bytebot_client()
        result = await client.cancel_task(task_id)
        if result:
            await send_func("bytebot_task_cancelled", {"task_id": task_id, "status": result.get("status")})
            await send_reply(f"Bytebot 任务 {task_id[:8]}... 已取消", "neutral", send_func)
        else:
            await send_reply(f"取消任务失败（可能已完成或不存在）🥔", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_bytebot_message(payload: dict, send_func):
    """Send a guidance message to a running Bytebot task."""
    task_id = payload.get("task_id", "")
    message = payload.get("message", "")
    if not task_id or not message:
        await send_func("error", {"info": "需要 task_id 和 message"})
        return
    try:
        client = get_bytebot_client()
        result = await client.add_message(task_id, message)
        if result:
            await send_reply(f"已向 Bytebot 任务发送指导~ 🥔", "happy", send_func)
        else:
            await send_reply("发送失败，任务可能已结束~", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_trade_analysis(payload: dict, send_func):
    global _trading_scheduler
    if not _trading_scheduler:
        _trading_scheduler = TradingScheduler(send_func, broker=_get_broker())
    symbols = payload.get("symbols", [])
    if not symbols:
        from potato.user_prefs import UserPrefs
        prefs = UserPrefs()
        symbols = prefs.get("watchlist", [])[:5]
    if not symbols:
        symbols = ["000001", "600519", "000858", "601318", "000333"]
    try:
        brain.state = "thinking"
        await send_func("state_update", {"state": "thinking"})
        user_prefs = {}
        try:
            from potato.user_prefs import UserPrefs
            up = UserPrefs()
            user_prefs = {"risk_level": up.get("risk_level", ""), "watchlist": up.get("watchlist", []), "sectors": up.get("sectors", [])}
        except Exception:
            pass
        result = await _trading_scheduler.run_manual_analysis(
            symbols=symbols,
            user_prefs=user_prefs,
        )
        if result.get("ok"):
            analysis = result.get("analysis", {})
            picks = analysis.get("stock_picks", [])
            formatted = format_trade_decision_for_pet(result)
            await send_func("trade_analysis", {
                "analysis": analysis,
                "formatted": formatted,
                "symbols": symbols,
            })
            for pick in picks:
                if pick.get("action") in ("BUY", "SELL"):
                    signal = format_trade_signal_message(pick)
                    if signal:
                        await send_func("trade_signal", {
                            "symbol": pick.get("symbol", ""),
                            "name": pick.get("name", ""),
                            "action": pick.get("action", ""),
                            "confidence": pick.get("confidence", 0),
                            "message": signal,
                        })
        else:
            await send_func("error", {"info": f"分析失败: {result.get('error', '')}"})
    except Exception as e:
        logger.warning("Trade analysis error: %s", e)
        await send_func("error", {"info": _safe_error(e)})
    finally:
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})


async def handle_trade_execute(payload: dict, send_func):
    global _trading_scheduler
    if not _trading_scheduler:
        _trading_scheduler = TradingScheduler(send_func, broker=_get_broker())
    pick = payload.get("pick", {})
    if not pick:
        await send_func("error", {"info": "需要交易信息(pick)"})
        return
    try:
        brain.state = "thinking"
        await send_func("state_update", {"state": "thinking"})
        user_prefs = {}
        try:
            from potato.user_prefs import UserPrefs
            up = UserPrefs()
            user_prefs = {
                "risk_level": up.get("risk_level", ""),
                "max_single_cny": up.get("max_single_trade_cny", "50"),
                "platform_id": payload.get("platform_id", "eastmoney"),
            }
        except Exception:
            pass
        result = await _trading_scheduler.execute_trade_decision(pick, user_prefs)
        await send_func("trade_result", result)
        if result.get("ok"):
            await send_reply(f"交易已提交！{result.get('action','')} {result.get('symbol','')} 🥔", "happy", send_func)
        else:
            await send_reply(f"交易被拦截: {result.get('reason', '')} 🥔", "neutral", send_func)
    except Exception as e:
        logger.warning("Trade execute error: %s", e)
        await send_func("error", {"info": _safe_error(e)})
    finally:
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})


async def handle_trade_auto_start(payload: dict, send_func):
    global _trading_scheduler
    try:
        if _trading_scheduler and _trading_scheduler._running:
            _trading_scheduler.send_func = send_func
            await send_func("trade_auto_status", {"running": True, "status": _trading_scheduler.get_status()})
            return
        _trading_scheduler = TradingScheduler(send_func, broker=_get_broker())
        _trading_scheduler.start()
        await send_func("trade_auto_status", {"running": True, "status": _trading_scheduler.get_status()})
        await send_reply("自动操盘已启动！我会按盘前→开盘→午间→尾盘→盘后流程自动运转 🥔📈", "happy", send_func)
    except Exception as e:
        logger.warning("trade_auto_start error: %s", e)
        await send_func("error", {"info": f"启动自动操盘失败: {_safe_error(e)}"})


async def handle_trade_auto_stop(send_func):
    global _trading_scheduler
    try:
        if _trading_scheduler:
            _trading_scheduler.stop()
        await send_func("trade_auto_status", {"running": False})
        await send_reply("自动操盘已停止 🥔", "neutral", send_func)
    except Exception as e:
        logger.warning("trade_auto_stop error: %s", e)
        await send_func("error", {"info": f"停止操盘失败: {_safe_error(e)}"})


async def handle_trade_status(send_func):
    global _trading_scheduler
    try:
        if _trading_scheduler:
            await send_func("trade_auto_status", _trading_scheduler.get_status())
        else:
            await send_func("trade_auto_status", {"running": False, "trades_today": 0, "total_trades": 0})
    except Exception as e:
        logger.warning("trade_status error: %s", e)
        await send_func("trade_auto_status", {"running": False, "error": _safe_error(e)})


_journal = TradeJournal()


async def handle_trade_review(payload: dict, send_func):
    try:
        date_str = payload.get("date") if isinstance(payload, dict) else None
        review = _journal.generate_daily_review(date_str)
        trades = _journal.get_recent_trades(20)
        trade_lines = []
        for t in trades:
            icon = "✅" if t.realized_pnl > 0 else ("❌" if t.realized_pnl < 0 else "➖")
            trade_lines.append(
                f"{icon} {t.symbol} {t.name} {t.direction} "
                f"¥{t.entry_price}→¥{t.exit_price} P&L=¥{t.realized_pnl}({t.realized_pnl_pct:.1f}%) "
                f"置信度{float(t.confidence):.0%} 持仓{t.hold_duration_minutes}分钟"
            )
        summary = (
            f"📊 复盘: {review.total_trades}笔 "
            f"胜率{review.win_rate}% "
            f"盈亏¥{review.total_pnl} "
            f"利润因子{review.profit_factor} "
            f"最大回撤{review.max_drawdown_pct}%\n"
        )
        if trade_lines:
            summary += "逐笔:\n" + "\n".join(trade_lines[:10])
        for lesson in review.ai_lessons:
            summary += f"\n💡 {lesson}"

        await send_func("trade_review", {
            "date": review.date,
            "total_trades": review.total_trades,
            "winning": review.winning_trades,
            "losing": review.losing_trades,
            "win_rate": str(review.win_rate),
            "total_pnl": str(review.total_pnl),
            "profit_factor": str(review.profit_factor),
            "max_drawdown_pct": str(review.max_drawdown_pct),
            "lessons": review.ai_lessons,
            "trades": [t.to_dict() for t in trades[:20]],
            "summary": summary,
        })
    except Exception as e:
        logger.error("trade_review error: %s", e)
        await send_func("error", {"info": f"复盘失败: {e}"})


async def handle_position_status(payload: dict, send_func):
    try:
        positions = _journal.get_open_positions_summary()
        summary = f"📈 当前持仓{len(positions)}只"
        for p in positions:
            summary += f"\n  {p['name']}({p['symbol']}) {p['direction']} 入场¥{p['entry_price']} 目标¥{p['target_price']} 止损¥{p['stop_loss_price']}"
        await send_func("position_status", {
            "positions": positions,
            "count": len(positions),
            "summary": summary,
        })
    except Exception as e:
        logger.error("position_status error: %s", e)
        await send_func("error", {"info": f"持仓查询失败: {e}"})


async def handle_close_position(payload: dict, send_func):
    try:
        trade_id = payload.get("trade_id", "") if isinstance(payload, dict) else ""
        exit_price_str = payload.get("exit_price", "0") if isinstance(payload, dict) else "0"
        exit_reason = payload.get("reason", "manual") if isinstance(payload, dict) else "manual"
        if not trade_id:
            await send_func("error", {"info": "平仓需要trade_id"})
            return
        from decimal import Decimal
        exit_price = Decimal(str(exit_price_str)) if exit_price_str else Decimal("0")
        if exit_price <= 0:
            try:
                from potato.trading.analyzer import fetch_realtime_quote as _frq
                symbol = trade_id.split("_")[0]
                quote = await _frq(symbol)
                if quote and quote.get("price"):
                    exit_price = Decimal(str(quote["price"]))
            except Exception:
                pass
        rec = _journal.record_exit(trade_id, exit_price, exit_reason)
        if rec:
            icon = "✅赚" if rec.realized_pnl > 0 else "❌亏"
            summary = (
                f"{icon} 平仓 {rec.name}({rec.symbol}) "
                f"¥{rec.entry_price}→¥{rec.exit_price} "
                f"P&L=¥{rec.realized_pnl}({rec.realized_pnl_pct:.1f}%) "
                f"持仓{rec.hold_duration_minutes}分钟"
            )
            await send_func("close_position", {
                "trade_id": rec.id,
                "symbol": rec.symbol,
                "name": rec.name,
                "entry_price": str(rec.entry_price),
                "exit_price": str(rec.exit_price),
                "realized_pnl": str(rec.realized_pnl),
                "realized_pnl_pct": str(rec.realized_pnl_pct),
                "hold_duration_minutes": rec.hold_duration_minutes,
                "exit_reason": rec.exit_reason,
                "prediction_correct": rec.prediction_correct,
                "stop_hit": rec.stop_hit,
                "target_hit": rec.target_hit,
                "summary": summary,
            })
        else:
            await send_func("error", {"info": f"未找到持仓{trade_id}"})
    except Exception as e:
        logger.error("close_position error: %s", e)
        await send_func("error", {"info": f"平仓失败: {e}"})


async def handle_review_history(payload: dict, send_func):
    try:
        days = int(payload.get("days", 7)) if isinstance(payload, dict) else 7
        trades = _journal.get_recent_trades(n=100)
        if not trades:
            await send_func("review_history", {"trades": [], "summary": "暂无交易记录"})
            return

        total_pnl = sum(float(t.realized_pnl) for t in trades)
        wins = len([t for t in trades if t.realized_pnl > 0])
        total = len(trades)
        win_rate = round(wins / total * 100, 1) if total else 0

        summary = f"📋 近{days}天: {total}笔交易 胜率{win_rate}% 总盈亏¥{total_pnl:.2f}"

        await send_func("review_history", {
            "trades": [t.to_dict() for t in trades[:50]],
            "total_pnl": str(round(total_pnl, 2)),
            "win_rate": str(win_rate),
            "total_trades": total,
            "winning": wins,
            "consecutive_losses": _journal.get_consecutive_losses(),
            "summary": summary,
        })
    except Exception as e:
        logger.error("review_history error: %s", e)
        await send_func("error", {"info": f"历史查询失败: {e}"})


async def handle_broker_status(send_func):
    try:
        broker = _get_broker()
        health = await broker.health_check()
        balance = await broker.get_balance()
        _broker_instance = broker
        await send_func("broker_status", {
            "mode": broker.mode,
            "is_live": broker.is_live,
            "health": health,
            "balance": balance.to_dict(),
        })
    except Exception as e:
        logger.error("broker_status error: %s", e)
        await send_func("broker_status", {
            "mode": "dry_run",
            "is_live": False,
            "health": {"ok": False, "message": str(e)},
            "balance": {},
        })


async def handle_broker_switch(payload: dict, send_func):
    global _broker_instance, _trading_scheduler
    try:
        broker = _get_broker()
        target_mode = str(payload.get("mode", "dry_run")).lower()
        result = await broker.switch_mode(target_mode)
        _broker_instance = broker
        if _trading_scheduler:
            _trading_scheduler.executor = TradeExecutor(_trading_scheduler.send_func, broker=broker)
        if result.get("ok"):
            mode_cn = "实盘" if result["mode"] == "live" else "模拟"
            await send_func("broker_switch", {
                "ok": True,
                "mode": result["mode"],
                "is_live": result["is_live"],
                "message": f"交易模式已切换为 {mode_cn} 模式",
            })
            await send_reply(f"交易模式已切换为 {mode_cn} 模式 🥔", "happy" if target_mode == "dry_run" else "thinking", send_func)
        else:
            await send_func("broker_switch", {
                "ok": False,
                "mode": broker.mode,
                "message": result.get("message", "切换失败"),
            })
            await send_reply(f"切换失败: {result.get('message', '未知原因')} 🥔", "sad", send_func)
    except Exception as e:
        logger.error("broker_switch error: %s", e)
        await send_func("broker_switch", {"ok": False, "message": str(e)})


async def handle_broker_balance(send_func):
    try:
        broker = _get_broker()
        balance = await broker.get_balance()
        positions = await broker.get_positions()
        pos_summary = []
        for p in positions:
            pos_summary.append(f"{p.name}({p.symbol}) {p.quantity}股 盈亏{p.profit_pct}%")

        bal_cn = (
            f"💰 账户余额 ({'实盘' if broker.is_live else '模拟'})\n"
            f"总资产: ¥{balance.total_assets}\n"
            f"可用资金: ¥{balance.available_cash}\n"
            f"持仓市值: ¥{balance.market_value}\n"
            f"浮动盈亏: ¥{balance.profit_loss}"
        )
        if pos_summary:
            bal_cn += f"\n\n📈 持仓{len(positions)}只:\n" + "\n".join(pos_summary)

        await send_func("broker_balance", {
            "balance": balance.to_dict(),
            "positions": [p.to_dict() for p in positions],
            "is_live": broker.is_live,
            "summary": bal_cn,
        })
        await send_reply(bal_cn, "happy", send_func)
    except Exception as e:
        logger.error("broker_balance error: %s", e)
        await send_func("error", {"info": f"余额查询失败: {e}"})


async def handle_billing_dashboard(send_func):
    try:
        dashboard = _billing.get_billing_dashboard()
        await send_func("billing_dashboard", dashboard)
        summary = dashboard.get("summary_text", "")
        if summary:
            await send_reply(summary, "neutral", send_func)
    except Exception as e:
        logger.error("billing_dashboard error: %s", e)
        await send_func("error", {"info": f"计费面板加载失败: {e}"})


async def handle_billing_topup(payload: dict, send_func):
    try:
        amount = float(payload.get("amount", 0))
        method = str(payload.get("method", "manual"))
        tx_hash = str(payload.get("tx_hash", ""))
        description = str(payload.get("description", ""))

        if amount <= 0:
            await send_func("error", {"info": "充值金额必须大于0"})
            return
        if amount > 100000:
            await send_func("error", {"info": "单次充值金额不能超过10万元"})
            return

        result = _billing.add_wallet_topup(
            amount_cny=amount,
            method=method,
            description=description,
            tx_hash=tx_hash,
        )
        wallet = _billing.get_wallet_balance()
        await send_func("billing_topup", {
            "ok": True,
            "amount_cny": amount,
            "method": method,
            "wallet": wallet,
            "message": f"充值成功！¥{amount:.2f}已到账，余额¥{wallet['remaining_cny']:.2f}",
        })
        await send_reply(f"充值成功！¥{amount:.2f}已到账，当前余额¥{wallet['remaining_cny']:.2f} 🥔", "happy", send_func)
    except Exception as e:
        logger.error("billing_topup error: %s", e)
        await send_func("error", {"info": f"充值失败: {e}"})


async def handle_billing_usage(payload: dict, send_func):
    try:
        days = int(payload.get("days", 30)) if isinstance(payload, dict) else 30
        usage = _billing.get_usage_summary(days=days)
        await send_func("billing_usage", usage)

        providers_text = []
        for p in usage.get("providers", []):
            prov_name = PROVIDER_PRICING.get(p["provider"], {}).get("name", p["provider"])
            providers_text.append(f"  {prov_name}: 入{p['tokens_in']}出{p['tokens_out']} ¥{p['total_cny']:.2f}")

        summary = (
            f"📊 近{days}天使用:\n"
            f"  总输入: {usage['total_tokens_in']} tokens\n"
            f"  总输出: {usage['total_tokens_out']} tokens\n"
            f"  费用合计: ¥{usage['total_all_cny']:.2f}\n\n"
        )
        if providers_text:
            summary += "各服务商:\n" + "\n".join(providers_text)

        await send_reply(summary, "neutral", send_func)
    except Exception as e:
        logger.error("billing_usage error: %s", e)
        await send_func("error", {"info": f"用量查询失败: {e}"})


async def handle_billing_renewal_payment(payload: dict, send_func):
    """Handle renewal — auto-deduct if balance sufficient, otherwise show payment address + QR."""
    try:
        provider = ""
        if isinstance(payload, dict):
            provider = str(payload.get("billing_renewal_payment") or payload.get("provider") or "")

        payment_info = _billing.get_renewal_payment_info(provider=provider)

        if payment_info.get("balance_sufficient"):
            summary = f"✅ 续费成功！已自动从余额扣款。\n当前余额: ¥{payment_info['current_balance_cny']:.2f}"
        else:
            items_text = []
            for item in payment_info["items"]:
                items_text.append(f"  {item['name']}: ¥{item['price_cny']:.0f}/月")

            try:
                qr_b64 = _billing.generate_payment_qr(amount_cny=payment_info.get("total_renewal_cny", 0))
                payment_info["qr_code"] = qr_b64
            except Exception:
                payment_info["qr_code"] = ""

            summary = f"💳 续费支付\n\n收款地址: {payment_info['wallet_address']}\n币种: {payment_info['wallet_label']}\n\n"
            if items_text:
                summary += "待续费服务:\n" + "\n".join(items_text) + "\n"
                summary += f"\n合计: ¥{payment_info['total_renewal_cny']:.2f}\n"
            summary += f"\n当前余额: ¥{payment_info['current_balance_cny']:.2f}\n"
            summary += payment_info["payment_note"]
            if payment_info.get("qr_code"):
                summary += "\n\n📱 请扫描二维码支付"

        await send_func("billing_renewal_payment", payment_info)
        await send_reply(summary, "happy" if payment_info.get("balance_sufficient") else "neutral", send_func)
    except Exception as e:
        logger.error("billing_renewal_payment error: %s", e)
        await send_func("error", {"info": f"续费信息获取失败: {e}"})


async def handle_billing_confirm_payment(payload: dict, send_func):
    """Handle user payment confirmation — add topup and retry renewal."""
    try:
        amount = float(payload.get("billing_confirm_payment") or payload.get("amount") or 0)
        tx_hash = str(payload.get("tx_hash") or "")
        method = "crypto" if tx_hash else "manual"

        if amount <= 0:
            await send_func("error", {"info": "请指定充值金额"})
            return

        result = _billing.add_wallet_topup(amount_cny=amount, method=method, tx_hash=tx_hash)
        wallet = _billing.get_wallet_balance()
        payment_info = _billing.get_renewal_payment_info()

        if payment_info.get("balance_sufficient"):
            summary = f"✅ 付款已确认，续费成功！\n充值 ¥{amount:.2f}\n当前余额: ¥{wallet['remaining_cny']:.2f}"
        else:
            summary = f"💰 付款已记录！\n充值 ¥{amount:.2f}\n当前余额: ¥{wallet['remaining_cny']:.2f}\n待续费: ¥{payment_info['total_renewal_cny']:.2f}"
            if wallet["remaining_cny"] < payment_info["total_renewal_cny"]:
                diff = payment_info["total_renewal_cny"] - wallet["remaining_cny"]
                summary += f"\n还需充值 ¥{diff:.2f} 才能完成续费"

        await send_func("billing_confirm_payment", {
            "ok": True,
            "amount_cny": amount,
            "wallet": wallet,
            "auto_renewed": payment_info.get("balance_sufficient", False),
        })
        await send_reply(summary, "happy", send_func)
    except Exception as e:
        logger.error("billing_confirm_payment error: %s", e)
        await send_func("error", {"info": f"付款确认失败: {e}"})


async def game_loop(ws, send_func):
    """Autonomous awareness — proactive analysis and trading reminders."""
    logger.info("小土豆自主意识启动 (proactive loop)")

    while True:
        await asyncio.sleep(1)
        now = time.time()

        if (
            not brain.is_dnd_mode
            and brain.state == "idle"
            and now - brain.last_interaction > brain.current_threshold
        ):
            brain.increase_boredom_time()
            brain.state = "thinking"
            await send_func("state_update", {"state": "thinking"})
            brain.last_interaction = now

            try:
                sys_prompt = await brain.build_system_prompt()
                last_active = datetime.datetime.fromtimestamp(brain.last_user_input_time).strftime("%H:%M:%S")
                trigger = f"""(系统触发：用户静默中，最后活跃 {last_active}。
可以：1) 汇报最新分析 2) 提醒查看股票 3) 主动聊天。返回 JSON。)"""

                msgs = [sys_prompt] + brain.history + [{"role": "user", "content": trigger}]
                result_json = await AIService.chat_with_potato_brain(msgs)

                if result_json.get("quota_exhausted"):
                    from potato.vault import KNOWN_KEYS as _VK
                    providers = result_json.get("quota_providers", [])
                    renewal_info = []
                    for qi in providers:
                        pname = qi.get("provider", "")
                        rurl = qi.get("renewal_url", "")
                        key_env = ""
                        for p in PROVIDERS:
                            if p.get("name") == pname:
                                key_env = p.get("key_env", "")
                                break
                        key_meta = _VK.get(key_env, {})
                        renewal_info.append({
                            "provider": pname,
                            "renewal_url": rurl,
                            "key_env": key_env,
                            "key_desc": key_meta.get("desc", key_env),
                            "dashboard_url": key_meta.get("dashboard_url", rurl),
                        })
                    await send_func("quota_exhausted", {
                        "providers": renewal_info,
                        "message": f"你的 {', '.join(p['key_desc'] for p in renewal_info)} 额度已用完，需要续费才能继续使用哦~",
                    })
                    brain.state = "idle"
                    await send_func("state_update", {"state": "idle"})
                    await asyncio.sleep(300)
                    continue

                reply = result_json.get("reply")
                emotion = result_json.get("emotion", "neutral")

                if reply:
                    ai_time = datetime.datetime.now().strftime("[%H:%M:%S]")
                    brain.history.append({"role": "assistant", "content": f"{ai_time} {reply}"})
                    brain.history = brain.history[-12:]
                    await send_reply(reply, emotion, send_func)

            except Exception as e:
                logger.warning("Proactive speech failed: %s", e)


async def handle_plan_execute_analysis(payload: dict, send_func):
    global _trading_scheduler
    if not _trading_scheduler:
        _trading_scheduler = TradingScheduler(send_func, broker=_get_broker())
    symbols = payload.get("symbols", [])
    if not symbols:
        from potato.user_prefs import UserPrefs
        prefs = UserPrefs()
        symbols = prefs.get("watchlist", [])[:5]
    if not symbols:
        symbols = ["000001", "600519", "000858", "601318", "000333"]
    try:
        brain.state = "thinking"
        await send_func("state_update", {"state": "thinking"})
        user_prefs = {}
        try:
            from potato.user_prefs import UserPrefs
            up = UserPrefs()
            user_prefs = {"risk_level": up.get("risk_level", ""), "watchlist": up.get("watchlist", []), "sectors": up.get("sectors", [])}
        except Exception:
            pass
        result = await _trading_scheduler.run_manual_analysis(
            symbols=symbols,
            user_prefs=user_prefs,
            use_plan_execute=True,
        )
        if result.get("ok"):
            analysis = result.get("analysis", {})
            picks = analysis.get("stock_picks", [])
            formatted = format_trade_decision_for_pet(result)
            await send_func("plan_execute_analysis", {
                "analysis": analysis,
                "formatted": formatted,
                "symbols": symbols,
                "method": "plan_execute",
                "steps_completed": len(result.get("step_results", [])),
            })
            for pick in picks:
                if pick.get("action") in ("BUY", "SELL"):
                    signal = format_trade_signal_message(pick)
                    if signal:
                        await send_func("trade_signal", {
                            "symbol": pick.get("symbol", ""),
                            "name": pick.get("name", ""),
                            "action": pick.get("action", ""),
                            "confidence": pick.get("confidence", 0),
                            "message": signal,
                        })
        else:
            await send_func("error", {"info": f"多步分析失败: {result.get('error', '')}"})
    except Exception as e:
        logger.warning("PlanExecute analysis error: %s", e)
        await send_func("error", {"info": _safe_error(e)})
    finally:
        brain.state = "idle"
        await send_func("state_update", {"state": "idle"})


def _find_available_port(start=8000, max_tries=10):
    import socket
    for port in range(start, start + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start


if __name__ == "__main__":
    import socket
    import uvicorn
    preferred_port = int(os.getenv("PORT", "8000"))
    port = _find_available_port(preferred_port)
    if port != preferred_port:
        logger.warning("Port %d busy, using %d instead", preferred_port, port)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        lifespan="on",
        loop="asyncio",
        log_level="info",
        timeout_graceful_shutdown=5,
    )


# ── EastMoney Data Handlers ─────────────────────────────────────────────

_EM_KEY = os.environ.get("EM_API_KEY", "")


def _em_client() -> EastMoneyClient:
    from potato.vault import Vault
    key = _EM_KEY
    if not key:
        try:
            key = Vault().get("EM_API_KEY") or ""
        except Exception:
            pass
    return EastMoneyClient(api_key=key)


async def handle_em_financial_qa(payload: dict, send_func):
    """Ask EastMoney AI a financial question."""
    question = payload.get("question", "")
    stock_code = payload.get("stock_code", "")
    if not question:
        await send_func("error", {"info": "请提供问题"})
        return
    try:
        client = _em_client()
        answer = client.financial_qa(question, stock_code)
        if answer:
            await send_func("em_financial_qa", {"question": question, "answer": answer})
        else:
            await send_func("em_financial_qa", {"question": question, "answer": "暂无数据"})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_em_earnings_review(payload: dict, send_func):
    """Get earnings review for a stock."""
    stock_code = payload.get("stock_code", "")
    if not stock_code:
        await send_func("error", {"info": "请提供股票代码"})
        return
    try:
        client = _em_client()
        result = client.earnings_review(stock_code)
        await send_func("em_earnings_review", {"stock_code": stock_code, "content": result or "暂无数据"})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_em_industry_research(payload: dict, send_func):
    """Get industry research report."""
    industry = payload.get("industry", "")
    stock_code = payload.get("stock_code", "")
    if not industry:
        await send_func("error", {"info": "请提供行业名称"})
        return
    try:
        client = _em_client()
        result = client.industry_research(industry, stock_code)
        await send_func("em_industry_research", {"industry": industry, "content": result or "暂无数据"})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_em_tracking_report(payload: dict, send_func):
    """Get tracking report for a stock."""
    stock_code = payload.get("stock_code", "")
    if not stock_code:
        await send_func("error", {"info": "请提供股票代码"})
        return
    try:
        client = _em_client()
        result = client.tracking_report(stock_code)
        await send_func("em_tracking_report", {"stock_code": stock_code, "content": result or "暂无数据"})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_em_hotspot_discovery(payload: dict, send_func):
    """Discover market hotspots."""
    keyword = payload.get("keyword", "")
    try:
        client = _em_client()
        result = client.hotspot_discovery(keyword)
        await send_func("em_hotspot_discovery", {"keyword": keyword, "content": result or "暂无数据"})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_em_comparable_company(payload: dict, send_func):
    """Get comparable company analysis."""
    stock_code = payload.get("stock_code", "")
    if not stock_code:
        await send_func("error", {"info": "请提供股票代码"})
        return
    try:
        client = _em_client()
        result = client.comparable_company(stock_code)
        await send_func("em_comparable_company", {"stock_code": stock_code, "content": result or "暂无数据"})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_stock_changes(send_func):
    """Get real-time stock anomaly data (22 types)."""
    try:
        changes = get_stock_changes()
        await send_func("stock_changes", {"changes": changes, "count": len(changes)})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_hot_tables(payload: dict, send_func):
    """Get Dragon Tiger List (龙虎榜) data."""
    market = payload.get("market", 1)
    try:
        tables = get_hot_tables(market=market)
        await send_func("hot_tables", {"market": market, "data": tables})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_chip_distribution(payload: dict, send_func):
    """Get chip/cost distribution for a stock."""
    stock_code = payload.get("stock_code", "")
    if not stock_code:
        await send_func("error", {"info": "请提供股票代码"})
        return
    try:
        data = get_chip_distribution(stock_code)
        await send_func("chip_distribution", {"stock_code": stock_code, "data": data})
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_sentiment_analysis(payload: dict, send_func):
    """Analyze financial sentiment of text."""
    text = payload.get("text", "")
    if not text:
        await send_func("error", {"info": "请提供要分析的文本"})
        return
    try:
        result = analyze_sentiment(text)
        await send_func("sentiment_analysis", result)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_realtime_quote(payload: dict, send_func):
    """Get real-time stock quote from Sina Finance."""
    stock_code = payload.get("stock_code", "")
    if not stock_code:
        await send_func("error", {"info": "请提供股票代码"})
        return
    try:
        quote = get_realtime_quote(stock_code)
        await send_func("realtime_quote", quote)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_em_query(payload: dict, send_func):
    question = str(payload.get("question", ""))[:1000]
    if not question:
        await send_func("error", {"info": "请输入问题"})
        return
    try:
        client = _em_client()
        result = client.financial_qa(question)
        content = result if isinstance(result, str) else str(result)
        await send_func("em_financial_qa", {"question": question, "content": content or "暂无数据"})
        await send_reply(f"📊 东方财富问答: {content[:300]}", "happy", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_em_hotspot(send_func):
    try:
        client = _em_client()
        result = client.hotspot_discovery("")
        content = result if isinstance(result, str) else str(result)
        await send_func("em_hotspot_discovery", {"content": content or "暂无数据"})
        await send_reply(f"🔥 热点板块: {content[:300]}", "happy", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_em_sentiment(payload: dict, send_func):
    text = payload.get("text", "")
    if not text:
        text = "A股市场"
    try:
        result = analyze_sentiment(text)
        await send_func("sentiment_analysis", result)
        emoji = {"看涨": "🟢", "看跌": "🔴"}.get(result.get("category", ""), "⚪")
        summary = f"{emoji} 市场情绪: {result['category']} (得分 {result['score']:.1f})"
        if result.get("positive_words"):
            top_pos = [w for w, _ in result["positive_words"][:3]]
            summary += f"\n正面: {', '.join(top_pos)}"
        if result.get("negative_words"):
            top_neg = [w for w, _ in result["negative_words"][:3]]
            summary += f"\n负面: {', '.join(top_neg)}"
        await send_reply(summary, "happy" if result.get("category") == "看涨" else "angry" if result.get("category") == "看跌" else "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_realtime_quote_ai(payload: dict, send_func):
    symbol = payload.get("symbol", "")
    if not symbol:
        await send_func("error", {"info": "请提供股票代码"})
        return
    try:
        quote = get_realtime_quote(symbol)
        await send_func("realtime_quote", quote)
        if quote and quote.get("name"):
            chg = quote.get("change_pct", 0)
            emoji = "📈" if chg >= 0 else "📉"
            await send_reply(
                f"{emoji} {quote['name']}({symbol}): ¥{quote.get('price', 'N/A')} {chg:+.2f}%",
                "happy" if chg >= 0 else "angry",
                send_func,
            )
        else:
            await send_reply(f"未找到 {symbol} 的行情数据", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_stock_changes_ai(send_func):
    try:
        changes = get_stock_changes()
        await send_func("stock_changes", {"changes": changes, "count": len(changes)})
        if changes:
            top5 = changes[:5]
            lines = [f"  {c.get('name', '?')}({c.get('code', '?')}): {c.get('type', '?')}" for c in top5]
            await send_reply(f"📈 异动监控: 发现{len(changes)}只异动股\n" + "\n".join(lines), "neutral", send_func)
        else:
            await send_reply("暂无异动股票", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_hot_tables_ai(send_func):
    try:
        tables = get_hot_tables()
        await send_func("hot_tables", {"data": tables})
        if tables:
            await send_reply(f"🀄 龙虎榜: 今日{len(tables)}只个股上榜", "neutral", send_func)
        else:
            await send_reply("今日龙虎榜暂无数据", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_chip_distribution_ai(payload: dict, send_func):
    symbol = payload.get("symbol", "")
    if not symbol:
        await send_func("error", {"info": "请提供股票代码"})
        return
    try:
        data = get_chip_distribution(symbol)
        await send_func("chip_distribution", {"stock_code": symbol, "data": data})
        if data:
            await send_reply(f"📊 {symbol} 筹码分布已获取", "neutral", send_func)
        else:
            await send_reply(f"{symbol} 筹码数据暂无", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_iwencai_query(payload: dict, send_func):
    query = str(payload.get("query", ""))[:1000]
    if not query:
        await send_func("error", {"info": "请输入查询内容"})
        return
    try:
        client = IwencaiClient()
        result = await asyncio.to_thread(client.query, query)
        text = format_iwencai_to_text(result)
        await send_func("iwencai_query", {"query": query, "result": result, "text": text})
        await send_reply(f"🔍 {text[:300]}", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_iwencai_select(payload: dict, send_func):
    query = payload.get("query", "")
    if not query:
        await send_func("error", {"info": "请输入选股条件"})
        return
    try:
        client = IwencaiClient()
        result = await asyncio.to_thread(client.select_stocks, query)
        text = format_iwencai_to_text(result)
        await send_func("iwencai_select", {"query": query, "result": result, "text": text})
        await send_reply(f"🎯 {text[:300]}", "happy" if result.get("ok") else "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})


async def handle_iwencai_search(payload: dict, send_func):
    keyword = payload.get("keyword", "")
    channel = payload.get("channel", "news")
    if not keyword:
        await send_func("error", {"info": "请输入搜索关键词"})
        return
    try:
        client = IwencaiClient()
        result = await asyncio.to_thread(client.search, keyword, channel=channel)
        text = format_iwencai_to_text(result)
        await send_func("iwencai_search", {"keyword": keyword, "channel": channel, "result": result, "text": text})
        await send_reply(f"📰 {text[:300]}", "neutral", send_func)
    except Exception as e:
        await send_func("error", {"info": _safe_error(e)})
