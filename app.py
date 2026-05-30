"""Zeabur entrypoint: FastAPI + optional APScheduler trading loop."""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from potato.config import load_settings
from potato.cycle import run_cycle
from potato.db import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("potato")

_scheduler = None
_db: Database | None = None
_last_cycle: dict[str, Any] = {"status": "idle"}
_last_intel: dict[str, Any] = {"status": "idle"}
_lock = threading.Lock()
_db_lock = threading.Lock()

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


def _get_db() -> Database:
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database(load_settings())
    return _db


import hmac as _hmac

def _verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = load_settings().potato_api_key
    if not expected:
        raise HTTPException(status_code=401, detail="POTATO_API_KEY not configured — set it before deploying. See .env.example")
    if not _hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="invalid api key")


def _bootstrap_on_start() -> None:
    import os as _os
    if not _os.getenv("POTATO_API_KEY", "").strip():
        logger.warning(
            "⚠️  POTATO_API_KEY is not set! All API requests will be rejected. "
            "Set POTATO_API_KEY in your environment or .env file before deploying."
        )
    from potato.bootstrap_config import load_bootstrap_settings

    bootstrap = load_bootstrap_settings()
    from potato.bootstrap_config import validate_crdb_url

    ok_url, url_err = validate_crdb_url(bootstrap.crdb_url)
    if not ok_url:
        logger.info("CRDB 未配置 (%s)，将使用 SQLite 本地模式", url_err)

    try:
        db = Database(load_settings(use_db_secrets=False))
        db.init_schema()
        logger.info("Database schema ready (%s)", db.backend)
    except Exception as exc:
        logger.warning("DB init skipped/failed: %s", exc)

    if os.getenv("POTATO_SEED_SECRETS_ON_START", "false").lower() in {"1", "true", "yes"}:
        try:
            from potato.bootstrap_config import load_bootstrap_settings
            from potato.secret_store import SecretStore, collect_secrets_from_env

            items = collect_secrets_from_env()
            # Never seed bootstrap keys from env into DB on start (bootstrap stays in process env).
            for bootstrap_key in ("CRDB_DATABASE_URL", "CRDB_CLUSTER_ID", "CRDB_SSL_ROOT_CERT"):
                items.pop(bootstrap_key, None)
            if items:
                bootstrap = load_bootstrap_settings()
                if bootstrap.crdb_dsn:
                    store = SecretStore(bootstrap)
                    store.ensure_schema()
                    store.upsert_many(items)
                    logger.info("Secrets seeded: %s", list(items.keys()))
        except Exception as exc:
            logger.error("Secret seed failed: %s", exc, exc_info=True)

    _ensure_bot_secrets()


def _ensure_bot_secrets() -> None:
    """Ensure bot secrets in DB or env; start Telegram poller when token is available."""
    try:
        from potato.notifications import BotNotifier, ensure_bot_placeholders, is_live_secret, upsert_bot_secret

        settings = load_settings()

        if os.getenv("POTATO_AUTO_SEED_BOTS", "").lower() in {"1", "true", "yes"}:
            env_seed = {
                "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
                "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
                "FEISHU_APP_ID": os.getenv("FEISHU_APP_ID", ""),
                "FEISHU_APP_SECRET": os.getenv("FEISHU_APP_SECRET", ""),
                "FEISHU_WEBHOOK_URL": os.getenv("FEISHU_WEBHOOK_URL", ""),
                "FEISHU_RECEIVE_ID": os.getenv("FEISHU_RECEIVE_ID", ""),
                "DINGTALK_WEBHOOK_URL": os.getenv("DINGTALK_WEBHOOK_URL", ""),
                "POTATO_NOTIFY_ENABLED": "true",
                "POTATO_NOTIFY_CHANNELS": "telegram,dingtalk",
            }
            for key, val in env_seed.items():
                if val and is_live_secret(val):
                    upsert_bot_secret(key, val.strip())
            logger.info("POTATO_AUTO_SEED_BOTS upserted from env")

        try:
            from potato.secret_store import SecretStore
            from potato.bootstrap_config import load_bootstrap_settings

            bootstrap = load_bootstrap_settings()
            if bootstrap.crdb_dsn:
                store = SecretStore(bootstrap)
                store.ensure_schema()
                added = ensure_bot_placeholders(store)
                if added:
                    logger.info("Bot placeholders created: %s", added)

                secrets = store.load_all()
                token = secrets.get("TELEGRAM_BOT_TOKEN", "")
                chat_id = secrets.get("TELEGRAM_CHAT_ID", "")
                if is_live_secret(token) and not is_live_secret(chat_id):
                    discover = BotNotifier().telegram_discover_chat_id()
                    if discover.get("ok") and discover.get("chat_id"):
                        upsert_bot_secret("TELEGRAM_CHAT_ID", discover["chat_id"])
                        logger.info("Telegram chat_id discovered: %s", discover.get("chat_id"))
                        from potato.telegram_bot import get_telegram_runner

                        get_telegram_runner().send_to_chat(
                            discover["chat_id"],
                            "🥔 小土豆 Telegram 已连接！之后每轮交易循环会推送摘要。",
                        )
        except Exception as store_exc:
            logger.warning("DB-backed secrets unavailable, using env fallback: %s", store_exc, exc_info=True)

        from potato.telegram_bot import start_telegram_runner

        if is_live_secret(settings.telegram_bot_token):
            tg_start = start_telegram_runner()
            logger.info("Telegram runner started: %s", tg_start)
    except Exception as exc:
        logger.error("Bot bootstrap failed: %s", exc, exc_info=True)


