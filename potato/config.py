from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml
from dotenv import load_dotenv

from potato.bootstrap_config import build_crdb_dsn, load_bootstrap_settings
from potato.secret_store import load_db_secrets, resolve_secret

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    chain_id: int
    tag_id: int
    trading_mode: str
    _crdb_url: str
    _crdb_ssl_root_cert: str
    github_token: str
    deepseek_api_key: str
    zeabur_api_key: str
    zeabur_project_id: str
    zeabur_service_id: str
    zeabur_environment_id: str
    github_repo: str
    max_single_cny: Decimal
    max_daily_cny: Decimal
    min_volume_24h: Decimal
    min_price: Decimal
    max_price: Decimal
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    max_open_positions: int
    default_order_size_cny: Decimal
    max_consecutive_failures: int
    llm_model: str
    potato_api_key: str
    notify_enabled: bool
    notify_channels: tuple[str, ...]
    telegram_bot_token: str
    telegram_chat_id: str
    dingtalk_webhook_url: str
    dingtalk_secret: str
    feishu_webhook_url: str
    feishu_app_id: str
    feishu_app_secret: str
    feishu_receive_id: str
    feishu_api_base: str

    @property
    def dry_run(self) -> bool:
        return self.trading_mode.lower() != "live"

    @property
    def crdb_url(self) -> str:
        return self._crdb_url

    @property
    def crdb_ssl_root_cert(self) -> str:
        return self._crdb_ssl_root_cert

    @property
    def crdb_dsn(self) -> str:
        return build_crdb_dsn(self._crdb_url, self._crdb_ssl_root_cert)


def _dec(name: str, default: str, secrets: dict[str, str] | None = None) -> Decimal:
    if secrets and name in secrets and secrets[name]:
        return Decimal(secrets[name])
    return Decimal(os.getenv(name, default))


def _load_db_secrets() -> dict[str, str]:
    return load_db_secrets()


def load_settings(*, use_db_secrets: bool = True) -> Settings:
    cfg_path = ROOT / "config" / "potato.yaml"
    cfg = {}
    if cfg_path.exists():
        with cfg_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    strat = cfg.get("strategy", {})
    risk = cfg.get("risk", {})
    oc = cfg.get("openclaw", {})

    bootstrap = load_bootstrap_settings()
    secrets: dict[str, str] = _load_db_secrets() if use_db_secrets else {}

    def s(key: str, *env_names: str, default: str = "") -> str:
        return resolve_secret(key, secrets, *env_names, default=default)

    crdb_url = bootstrap.crdb_url or s("CRDB_DATABASE_URL", "CRDB_DATABASE_URL")
    crdb_cert = bootstrap.crdb_ssl_root_cert or s(
        "CRDB_SSL_ROOT_CERT", "CRDB_SSL_ROOT_CERT", default="/data/postgresql/root.crt"
    )

    return Settings(
        chain_id=int(cfg.get("chain_id", 0)),
        tag_id=int(cfg.get("tag_id", 0)),
        trading_mode=s("POTATO_TRADING_MODE", "POTATO_TRADING_MODE", default="dry_run"),
        _crdb_url=crdb_url,
        _crdb_ssl_root_cert=crdb_cert,
        github_token=s("GITHUB_TOKEN", "GITHUB_TOKEN", "GITHUB_PAT", "GITHUB_PUSH_TOKEN"),
        deepseek_api_key=s("DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"),
        zeabur_api_key=s("ZEABUR_API_KEY", "ZEABUR_API_KEY"),
        zeabur_project_id=s("ZEABUR_PROJECT_ID", "ZEABUR_PROJECT_ID"),
        zeabur_service_id=s("ZEABUR_SERVICE_ID", "ZEABUR_SERVICE_ID"),
        zeabur_environment_id=s("ZEABUR_ENVIRONMENT_ID", "ZEABUR_ENVIRONMENT_ID"),
        github_repo=s("GITHUB_REPO", "GITHUB_REPO", default="YOUR_GITHUB_USERNAME/a-stock-desktop-pet"),
        potato_api_key=s("POTATO_API_KEY", "POTATO_API_KEY"),
        max_single_cny=_dec("POTATO_MAX_SINGLE_CNY", str(risk.get("max_single_cny", 300)), secrets),
        max_daily_cny=_dec("POTATO_MAX_DAILY_CNY", str(risk.get("max_daily_cny", 1500)), secrets),
        min_volume_24h=_dec("POTATO_MIN_VOLUME_24H", str(strat.get("min_volume_24h", 50000)), secrets),
        min_price=_dec("POTATO_MIN_PRICE", str(strat.get("min_price", 5.0)), secrets),
        max_price=_dec("POTATO_MAX_PRICE", str(strat.get("max_price", 100.0)), secrets),
        take_profit_pct=_dec("POTATO_TAKE_PROFIT_PCT", str(strat.get("take_profit_pct", 0.10)), secrets),
        stop_loss_pct=_dec("POTATO_STOP_LOSS_PCT", str(strat.get("stop_loss_pct", 0.05)), secrets),
        max_open_positions=int(secrets.get("POTATO_MAX_OPEN_POSITIONS", "") or os.getenv("POTATO_MAX_OPEN_POSITIONS", str(risk.get("max_open_positions", 5)))),
        default_order_size_cny=_dec("POTATO_DEFAULT_ORDER_SIZE_CNY", str(strat.get("default_order_size_cny", 200)), secrets),
        max_consecutive_failures=int(risk.get("max_consecutive_failures", 3)),
        llm_model=s("POTATO_LLM_MODEL", "POTATO_LLM_MODEL", default=oc.get("model", "deepseek/deepseek-chat")),
        notify_enabled=s("POTATO_NOTIFY_ENABLED", "POTATO_NOTIFY_ENABLED", default="true").lower() in {"1", "true", "yes"},
        notify_channels=tuple(
            c.strip().lower()
            for c in s(
                "POTATO_NOTIFY_CHANNELS",
                "POTATO_NOTIFY_CHANNELS",
                default="telegram,dingtalk",
            ).split(",")
            if c.strip()
        ),
        telegram_bot_token=s("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=s("TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID"),
        dingtalk_webhook_url=s("DINGTALK_WEBHOOK_URL", "DINGTALK_WEBHOOK_URL"),
        dingtalk_secret=s("DINGTALK_SECRET", "DINGTALK_SECRET"),
        feishu_webhook_url=s("FEISHU_WEBHOOK_URL", "FEISHU_WEBHOOK_URL"),
        feishu_app_id=s("FEISHU_APP_ID", "FEISHU_APP_ID"),
        feishu_app_secret=s("FEISHU_APP_SECRET", "FEISHU_APP_SECRET"),
        feishu_receive_id=s("FEISHU_RECEIVE_ID", "FEISHU_RECEIVE_ID"),
        feishu_api_base=s(
            "FEISHU_API_BASE",
            "FEISHU_API_BASE",
            default="https://open.larksuite.com",
        ),
    )
