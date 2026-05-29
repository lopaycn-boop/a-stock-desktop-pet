"""Broker adapter tests — dry-run mode, mode switching, order flow."""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from potato.trading.broker import (
    BrokerAdapter,
    DryRunBroker,
    EasyTraderBroker,
    OrderResult,
    PositionInfo,
    BalanceInfo,
)


@pytest.mark.asyncio
async def test_dry_run_broker_buy():
    broker = DryRunBroker()
    result = await broker.buy("600519", "贵州茅台", Decimal("1800"), 100)
    assert result.ok is True
    assert result.action == "BUY"
    assert result.symbol == "600519"
    assert result.name == "贵州茅台"
    assert result.price == Decimal("1800")
    assert result.quantity == 100
    assert result.amount_cny == Decimal("180000")
    assert result.mode == "dry_run"
    assert result.order_id.startswith("DRY-")
    assert result.status == "filled"


@pytest.mark.asyncio
async def test_dry_run_broker_sell():
    broker = DryRunBroker()
    pos = await broker.buy("600519", "贵州茅台", Decimal("1800"), 100)
    assert pos.ok is True
    result = await broker.sell("600519", "贵州茅台", Decimal("1900"), 100)
    assert result.ok is True
    assert result.action == "SELL"
    assert result.symbol == "600519"
    assert result.price == Decimal("1900")
    assert result.mode == "dry_run"


@pytest.mark.asyncio
async def test_dry_run_broker_position():
    broker = DryRunBroker()
    await broker.buy("000858", "五粮液", Decimal("160"), 200)
    pos = await broker.get_position("000858")
    assert pos is not None
    assert pos.symbol == "000858"
    assert pos.name == "五粮液"
    assert pos.quantity == 200
    assert pos.cost_price == Decimal("160")
    positions = await broker.get_positions()
    assert len(positions) >= 1


@pytest.mark.asyncio
async def test_dry_run_broker_balance():
    broker = DryRunBroker()
    bal = await broker.get_balance()
    assert isinstance(bal, BalanceInfo)
    assert bal.available_cash > Decimal("0")


@pytest.mark.asyncio
async def test_dry_run_broker_cancel():
    broker = DryRunBroker()
    result = await broker.cancel_order("DRY-000001")
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_dry_run_health_check():
    broker = DryRunBroker()
    health = await broker.health_check()
    assert health["ok"] is True
    assert health["mode"] == "dry_run"
    assert health["connected"] is True


@pytest.mark.asyncio
async def test_broker_adapter_default_mode():
    broker = BrokerAdapter()
    assert broker.mode == "dry_run"
    assert broker.is_live is False


@pytest.mark.asyncio
async def test_broker_adapter_dry_run_explicit():
    broker = BrokerAdapter(mode="dry_run")
    assert broker.mode == "dry_run"
    assert broker.is_live is False
    health = await broker.health_check()
    assert health["ok"] is True
    assert health["configured_mode"] == "dry_run"


@pytest.mark.asyncio
async def test_broker_adapter_switch_to_live_fails_without_broker():
    broker = BrokerAdapter(mode="dry_run")
    assert broker.mode == "dry_run"
    result = await broker.switch_mode("invalid_mode")
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_broker_adapter_buy_dry_run():
    broker = BrokerAdapter(mode="dry_run")
    result = await broker.buy("601318", "中国平安", Decimal("45"), 200)
    assert result.ok is True
    assert result.mode == "dry_run"
    assert result.symbol == "601318"


@pytest.mark.asyncio
async def test_broker_adapter_sell_dry_run():
    broker = BrokerAdapter(mode="dry_run")
    await broker.buy("601318", "中国平安", Decimal("45"), 200)
    result = await broker.sell("601318", "中国平安", Decimal("47"), 200)
    assert result.ok is True
    assert result.mode == "dry_run"


@pytest.mark.asyncio
async def test_broker_adapter_cancel_dry_run():
    broker = BrokerAdapter(mode="dry_run")
    result = await broker.cancel_order("DRY-000001")
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_order_result_to_dict():
    order = OrderResult(
        ok=True, action="BUY", symbol="600519", name="贵州茅台",
        price=Decimal("1800"), quantity=100, amount_cny=Decimal("180000"),
        order_id="DRY-000001", status="filled", message="OK",
        mode="dry_run", timestamp="2025-01-01T00:00:00Z",
    )
    d = order.to_dict()
    assert d["ok"] is True
    assert d["action"] == "BUY"
    assert d["symbol"] == "600519"
    assert d["price"] == "1800"
    assert d["quantity"] == 100
    assert d["mode"] == "dry_run"


@pytest.mark.asyncio
async def test_position_info_to_dict():
    pos = PositionInfo(
        symbol="600519", name="贵州茅台", quantity=100, available=100,
        cost_price=Decimal("1800"), current_price=Decimal("1900"),
        market_value=Decimal("190000"), profit_loss=Decimal("10000"),
        profit_pct=Decimal("5.56"),
    )
    d = pos.to_dict()
    assert d["symbol"] == "600519"
    assert d["quantity"] == 100
    assert d["profit_pct"] == "5.56"


@pytest.mark.asyncio
async def test_balance_info_to_dict():
    bal = BalanceInfo(
        total_assets=Decimal("100000"), available_cash=Decimal("100000"),
        frozen_cash=Decimal("0"), market_value=Decimal("0"),
        profit_loss=Decimal("0"),
    )
    d = bal.to_dict()
    assert d["total_assets"] == "100000"
    assert d["available_cash"] == "100000"


@pytest.mark.asyncio
async def test_executor_uses_broker_adapter():
    from potato.trading.executor import TradeExecutor
    from potato.trading.broker import BrokerAdapter

    broker = BrokerAdapter(mode="dry_run")
    executor = TradeExecutor(broker=broker)
    assert executor._broker.mode == "dry_run"
    assert executor._broker.is_live is False


@pytest.mark.asyncio
async def test_executor_default_broker_is_dry_run():
    from potato.trading.executor import TradeExecutor

    executor = TradeExecutor()
    assert executor._broker.mode == "dry_run"
    assert executor._broker.is_live is False


@pytest.mark.asyncio
async def test_multiple_buys_sell():
    broker = DryRunBroker()
    await broker.buy("600519", "贵州茅台", Decimal("1800"), 100)
    await broker.buy("000858", "五粮液", Decimal("160"), 200)

    positions = await broker.get_positions()
    assert len(positions) == 2

    result = await broker.sell("600519", "贵州茅台", Decimal("1850"), 100)
    assert result.ok is True

    positions = await broker.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "000858"


@pytest.mark.asyncio
async def test_sell_nonexistent_position():
    broker = DryRunBroker()
    result = await broker.sell("999999", "不存在", Decimal("10"), 100)
    assert result.ok is True
    assert result.mode == "dry_run"


@pytest.mark.asyncio
async def test_easytrader_broker_not_connected():
    broker = EasyTraderBroker(broker_id="eastmoney")
    result = await broker.buy("600519", "贵州茅台", Decimal("1800"), 100)
    assert result.ok is False
    assert result.mode == "live"
    assert "无法连接" in result.message or "客户端" in result.message


@pytest.mark.asyncio
async def test_easytrader_health_check_not_connected():
    broker = EasyTraderBroker(broker_id="eastmoney")
    health = await broker.health_check()
    assert health["mode"] == "live"
    assert health["broker"] == "eastmoney"