def _run_cycle_job() -> None:
    global _last_cycle
    with _lock:
        try:
            result = run_cycle()
            _last_cycle = {**result, "finished_at": datetime.now(timezone.utc).isoformat()}
            logger.info("Cycle %s status=%s", result.get("run_id"), result.get("status"))
        except Exception as exc:
            _last_cycle = {
                "status": "failed",
                "error": str(exc),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
            logger.exception("Cycle failed")


def _run_intel_job() -> None:
    global _last_intel
    if os.getenv("POTATO_INTEL_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        return
    with _lock:
        try:
            from potato.intel import run_daily_intel

            push = os.getenv("POTATO_INTEL_PUSH", "true").lower() in {"1", "true", "yes"}
            result = run_daily_intel(push=push)
            _last_intel = {**result, "finished_at": datetime.now(timezone.utc).isoformat()}
            logger.info("Intel job %s: %s", result.get("run_id"), result.get("status"))
        except Exception as exc:
            _last_intel = {
                "status": "failed",
                "error": str(exc),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
            logger.exception("Intel job failed")


def _start_scheduler() -> None:
    global _scheduler
    if os.getenv("POTATO_ENABLE_SCHEDULER", "true").lower() not in {"1", "true", "yes"}:
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    minutes = int(os.getenv("POTATO_CYCLE_MINUTES", "3"))
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_run_cycle_job, IntervalTrigger(minutes=minutes), id="potato-cycle", replace_existing=True)

    if os.getenv("POTATO_INTEL_ENABLED", "true").lower() in {"1", "true", "yes"}:
        hour = int(os.getenv("POTATO_INTEL_HOUR", "8"))
        minute = int(os.getenv("POTATO_INTEL_MINUTE", "0"))
        _scheduler.add_job(
            _run_intel_job,
            CronTrigger(hour=hour, minute=minute),
            id="potato-intel-daily",
            replace_existing=True,
        )
        logger.info("Intel scheduler: daily at %02d:%02d UTC", hour, minute)

    _scheduler.start()
    logger.info("Scheduler started: cycle every %s minutes", minutes)


def _stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap_on_start()
    _start_scheduler()
    yield
    from potato.telegram_bot import stop_telegram_runner

    stop_telegram_runner()
    _stop_scheduler()


app = FastAPI(
    title="小土豆 A股操盘手",
    description="OpenClaw Pi + DeepSeek + CockroachDB",
    version="2.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


class CycleResponse(BaseModel):
    ok: bool
    result: dict[str, Any]


class BotSetupRequest(BaseModel):
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    dingtalk_webhook_url: str | None = None
    dingtalk_secret: str | None = None
    feishu_webhook_url: str | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_receive_id: str | None = None


class ActivateBotsRequest(BaseModel):
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_receive_id: str | None = None
    feishu_webhook_url: str | None = None
    dingtalk_webhook_url: str | None = None
    send_test: bool = True


class SecretUpsertRequest(BaseModel):
    key: str
    value: str


class StockSentimentRequest(BaseModel):
    text: str = ""


class IwencaiQueryRequest(BaseModel):
    question: str = ""
    page: int = 1
    limit: int = 10


class IwencaiSearchRequest(BaseModel):
    keyword: str = ""
    channel: str = "news"
    limit: int = 10


class IwencaiSelectRequest(BaseModel):
    query: str = ""
    limit: int = 20


class IwencaiFormatRequest(BaseModel):
    question: str = ""


class CredentialGrantRequest(BaseModel):
    platform_id: str
    credentials: dict[str, str]


class CredentialRevokeRequest(BaseModel):
    platform_id: str


class TelegramConnectRequest(BaseModel):
    bot_token: str
    chat_id: str | None = None
    send_test: bool = True


@app.get("/", response_class=HTMLResponse)
def root(_: None = Depends(_verify_api_key)) -> str:
    try:
        db = _get_db()
        risk = db.get_risk_state()
        positions = db.list_open_positions()
    except Exception:
        return "<html><body><h1>小土豆 A股操盘手</h1><p>数据库连接中...</p></body></html>"
    with _lock:
        last_cycle = dict(_last_cycle)
        last_intel = dict(_last_intel)
    cycle_status = last_cycle.get("status", "idle")
    cycle_time = last_cycle.get("finished_at", "—")
    intel_status = last_intel.get("status", "idle")
    intel_time = last_intel.get("finished_at", "—")
    cycle_cls = 'ok' if cycle_status == 'completed' else 'idle'
    intel_cls = 'ok' if intel_status == 'completed' else 'idle'
    risk_html = ""
    for k, v in risk.items():
        label = {"spent_cny": "今日已用(CNY)", "trade_count": "交易数", "circuit_breaker": "熔断"}.get(k, k)
        val = "是" if k == "circuit_breaker" and v else "否" if k == "circuit_breaker" else v
        risk_html += f'<tr><td>{label}</td><td>{val}</td></tr>'
    pos_html = ""
    for p in positions[:10]:
        pos_html += f'<tr><td>{p.get("symbol","?")}</td><td>{p.get("side","?")}</td><td>{p.get("qty","?")}</td><td>{p.get("entry_price","?")}</td></tr>'
    if not pos_html:
        pos_html = '<tr><td colspan="4">暂无持仓</td></tr>'
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>小土豆 A股操盘手</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#1a1a2e;color:#e0e0e0;padding:2rem}}
.card{{background:#16213e;border-radius:12px;padding:1.5rem;margin-bottom:1rem}}
h1{{color:#e94560;margin-bottom:.5rem}} h2{{color:#7ec8e3;font-size:1.1rem;margin-bottom:.5rem}}
.badge{{display:inline-block;padding:2px 10px;border-radius:99px;font-size:.8rem;font-weight:600}}
.ok{{background:#1b998b;color:#fff}} .idle{{background:#546e7a;color:#fff}} .err{{background:#e94560;color:#fff}}
table{{width:100%;border-collapse:collapse}} td,th{{padding:.4rem .6rem;text-align:left;border-bottom:1px solid #0f3460}}
th{{color:#7ec8e3}} .mono{{font-family:monospace}} .muted{{color:#546e7a;font-size:.85rem}}
</style></head><body>
<h1>&#129352; 小土豆 A股操盘手</h1>
<p class="muted">your-app.zeabur.app</p>
<div class="card"><h2>服务状态</h2>
<table><tr><td>交易模式</td><td><span class="badge ok">{settings.trading_mode}</span></td></tr>
<tr><td>调度器</td><td>{os.getenv("POTATO_ENABLE_SCHEDULER","true")}</td></tr>
<tr><td>LLM</td><td class="mono">{settings.llm_model}</td></tr></table></div>
<div class="card"><h2>上轮交易</h2>
<table><tr><td>状态</td><td><span class="badge {cycle_cls}">{cycle_status}</span></td></tr>
<tr><td>完成时间</td><td>{cycle_time}</td></tr></table></div>
<div class="card"><h2>上轮情报</h2>
<table><tr><td>状态</td><td><span class="badge {intel_cls}">{intel_status}</span></td></tr>
<tr><td>完成时间</td><td>{intel_time}</td></tr></table></div>
<div class="card"><h2>风控</h2><table>{risk_html}</table></div>
<div class="card"><h2>持仓</h2><table><tr><th>代码</th><th>方向</th><th>数量</th><th>入场价</th></tr>{pos_html}</table></div>
<p class="muted" style="margin-top:1rem">API: /health &nbsp; /api/status &nbsp; /api/credentials/status</p>
</body></html>"""


@app.get("/health")
@limiter.limit("30/minute")
def health(request: Request) -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/status")
def status(_: None = Depends(_verify_api_key)) -> dict[str, Any]:
    settings = load_settings()
    db = Database(settings)
    with _lock:
        last_cycle = dict(_last_cycle)
        last_intel = dict(_last_intel)
    return {
        "last_cycle": last_cycle,
        "last_intel": last_intel,
        "risk_state": db.get_risk_state(),
        "open_positions": db.list_open_positions(),
        "llm_model": settings.llm_model,
    }


@app.post("/api/cycle/run", response_model=CycleResponse)
@limiter.limit("6/minute")
def trigger_cycle(request: Request, _: None = Depends(_verify_api_key)) -> CycleResponse:
    _run_cycle_job()
    with _lock:
        ok = _last_cycle.get("status") == "completed"
        result = dict(_last_cycle)
    return CycleResponse(ok=ok, result=result)


@app.post("/api/intel/run")
@limiter.limit("6/minute")
def trigger_intel(request: Request, _: None = Depends(_verify_api_key)) -> dict[str, Any]:
    _run_intel_job()
    with _lock:
        return {"ok": _last_intel.get("status") == "completed", "result": dict(_last_intel)}


@app.get("/api/intel/last")
def last_intel(_: None = Depends(_verify_api_key)) -> dict[str, Any]:
    with _lock:
        return dict(_last_intel)


@app.get("/api/markets/top")
def top_markets(limit: int = 10, _: None = Depends(_verify_api_key)) -> dict[str, Any]:
    return {"markets": _get_db().top_markets(limit=limit)}


@app.post("/api/deploy/zeabur")
def deploy_zeabur(_: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.zeabur import deploy_from_settings

    settings = load_settings()
    if not settings.zeabur_api_key:
        raise HTTPException(status_code=400, detail="ZEABUR_API_KEY not configured in app_secrets or env")
    try:
        return {"ok": True, "result": deploy_from_settings(settings)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="deployment failed") from exc


@app.get("/api/bots/status")
def bots_status(_: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.notifications import BotNotifier

    return {"ok": True, "bots": BotNotifier().channel_status()}


@app.post("/api/bots/setup")
def bots_setup(body: BotSetupRequest, _: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.notifications import upsert_bot_secret

    mapping = {
        "TELEGRAM_BOT_TOKEN": body.telegram_bot_token,
        "TELEGRAM_CHAT_ID": body.telegram_chat_id,
        "DINGTALK_WEBHOOK_URL": body.dingtalk_webhook_url,
        "DINGTALK_SECRET": body.dingtalk_secret,
        "FEISHU_WEBHOOK_URL": body.feishu_webhook_url,
        "FEISHU_APP_ID": body.feishu_app_id,
        "FEISHU_APP_SECRET": body.feishu_app_secret,
        "FEISHU_RECEIVE_ID": body.feishu_receive_id,
    }
    saved = []
    for key, value in mapping.items():
        if value:
            upsert_bot_secret(key, value.strip())
            saved.append(key)
    from potato.notifications import BotNotifier

    return {"ok": True, "saved_keys": saved, "bots": BotNotifier().channel_status()}


@app.post("/api/bots/activate")
def bots_activate(body: ActivateBotsRequest | None = None, _: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.bot_activation import activate_bots
    from potato.notifications import upsert_bot_secret

    body = body or ActivateBotsRequest()
    mapping = {
        "TELEGRAM_BOT_TOKEN": body.telegram_bot_token,
        "TELEGRAM_CHAT_ID": body.telegram_chat_id,
        "FEISHU_APP_ID": body.feishu_app_id,
        "FEISHU_APP_SECRET": body.feishu_app_secret,
        "FEISHU_RECEIVE_ID": body.feishu_receive_id,
        "FEISHU_WEBHOOK_URL": body.feishu_webhook_url,
        "DINGTALK_WEBHOOK_URL": body.dingtalk_webhook_url,
    }
    saved = []
    for key, value in mapping.items():
        if value:
            upsert_bot_secret(key, value.strip())
            saved.append(key)

    result = activate_bots(send_test=body.send_test)
    result["saved_keys"] = saved
    return result


@app.post("/api/bots/telegram/connect")
def telegram_connect(body: TelegramConnectRequest, _: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.notifications import BotNotifier, upsert_bot_secret
    from potato.telegram_bot import get_telegram_runner, start_telegram_runner

    upsert_bot_secret("TELEGRAM_BOT_TOKEN", body.bot_token.strip())
    get_telegram_runner().delete_webhook()

    chat_id = (body.chat_id or "").strip()
    discover = None
    if not chat_id:
        discover = BotNotifier().telegram_discover_chat_id()
        if discover.get("ok"):
            chat_id = discover["chat_id"]
            upsert_bot_secret("TELEGRAM_CHAT_ID", chat_id)
    else:
        upsert_bot_secret("TELEGRAM_CHAT_ID", chat_id)

    me = BotNotifier().telegram_get_me()
    runner = start_telegram_runner()
    test = None
    if body.send_test and chat_id:
        test = get_telegram_runner().send_to_chat(
            chat_id, "🥔 小土豆 Telegram 机器人已连接（密钥来自 CockroachDB）"
        )
    elif body.send_test and not chat_id:
        test = {"ok": False, "error": "请先给机器人发 /start，再调用 connect"}

    return {
        "ok": bool(me.get("ok")),
        "bot": me.get("result"),
        "chat_id": chat_id or None,
        "discover": discover,
        "test_send": test,
        "runner": runner,
        "bots": BotNotifier().channel_status(),
    }


@app.post("/api/bots/telegram/discover")
def telegram_discover(_: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.notifications import BotNotifier, upsert_bot_secret

    result = BotNotifier().telegram_discover_chat_id()
    if result.get("ok") and result.get("chat_id"):
        upsert_bot_secret("TELEGRAM_CHAT_ID", result["chat_id"])
    return result


@app.get("/api/bots/telegram/diag")
def telegram_diag(_: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.notifications import BotNotifier, is_live_secret
    from potato.telegram_bot import get_telegram_runner, start_telegram_runner, telegram_runner_status

    settings = load_settings()
    runner = get_telegram_runner()
    me = BotNotifier().telegram_get_me() if is_live_secret(settings.telegram_bot_token) else {"ok": False}

    wh = {}
    if is_live_secret(settings.telegram_bot_token):
        import httpx
        from potato.notifications import mask_secret

        masked_token = mask_secret(settings.telegram_bot_token)
        wh = httpx.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getWebhookInfo",
            timeout=20.0,
        ).json()
        wh.pop("result", {}).get("url", "")

    updates = {"ok": False}
    if is_live_secret(settings.telegram_bot_token):
        import httpx

        runner.delete_webhook()
        updates = httpx.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
            params={"limit": 5},
            timeout=20.0,
        ).json()

    if is_live_secret(settings.telegram_bot_token) and not telegram_runner_status().get("poller_alive"):
        start_telegram_runner()

    return {
        "ok": True,
        "bot_username": (me.get("result") or {}).get("username"),
        "bot_link": f"https://t.me/{(me.get('result') or {}).get('username')}" if me.get("ok") else None,
        "token_configured": is_live_secret(settings.telegram_bot_token),
        "chat_id_configured": is_live_secret(settings.telegram_chat_id),
        "get_me": me,
        "webhook_info": wh,
        "recent_updates_count": len(updates.get("result") or []),
        "hint": "Telegram 搜索 @" + ((me.get("result") or {}).get("username") or "xiaotudou00bot") + " 发送 /start",
        "runner": telegram_runner_status(),
        "bots": BotNotifier().channel_status(),
    }


@app.post("/api/notify/test")
def notify_test(_: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.notifications import BotNotifier

    return BotNotifier().notify("🥔 小土豆通知测试 — Telegram / 钉钉 / 飞书（占位渠道会自动跳过）")


@app.post("/api/secrets/upsert")
def secrets_upsert(body: SecretUpsertRequest, _: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.secret_store import SECRET_KEYS, load_db_secrets
    from potato.notifications import upsert_bot_secret

    key = body.key.strip().upper()
    if key not in SECRET_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown key: {key}")
    value = body.value.strip()
    upsert_bot_secret(key, value)
    return {"ok": True, "key": key}


@app.post("/api/bots/telegram/webhook")
async def telegram_webhook(payload: dict[str, Any], x_telegram_bot_api_secret_token: str | None = Header(default=None)) -> dict[str, str]:
    """Telegram setWebhook target — validate secret_token, reply to /start."""
    from potato.telegram_bot import get_telegram_runner

    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not expected_secret or x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=403, detail="invalid webhook secret")

    msg = payload.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if chat_id is not None:
        get_telegram_runner().handle_incoming(chat_id, text)
    return {"ok": "true"}


@app.post("/api/credentials/grant")
def credential_grant(body: CredentialGrantRequest, _: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.credentials import CredentialsPlugin

    plugin = CredentialsPlugin(load_settings())
    return plugin.grant(body.platform_id, body.credentials)


@app.post("/api/credentials/revoke")
def credential_revoke(body: CredentialRevokeRequest, _: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.credentials import CredentialsPlugin

    plugin = CredentialsPlugin(load_settings())
    return plugin.revoke(body.platform_id)


@app.get("/api/credentials/status")
def credential_status(_: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.credentials import CredentialsPlugin

    plugin = CredentialsPlugin(load_settings())
    return {"ok": True, "platforms": plugin.permission_status()}


@app.get("/api/credentials/{platform_id}/schema")
def credential_schema(platform_id: str, _: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.credentials import CredentialsPlugin

    schema = CredentialsPlugin.field_schema(platform_id)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform_id}")
    return {"ok": True, "platform_id": platform_id, "fields": schema}


@app.get("/api/credentials/schemas")
def credential_schemas(_: None = Depends(_verify_api_key)) -> dict[str, Any]:
    from potato.credentials import CredentialsPlugin

    return {"ok": True, "platforms": CredentialsPlugin.all_field_schemas()}


# === Stock Data APIs ===
from potato.eastmoney import (
    get_realtime_quote, get_stock_changes, get_kline_data,
    get_hot_tables, get_chip_distribution, analyze_sentiment,
)
from potato.iwencai import IwencaiClient, format_iwencai_to_text


import re

_STOCK_CODE_RE = re.compile(r"^[0-9]{6}$")


def _validate_stock_code(code: str) -> str:
    if not _STOCK_CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Invalid stock code: must be 6 digits")
    return code


@app.get("/api/stock/quote/{code}")
@limiter.limit("30/minute")
def stock_quote(request: Request, code: str, _auth: None = Depends(_verify_api_key)) -> dict[str, Any]:
    return get_realtime_quote(_validate_stock_code(code))


@app.get("/api/stock/changes")
@limiter.limit("30/minute")
def stock_changes(request: Request, _auth: None = Depends(_verify_api_key)) -> list[dict]:
    return get_stock_changes()


@app.get("/api/stock/kline/{code}")
@limiter.limit("20/minute")
def stock_kline(request: Request, code: str, period: str = "101", start: str = "20250101", end: str = "20251231", _auth: None = Depends(_verify_api_key)) -> list[str]:
    return get_kline_data(_validate_stock_code(code), period, start, end)


@app.get("/api/stock/hot_tables")
@limiter.limit("20/minute")
def stock_hot_tables(request: Request, market: int = 1, _auth: None = Depends(_verify_api_key)) -> list[dict]:
    return get_hot_tables(market)


@app.get("/api/stock/chip/{code}")
@limiter.limit("20/minute")
def stock_chip(request: Request, code: str, _auth: None = Depends(_verify_api_key)) -> dict[str, Any]:
    return get_chip_distribution(_validate_stock_code(code))


@app.post("/api/stock/sentiment")
@limiter.limit("15/minute")
def stock_sentiment(request: Request, body: StockSentimentRequest, _auth: None = Depends(_verify_api_key)) -> dict[str, Any]:
    return analyze_sentiment(body.text)


@app.post("/api/iwencai/query")
@limiter.limit("10/minute")
def iwencai_query(request: Request, body: IwencaiQueryRequest, _auth: None = Depends(_verify_api_key)) -> dict[str, Any]:
    client = IwencaiClient()
    return client.query(body.question, body.page, body.limit)


@app.post("/api/iwencai/search")
@limiter.limit("10/minute")
def iwencai_search(request: Request, body: IwencaiSearchRequest, _auth: None = Depends(_verify_api_key)) -> dict[str, Any]:
    client = IwencaiClient()
    return client.search(body.keyword, body.channel, body.limit)


@app.post("/api/iwencai/select")
@limiter.limit("10/minute")
def iwencai_select(request: Request, body: IwencaiSelectRequest, _auth: None = Depends(_verify_api_key)) -> dict[str, Any]:
    client = IwencaiClient()
    return client.select_stocks(body.query, body.limit)


@app.post("/api/iwencai/format")
@limiter.limit("10/minute")
def iwencai_format(request: Request, body: IwencaiFormatRequest, _auth: None = Depends(_verify_api_key)) -> dict[str, Any]:
    client = IwencaiClient()
    result = client.query(body.question)
    return {"ok": True, "text": format_iwencai_to_text(result)}


@app.post("/api/stock/sentiment_full")
@limiter.limit("10/minute")
def stock_sentiment_full(request: Request, body: StockSentimentRequest, _auth: None = Depends(_verify_api_key)) -> dict[str, Any]:
    return {"ok": True, "data": analyze_sentiment(body.text)}


# === Plugin System APIs ===
from potato.plugins import call_plugin, list_plugins as _list_plugins


@app.get("/api/plugins")
def plugins_list() -> dict[str, Any]:
    plugins = _list_plugins()
    return {
        "ok": True,
        "plugins": [
            {"name": p.name, "display_name": p.display_name, "description": p.description,
             "version": p.version, "actions": p.actions, "available": p.available}
            for p in plugins
        ],
    }


@app.post("/api/plugins/{name}/{action}")
def plugin_call(name: str, action: str, body: dict[str, Any] = None) -> dict[str, Any]:
    import asyncio
    result = call_plugin(name, action, body or {})
    if asyncio.isfuture(result) or asyncio.iscoroutine(result):
        result = asyncio.get_event_loop().run_until_complete(result) if not asyncio.get_event_loop().is_running() else {"ok": False, "error": "async not supported in sync endpoint"}
    return result


@app.post("/api/plugin/analyze")
def plugin_analyze(body: dict[str, Any]) -> dict[str, Any]:
    import asyncio
    result = call_plugin("ais", "analyze", body or {})
    if asyncio.isfuture(result) or asyncio.iscoroutine(result):
        result = {"ok": False, "error": "async not supported"}
    return result


@app.post("/api/plugin/learn")
def plugin_learn(body: dict[str, Any]) -> dict[str, Any]:
    import asyncio
    result = call_plugin("ais", "learn", body or {})
    if asyncio.isfuture(result) or asyncio.iscoroutine(result):
        result = {"ok": False, "error": "async not supported"}
    return result


@app.post("/api/plugin/audit")
def plugin_audit(body: dict[str, Any]) -> dict[str, Any]:
    import asyncio
    result = call_plugin("deepaudit", "audit_snippet", body or {})
    if asyncio.isfuture(result) or asyncio.iscoroutine(result):
        result = {"ok": False, "error": "async not supported"}
    return result


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("app:app", host="127.0.0.1", port=port)
