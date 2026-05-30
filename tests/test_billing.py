"""Billing module tests — usage tracking, cost calculation, provider status, renewal."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from potato.billing import (
    BillingManager,
    PROVIDER_PRICING,
    PLATFORM_MARGIN_RATE,
    USD_TO_CNY,
    DEFAULT_PLATFORM_WALLET,
)


@pytest.fixture
def billing():
    manager = BillingManager()
    yield manager


def test_provider_pricing_structure():
    assert "deepseek" in PROVIDER_PRICING
    assert "siliconflow" in PROVIDER_PRICING
    assert "liner" in PROVIDER_PRICING
    assert "openai" in PROVIDER_PRICING
    assert "base44" in PROVIDER_PRICING
    for pid, pricing in PROVIDER_PRICING.items():
        assert "name" in pricing
        assert "input_per_1m" in pricing
        assert "output_per_1m" in pricing
        assert "monthly_min_usd" in pricing
        assert "renewal_url" in pricing


def test_record_usage(billing):
    record = billing.record_usage(
        provider="deepseek",
        model="deepseek-chat",
        tokens_in=1000,
        tokens_out=500,
        task="chat",
    )
    assert record.provider == "deepseek"
    assert record.tokens_in == 1000
    assert record.tokens_out == 500
    assert record.cost_usd > 0
    assert record.cost_cny > 0
    assert record.margin_cny > 0
    assert record.total_cny == round(record.cost_cny + record.margin_cny, 4)


def test_record_usage_multiple_providers(billing):
    billing.record_usage("deepseek", "deepseek-chat", 2000, 1000, "analysis")
    billing.record_usage("openai", "gpt-4o-mini", 500, 200, "chat")
    summary = billing.get_usage_summary(days=30)
    assert summary["total_tokens_in"] >= 2500
    assert summary["total_tokens_out"] >= 1200
    assert len(summary["providers"]) >= 2


def test_margin_rate():
    assert PLATFORM_MARGIN_RATE == 1.0


def test_cost_calculation():
    pricing = PROVIDER_PRICING["deepseek"]
    input_cost = (1000000 / 1_000_000) * pricing["input_per_1m"]
    output_cost = (1000000 / 1_000_000) * pricing["output_per_1m"]
    total_usd = input_cost + output_cost
    assert total_usd > 0
    total_cny = total_usd * USD_TO_CNY
    assert total_cny > 0
    margin = total_cny * PLATFORM_MARGIN_RATE
    total_with_margin = total_cny + margin
    assert total_with_margin == pytest.approx(total_cny * 2, abs=0.01)


def test_provider_statuses(billing):
    statuses = billing.get_provider_statuses()
    assert len(statuses) == 5
    for s in statuses:
        assert s.provider in PROVIDER_PRICING
        assert isinstance(s.key_configured, bool)
        assert isinstance(s.total_cost_cny, (int, float))
        assert s.monthly_min_cny > 0
        assert s.cost_with_margin > 0
        assert s.cost_with_margin == pytest.approx(s.monthly_min_cny * 2, abs=0.01)


def test_wallet_topup(billing):
    wallet_before = billing.get_wallet_balance()
    balance_before = wallet_before["balance_cny"]

    result = billing.add_wallet_topup(amount_cny=100.0, method="manual")
    assert result["ok"] is True
    assert result["amount_cny"] == 100.0

    result2 = billing.add_wallet_topup(amount_cny=50.0, method="crypto", tx_hash="0xabc123")
    assert result2["ok"] is True

    wallet = billing.get_wallet_balance()
    assert wallet["balance_cny"] == balance_before + 150.0


def test_wallet_balance(billing):
    wallet = billing.get_wallet_balance()
    assert "balance_cny" in wallet
    assert "remaining_cny" in wallet
    assert "currency" in wallet
    assert wallet["currency"] == "CNY"


def test_billing_dashboard_no_margin_exposure(billing):
    billing.record_usage("deepseek", "deepseek-chat", 1000, 500, "chat")
    dashboard = billing.get_billing_dashboard()
    assert "providers" in dashboard
    assert "wallet" in dashboard
    assert "usage_30d" in dashboard
    assert "summary_text" in dashboard
    assert dashboard["configured_count"] >= 0
    text = dashboard["summary_text"]
    assert "平台费" not in text
    assert "2x" not in text
    assert "费率" not in text
    assert "原价" not in text
    assert "margin" not in text.lower()


def test_billing_dashboard_shows_total_price(billing):
    dashboard = billing.get_billing_dashboard()
    text = dashboard["summary_text"]
    assert "¥" in text or "余额" in text or "使用" in text


def test_usage_summary_empty():
    manager = BillingManager()
    summary = manager.get_usage_summary(days=30)
    assert "total_tokens_in" in summary
    assert "total_tokens_out" in summary
    assert "total_cost_cny" in summary
    assert "providers" in summary


def test_monthly_min_calculation():
    for pid, pricing in PROVIDER_PRICING.items():
        min_usd = pricing["monthly_min_usd"]
        min_cny = min_usd * USD_TO_CNY
        cost_with_margin = min_cny * (1 + PLATFORM_MARGIN_RATE)
        assert cost_with_margin > 0
        assert cost_with_margin == pytest.approx(min_cny * 2, abs=0.01)


def test_default_wallet_address():
    assert DEFAULT_PLATFORM_WALLET == ""
    assert len(DEFAULT_PLATFORM_WALLET) == 0


def test_get_platform_wallet_default():
    manager = BillingManager()
    addr = manager._get_platform_wallet()
    assert addr == "" or addr.startswith("T")


def test_get_renewal_payment_info_no_margin_exposure():
    manager = BillingManager()
    info = manager.get_renewal_payment_info()
    assert "wallet_address" in info
    assert "wallet_label" in info
    assert "currency" in info
    assert "items" in info
    assert "payment_note" in info
    assert "balance_sufficient" in info
    assert info["wallet_address"] == DEFAULT_PLATFORM_WALLET
    assert info["wallet_label"] == "USDT-TRC20"
    assert isinstance(info["items"], list)
    for item in info["items"]:
        assert "price_cny" in item
        assert "name" in item
        assert "monthly_min_cny" not in item
        assert "cost_with_margin" not in item


def test_get_renewal_payment_info_with_provider():
    manager = BillingManager()
    info = manager.get_renewal_payment_info(provider="deepseek")
    assert info["wallet_address"] == DEFAULT_PLATFORM_WALLET
    for item in info["items"]:
        assert item["provider"] == "deepseek"


def test_renewal_auto_deduct_when_balance_sufficient():
    manager = BillingManager()
    manager.add_wallet_topup(amount_cny=500.0, method="test")
    wallet_before = manager.get_wallet_balance()
    info = manager.get_renewal_payment_info()
    if info["items"] and info["total_renewal_cny"] > 0:
        if info["balance_sufficient"]:
            wallet_after = manager.get_wallet_balance()
            assert wallet_after["remaining_cny"] < wallet_before["remaining_cny"]


def test_wallet_config_table_created():
    manager = BillingManager()
    import sqlite3
    from potato.billing import DB_PATH
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='wallet_config'"
        ).fetchone()
    assert row is not None


def test_platform_wallet_vault_key():
    from potato.vault import KNOWN_KEYS
    assert "PLATFORM_WALLET_ADDRESS" in KNOWN_KEYS
    assert KNOWN_KEYS["PLATFORM_WALLET_ADDRESS"]["category"] == "billing"
    assert KNOWN_KEYS["PLATFORM_WALLET_ADDRESS"].get("renewal_only") is True


def test_generate_payment_qr():
    manager = BillingManager()
    qr_b64 = manager.generate_payment_qr(amount_cny=72.5)
    assert qr_b64.startswith("data:image/png;base64,")
    assert len(qr_b64) > 100


def test_generate_payment_qr_no_amount():
    manager = BillingManager()
    qr_b64 = manager.generate_payment_qr()
    assert qr_b64.startswith("data:image/png;base64,")
    assert "tron:" in DEFAULT_PLATFORM_WALLET or len(qr_b64) > 100


def test_wallet_address_persisted_on_init():
    import sqlite3
    from potato.billing import DB_PATH, DEFAULT_PLATFORM_WALLET
    manager = BillingManager()
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT value FROM wallet_config WHERE key = 'platform_wallet'"
        ).fetchone()
    assert row is not None
    assert row[0] == DEFAULT_PLATFORM_WALLET or row[0] == ""


def test_dashboard_no_margin_keywords():
    manager = BillingManager()
    manager.record_usage("deepseek", "deepseek-chat", 500, 200, "chat")
    dashboard = manager.get_billing_dashboard()
    text = dashboard["summary_text"]
    for word in ["平台费", "2x", "费率", "原价", "margin", "成本拆分", "利润"]:
        assert word not in text.lower(), f"Dashboard exposes margin keyword: {word}"


def test_sanitize_reply_masks_secrets():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop_pet" / "backend"))
    from main import _sanitize_reply

    assert "***" in _sanitize_reply("my key is sk-abc12345def67890xyz012abc345def678"), "sk-key not masked"
    assert "***" in _sanitize_reply("wallet TNaKz5d2eR9u8W9oM3bXqY7kP4fGh6iJkLm"), "wallet not masked"
    assert "***" in _sanitize_reply("password=supersecret123"), "password not masked"
    assert "***" in _sanitize_reply("from potato.billing import BillingManager"), "import not masked"
    assert "***" in _sanitize_reply("sqlite database at data/billing.db"), "db path not masked"
    assert "***" in _sanitize_reply("def my_function("), "def not masked"
    assert "***" in _sanitize_reply("PLATFORM_MARGIN_RATE = 1.0"), "margin rate not masked"
    assert "***" in _sanitize_reply("cost_with_margin = 72.5"), "margin field not masked"


def test_renewal_items_no_margin_fields():
    manager = BillingManager()
    info = manager.get_renewal_payment_info()
    for item in info["items"]:
        assert "price_cny" in item
        assert "monthly_min_cny" not in item
        assert "cost_with_margin" not in item