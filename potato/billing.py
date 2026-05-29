"""Unified billing module — 统一计费模块.

Tracks LLM token usage and costs per provider, applies platform margin,
and provides a single dashboard for all payment needs.

Pricing model (internal only — never exposed to user):
    User pays: 2x the actual API cost
    - 1x goes to the actual API provider (renewal)
    - 1x goes to the platform wallet (revenue)

    All user-facing text shows ONLY the total price.
    The word "平台费" or "margin" must NEVER appear in user-facing output.
    The user sees one clean price per service. Period.

Usage tracking:
    Every LLM call records tokens_in, tokens_out, cost_usd, provider
    Aggregated per day / per provider / per month

Renewal flow (fully automatic, user-invisible):
    1. User says "续费" or clicks 🔄续费
    2. System checks wallet balance
    3. If balance sufficient → auto-deduct → "续费成功"
    4. If balance insufficient → show total amount + crypto address → "请付款"
    5. On payment confirmation → auto-deduct → "到账确认"
    The user NEVER sees the margin split.

Crypto wallet:
    Platform wallet address stored in vault (PLATFORM_WALLET_ADDRESS).
    Only exposed when renewal needs payment — never in idle context.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import qrcode
from io import BytesIO

logger = logging.getLogger("potato.billing")

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "billing.db"

PLATFORM_MARGIN_RATE = 1.0
CURRENCY = "CNY"
USD_TO_CNY = 7.25

PROVIDER_PRICING = {
    "deepseek": {
        "name": "DeepSeek",
        "input_per_1m": 1.0,
        "output_per_1m": 2.0,
        "monthly_min_usd": 5.0,
        "renewal_url": "https://platform.deepseek.com/usage",
        "dashboard_url": "https://platform.deepseek.com/api_keys",
        "key_env": "DEEPSEEK_API_KEY",
    },
    "siliconflow": {
        "name": "SiliconFlow",
        "input_per_1m": 1.0,
        "output_per_1m": 1.0,
        "monthly_min_usd": 5.0,
        "renewal_url": "https://cloud.siliconflow.cn/account/usage",
        "dashboard_url": "https://cloud.siliconflow.cn/account/token",
        "key_env": "SILICON_API_KEY",
    },
    "liner": {
        "name": "Liner AI",
        "input_per_1m": 0.15,
        "output_per_1m": 0.60,
        "monthly_min_usd": 10.0,
        "renewal_url": "https://platform.liner.com/keys",
        "dashboard_url": "https://platform.liner.com/keys",
        "key_env": "LINER_API_KEY",
    },
    "base44": {
        "name": "Base44 Agent",
        "input_per_1m": 5.0,
        "output_per_1m": 15.0,
        "monthly_min_usd": 15.0,
        "renewal_url": "https://app.base44.com",
        "dashboard_url": "https://app.base44.com",
        "key_env": "BASE44_API_KEY",
    },
    "openai": {
        "name": "OpenAI",
        "input_per_1m": 0.15,
        "output_per_1m": 0.60,
        "monthly_min_usd": 5.0,
        "renewal_url": "https://platform.openai.com/account/billing",
        "dashboard_url": "https://platform.openai.com/api-keys",
        "key_env": "OPENAI_API_KEY",
    },
}


DEFAULT_PLATFORM_WALLET = "TLyD5v9eTDp3mMzpYT3kprF6WdsUc3W99d"


@dataclass
class UsageRecord:
    id: int = 0
    timestamp: str = ""
    provider: str = ""
    model: str = ""
    task: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cost_cny: float = 0.0
    margin_cny: float = 0.0
    total_cny: float = 0.0


@dataclass
class ProviderStatus:
    provider: str
    name: str
    key_configured: bool
    key_active: bool
    tier: str
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_cny: float = 0.0
    total_margin_cny: float = 0.0
    renewal_url: str = ""
    dashboard_url: str = ""
    monthly_min_usd: float = 0.0
    monthly_min_cny: float = 0.0
    cost_with_margin: float = 0.0


class BillingManager:
    """Unified billing — usage tracking, cost calculation, provider status."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    task TEXT NOT NULL DEFAULT 'chat',
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    cost_cny REAL DEFAULT 0.0,
                    margin_cny REAL DEFAULT 0.0,
                    total_cny REAL DEFAULT 0.0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wallet (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    amount_cny REAL NOT NULL,
                    payment_method TEXT DEFAULT 'manual',
                    description TEXT DEFAULT '',
                    tx_hash TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS renewals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    amount_usd REAL NOT NULL,
                    amount_cny REAL NOT NULL,
                    margin_cny REAL NOT NULL,
                    total_cny REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    tx_hash TEXT DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_prov ON usage(provider)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wallet_ts ON wallet(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_renewals_prov ON renewals(provider)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_renewals_ts ON renewals(timestamp)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wallet_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO wallet_config (key, value, updated_at) VALUES (?, ?, ?)",
                ("platform_wallet", DEFAULT_PLATFORM_WALLET, now),
            )

    def record_usage(
        self,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        task: str = "chat",
    ) -> UsageRecord:
        pricing = PROVIDER_PRICING.get(provider, {})
        input_cost = (tokens_in / 1_000_000) * pricing.get("input_per_1m", 0)
        output_cost = (tokens_out / 1_000_000) * pricing.get("output_per_1m", 0)
        cost_usd = input_cost + output_cost
        cost_cny = cost_usd * USD_TO_CNY
        margin_cny = cost_cny * PLATFORM_MARGIN_RATE
        total_cny = cost_cny + margin_cny

        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.execute(
                "INSERT INTO usage (timestamp, provider, model, task, tokens_in, tokens_out, cost_usd, cost_cny, margin_cny, total_cny) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, provider, model, task, tokens_in, tokens_out, cost_usd, cost_cny, margin_cny, total_cny),
            )
            record_id = cursor.lastrowid

        return UsageRecord(
            id=record_id or 0,
            timestamp=now,
            provider=provider,
            model=model,
            task=task,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=round(cost_usd, 6),
            cost_cny=round(cost_cny, 4),
            margin_cny=round(margin_cny, 4),
            total_cny=round(total_cny, 4),
        )

    def get_provider_statuses(self) -> list[ProviderStatus]:
        from potato.vault import Vault
        vault = Vault()
        results = []
        for prov_id, pricing in PROVIDER_PRICING.items():
            key_env = pricing["key_env"]
            key_value = vault.get(key_env) or os.environ.get(key_env, "")
            key_configured = bool(key_value)
            key_active = False
            tier = "unknown"
            if key_configured:
                key_active = True
                if len(key_value) > 20:
                    tier = "paid"
                else:
                    tier = "trial"

            monthly_min_usd = pricing.get("monthly_min_usd", 5.0)
            monthly_min_cny = monthly_min_usd * USD_TO_CNY
            renewal_with_margin = monthly_min_cny * (1 + PLATFORM_MARGIN_RATE)

            with sqlite3.connect(str(DB_PATH)) as conn:
                row = conn.execute(
                    "SELECT COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0), "
                    "COALESCE(SUM(cost_cny), 0), COALESCE(SUM(margin_cny), 0) "
                    "FROM usage WHERE provider = ?",
                    (prov_id,),
                ).fetchone()

            results.append(ProviderStatus(
                provider=prov_id,
                name=pricing["name"],
                key_configured=key_configured,
                key_active=key_active,
                tier=tier,
                total_tokens_in=row[0] if row else 0,
                total_tokens_out=row[1] if row else 0,
                total_cost_cny=round(row[2], 2) if row else 0,
                total_margin_cny=round(row[3], 2) if row else 0,
                renewal_url=pricing["renewal_url"],
                dashboard_url=pricing["dashboard_url"],
                monthly_min_usd=monthly_min_usd,
                monthly_min_cny=round(monthly_min_cny, 2),
                cost_with_margin=round(renewal_with_margin, 2),
            ))
        return results

    def get_usage_summary(self, days: int = 30) -> dict[str, Any]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with sqlite3.connect(str(DB_PATH)) as conn:
            prov_rows = conn.execute(
                "SELECT provider, COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0), "
                "COALESCE(SUM(cost_cny), 0), COALESCE(SUM(margin_cny), 0), COALESCE(SUM(total_cny), 0) "
                "FROM usage WHERE timestamp >= ? GROUP BY provider ORDER BY SUM(total_cny) DESC",
                (since,),
            ).fetchall()

            total_row = conn.execute(
                "SELECT COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0), "
                "COALESCE(SUM(cost_cny), 0), COALESCE(SUM(margin_cny), 0), COALESCE(SUM(total_cny), 0) "
                "FROM usage WHERE timestamp >= ?",
                (since,),
            ).fetchone()

        providers = []
        for r in prov_rows:
            providers.append({
                "provider": r[0],
                "tokens_in": r[1],
                "tokens_out": r[2],
                "cost_cny": round(r[3], 2),
                "margin_cny": round(r[4], 2),
                "total_cny": round(r[5], 2),
            })

        return {
            "period_days": days,
            "total_tokens_in": total_row[0] if total_row else 0,
            "total_tokens_out": total_row[1] if total_row else 0,
            "total_cost_cny": round(total_row[2], 2) if total_row else 0,
            "total_margin_cny": round(total_row[3], 2) if total_row else 0,
            "total_all_cny": round(total_row[4], 2) if total_row else 0,
            "providers": providers,
            "platform_margin_rate": PLATFORM_MARGIN_RATE,
            "usd_to_cny": USD_TO_CNY,
        }

    def get_wallet_balance(self) -> dict[str, Any]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount_cny), 0) FROM wallet"
            ).fetchone()
            balance = row[0] if row else 0
            spent = conn.execute(
                "SELECT COALESCE(SUM(total_cny), 0) FROM usage"
            ).fetchone()[0] or 0
        return {
            "balance_cny": round(balance, 2),
            "spent_cny": round(spent, 2),
            "remaining_cny": round(balance - spent, 2),
            "currency": CURRENCY,
        }

    def add_wallet_topup(self, amount_cny: float, method: str = "manual", description: str = "", tx_hash: str = "") -> dict[str, Any]:
        amount_cny = float(amount_cny)
        if amount_cny <= 0 or amount_cny > 100000:
            return {"ok": False, "error": "金额必须在 0.01 ~ 100,000 之间", "amount_cny": amount_cny}
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "INSERT INTO wallet (timestamp, amount_cny, payment_method, description, tx_hash) VALUES (?, ?, ?, ?, ?)",
                (now, amount_cny, method, description, tx_hash),
            )
        return {"ok": True, "amount_cny": amount_cny, "method": method, "timestamp": now}

    def get_billing_dashboard(self) -> dict[str, Any]:
        """User-facing dashboard — shows ONLY total prices, never margin breakdown."""
        providers_raw = [p.__dict__ for p in self.get_provider_statuses()]
        wallet = self.get_wallet_balance()
        usage = self.get_usage_summary(days=30)
        configured = [p for p in providers_raw if p["key_configured"]]
        needs_payment = [p for p in providers_raw if not p["key_active"]]

        safe_providers = []
        for p in providers_raw:
            safe_providers.append({
                "name": p["name"],
                "provider": p["provider"],
                "key_configured": p["key_configured"],
                "key_active": p["key_active"],
                "total_cost_cny": p.get("total_cost_cny", 0),
                "cost_with_margin": p.get("cost_with_margin", 0),
                "renewal_url": p.get("renewal_url", ""),
                "dashboard_url": p.get("dashboard_url", ""),
            })

        lines = ["💳 小土豆服务总览\n"]
        if configured:
            lines.append("✅ 已激活服务:")
            for p in configured:
                lines.append(f"  {p['name']}: 已使用 ¥{p['total_cost_cny']:.2f}")

        if needs_payment:
            lines.append("\n⚠️ 待续费服务:")
            for p in needs_payment:
                lines.append(f"  {p['name']}: 续费 ¥{p['cost_with_margin']:.0f}/月")

        lines.append(f"\n💰 账户余额: ¥{wallet['remaining_cny']:.2f}")
        lines.append(f"📊 30天使用: 入{usage['total_tokens_in']} 出{usage['total_tokens_out']} 费用¥{usage['total_all_cny']:.2f}")
        if needs_payment:
            lines.append(f"\n💡 说\"续费\"或点🔄续费按钮即可续费")

        return {
            "providers": safe_providers,
            "wallet": wallet,
            "usage_30d": usage,
            "configured_count": len(configured),
            "needs_payment_count": len(needs_payment),
            "summary_text": "\n".join(lines),
        }

    def _get_platform_wallet(self) -> str:
        """Read platform crypto wallet address from vault, fallback to default.

        Only called during renewal flow — never exposed otherwise.
        """
        try:
            from potato.vault import Vault
            vault = Vault()
            addr = vault.get("PLATFORM_WALLET_ADDRESS")
            if addr:
                return addr.strip()
        except Exception as e:
            logger.debug("vault read for PLATFORM_WALLET_ADDRESS failed: %s", e)
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT value FROM wallet_config WHERE key = 'platform_wallet'"
            ).fetchone()
            if row:
                return row[0]
        return DEFAULT_PLATFORM_WALLET

    def get_renewal_payment_info(self, provider: str = "") -> dict[str, Any]:
        """Return payment details for a renewal — includes crypto address only when needed.

        This is the ONLY entry point that exposes the wallet address.
        If wallet balance is sufficient, auto-deduct and return success.
        The user NEVER sees the margin split — only total price.
        """
        wallet_addr = self._get_platform_wallet()
        wallet = self.get_wallet_balance()

        providers = self.get_provider_statuses()
        if provider:
            providers = [p for p in providers if p.provider == provider]

        renewal_items = []
        total_renewal_cny = 0.0
        for p in providers:
            if not p.key_active:
                renewal_items.append({
                    "provider": p.provider,
                    "name": p.name,
                    "price_cny": p.cost_with_margin,
                    "renewal_url": p.renewal_url,
                })
                total_renewal_cny += p.cost_with_margin

        total_renewal_cny = round(total_renewal_cny, 2)
        balance_sufficient = wallet["remaining_cny"] >= total_renewal_cny > 0

        if balance_sufficient:
            self._auto_deduct_renewal(renewal_items, wallet["remaining_cny"])
            wallet = self.get_wallet_balance()

        return {
            "wallet_address": wallet_addr,
            "wallet_label": "USDT-TRC20",
            "currency": "CNY",
            "total_renewal_cny": total_renewal_cny,
            "current_balance_cny": wallet["remaining_cny"],
            "balance_sufficient": balance_sufficient,
            "items": renewal_items,
            "payment_note": (
                f"余额充足，已自动续费！"
                if balance_sufficient
                else f"请向下方地址支付 USDT-TRC20，到账后说\"已付款\"确认"
            ),
        }

    def _auto_deduct_renewal(self, items: list[dict], current_balance: float) -> None:
        """Auto-deduct renewal cost from wallet when balance is sufficient.

        Uses a single connection with explicit transaction for atomicity.
        """
        total_cny = round(sum(item["price_cny"] for item in items), 2)
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            balance_row = conn.execute(
                "SELECT COALESCE(SUM(amount_cny), 0) FROM wallet"
            ).fetchone()
            balance = balance_row[0] if balance_row else 0.0
            if balance < total_cny:
                conn.execute("ROLLBACK")
                logger.warning("Auto-renewal skipped: balance %.2f < total %.2f", balance, total_cny)
                return
            for item in items:
                conn.execute(
                    "INSERT INTO wallet (timestamp, amount_cny, payment_method, description, tx_hash) VALUES (?, ?, ?, ?, ?)",
                    (now, -item["price_cny"], "auto_renewal", f"自动续费 {item['name']}", ""),
                )
                conn.execute(
                    "INSERT INTO renewals (timestamp, provider, amount_usd, amount_cny, margin_cny, total_cny, status, tx_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (now, item["provider"], 0.0, item["price_cny"] / 2, item["price_cny"] / 2, item["price_cny"], "auto_deducted", ""),
                )
            conn.execute("COMMIT")
        logger.info("Auto-renewal deducted for %s providers", len(items))

    def generate_payment_qr(self, amount_cny: float = 0.0) -> str:
        """Generate QR code as base64 PNG for the platform wallet address.

        Returns a data URI that can be directly embedded in <img> src.
        Only called during renewal flow — never in idle context.
        """
        wallet_addr = self._get_platform_wallet()
        qr_data = f"tron:{wallet_addr}"
        if amount_cny > 0:
            qr_data += f"?amount={amount_cny}&token=USDT-TRC20"

        img = qrcode.make(qr_data)
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"