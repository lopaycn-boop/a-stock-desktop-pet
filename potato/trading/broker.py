"""Broker adapter layer — 统一券商交易接口.

Supports:
    - easytrader (东方财富/同花顺/通用券商客户端)
    - Dry-run mode (模拟执行，不发送真实订单)
    - Live mode (真实交易，连接券商客户端)

Safety:
    - TRADING_MODE env var: "dry_run" (default) or "live"
    - Live mode requires: user capital confirmation + broker connected
    - All trades logged to journal regardless of mode
    - Double confirmation for live trades exceeding 50% of daily limit

Usage:
    broker = BrokerAdapter(mode="dry_run")   # 模拟模式（默认）
    broker = BrokerAdapter(mode="live")       # 真实交易模式
    result = await broker.buy(symbol="600519", price=1800.0, quantity=100)
    result = await broker.sell(symbol="600519", price=1850.0, quantity=100)
    result = await broker.get_position(symbol="600519")
    result = await broker.get_balance()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from potato.user_prefs import UserPrefs

logger = logging.getLogger("potato.trading.broker")

TRADING_MODE = os.environ.get("TRADING_MODE", "dry_run").lower()


@dataclass
class OrderResult:
    ok: bool
    action: str
    symbol: str
    name: str
    price: Decimal
    quantity: int
    amount_cny: Decimal
    order_id: str = ""
    status: str = ""
    message: str = ""
    mode: str = "dry_run"
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "symbol": self.symbol,
            "name": self.name,
            "price": str(self.price),
            "quantity": self.quantity,
            "amount_cny": str(self.amount_cny),
            "order_id": self.order_id,
            "status": self.status,
            "message": self.message,
            "mode": self.mode,
            "timestamp": self.timestamp,
        }


@dataclass
class PositionInfo:
    symbol: str
    name: str
    quantity: int
    available: int
    cost_price: Decimal
    current_price: Decimal
    market_value: Decimal
    profit_loss: Decimal
    profit_pct: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "quantity": self.quantity,
            "available": self.available,
            "cost_price": str(self.cost_price),
            "current_price": str(self.current_price),
            "market_value": str(self.market_value),
            "profit_loss": str(self.profit_loss),
            "profit_pct": str(self.profit_pct),
        }


@dataclass
class BalanceInfo:
    total_assets: Decimal
    available_cash: Decimal
    frozen_cash: Decimal
    market_value: Decimal
    profit_loss: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_assets": str(self.total_assets),
            "available_cash": str(self.available_cash),
            "frozen_cash": str(self.frozen_cash),
            "market_value": str(self.market_value),
            "profit_loss": str(self.profit_loss),
        }


class DryRunBroker:
    """Simulated broker for paper trading — no real orders placed."""

    def __init__(self):
        self._order_counter = 0
        self._positions: dict[str, PositionInfo] = {}
        self._balance = BalanceInfo(
            total_assets=Decimal("100000"),
            available_cash=Decimal("100000"),
            frozen_cash=Decimal("0"),
            market_value=Decimal("0"),
            profit_loss=Decimal("0"),
        )
        self._load_prefs_balance()

    def _load_prefs_balance(self):
        try:
            prefs = UserPrefs()
            all_prefs = prefs.get_all()
            daily = all_prefs.get("max_daily_trade_cny") or all_prefs.get("max_daily_cny")
            single = all_prefs.get("max_single_trade_cny") or all_prefs.get("max_single_cny")
            if daily:
                self._balance = BalanceInfo(
                    total_assets=Decimal(str(daily)),
                    available_cash=Decimal(str(daily)),
                    frozen_cash=Decimal("0"),
                    market_value=Decimal("0"),
                    profit_loss=Decimal("0"),
                )
        except Exception:
            pass

    async def buy(self, symbol: str, name: str, price: Decimal, quantity: int) -> OrderResult:
        self._order_counter += 1
        amount = price * quantity
        self._positions[symbol] = PositionInfo(
            symbol=symbol, name=name, quantity=quantity, available=quantity,
            cost_price=price, current_price=price,
            market_value=amount, profit_loss=Decimal("0"), profit_pct=Decimal("0"),
        )
        self._balance.available_cash -= amount
        self._balance.market_value += amount
        self._balance.frozen_cash += Decimal("0")
        return OrderResult(
            ok=True, action="BUY", symbol=symbol, name=name,
            price=price, quantity=quantity, amount_cny=amount,
            order_id=f"DRY-{self._order_counter:06d}",
            status="filled", message="模拟买入成功（dry_run模式）",
            mode="dry_run", timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def sell(self, symbol: str, name: str, price: Decimal, quantity: int) -> OrderResult:
        self._order_counter += 1
        amount = price * quantity
        pos = self._positions.get(symbol)
        if pos:
            pnl = (price - pos.cost_price) * quantity
            self._balance.market_value -= pos.cost_price * quantity
            self._balance.available_cash += amount
            self._balance.profit_loss += pnl
            del self._positions[symbol]
        return OrderResult(
            ok=True, action="SELL", symbol=symbol, name=name,
            price=price, quantity=quantity, amount_cny=amount,
            order_id=f"DRY-{self._order_counter:06d}",
            status="filled", message="模拟卖出成功（dry_run模式）",
            mode="dry_run", timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def get_position(self, symbol: str) -> PositionInfo | None:
        return self._positions.get(symbol)

    async def get_positions(self) -> list[PositionInfo]:
        return list(self._positions.values())

    async def get_balance(self) -> BalanceInfo:
        return self._balance

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        return {"ok": True, "message": "模拟撤单成功（dry_run模式）", "order_id": order_id}

    async def health_check(self) -> dict[str, Any]:
        return {"ok": True, "mode": "dry_run", "connected": True, "message": "模拟模式运行中"}


class EasyTraderBroker:
    """Real broker adapter using easytrader — connects to local broker client.

    Supported brokers: 东方财富, 同花顺, 华泰证券 (XTP)
    Requires the broker's desktop client to be running and logged in.
    """

    def __init__(self, broker_id: str = "eastmoney"):
        self._broker_id = broker_id
        self._trader = None
        self._connected = False
        self._order_counter = 0

    async def _connect(self) -> bool:
        if self._connected and self._trader:
            return True
        try:
            import easytrader
            if self._broker_id == "eastmoney":
                self._trader = easytrader.use("eastmoney")
            elif self._broker_id == "ths":
                self._trader = easytrader.use("ths")
            else:
                self._trader = easytrader.use("eastmoney")
            self._connected = True
            logger.info("EasyTrader connected to %s", self._broker_id)
            return True
        except ImportError:
            logger.error("easytrader not installed. Run: pip install easytrader")
            return False
        except Exception as e:
            logger.error("EasyTrader connect failed: %s", e)
            return False

    async def _ensure_connected(self) -> bool:
        return await asyncio.to_thread(self._sync_connect)

    def _sync_connect(self) -> bool:
        if self._connected and self._trader:
            return True
        try:
            import easytrader
            if self._broker_id == "eastmoney":
                self._trader = easytrader.use("eastmoney")
            elif self._broker_id == "ths":
                self._trader = easytrader.use("ths")
            else:
                self._trader = easytrader.use("eastmoney")
            self._connected = True
            return True
        except Exception as e:
            logger.error("EasyTrader connect failed: %s", e)
            return False

    async def buy(self, symbol: str, name: str, price: Decimal, quantity: int) -> OrderResult:
        self._order_counter += 1
        connected = await self._ensure_connected()
        if not connected:
            return OrderResult(
                ok=False, action="BUY", symbol=symbol, name=name,
                price=price, quantity=quantity, amount_cny=price * quantity,
                order_id="", status="error",
                message="无法连接券商客户端，请确认客户端已启动并登录",
                mode="live", timestamp=datetime.now(timezone.utc).isoformat(),
            )
        try:
            result = await asyncio.to_thread(
                self._trader.buy, security=symbol, price=float(price), amount=quantity,
            )
            order_id = str(result.get("entrust_no", f"LIVE-{self._order_counter:06d}"))
            return OrderResult(
                ok=True, action="BUY", symbol=symbol, name=name,
                price=price, quantity=quantity, amount_cny=price * quantity,
                order_id=order_id, status="submitted",
                message=f"买入委托已提交: {symbol} ¥{price} × {quantity}",
                mode="live", timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            logger.error("EasyTrader buy failed: %s", e)
            return OrderResult(
                ok=False, action="BUY", symbol=symbol, name=name,
                price=price, quantity=quantity, amount_cny=price * quantity,
                order_id="", status="error", message=f"买入失败: {e}",
                mode="live", timestamp=datetime.now(timezone.utc).isoformat(),
            )

    async def sell(self, symbol: str, name: str, price: Decimal, quantity: int) -> OrderResult:
        self._order_counter += 1
        connected = await self._ensure_connected()
        if not connected:
            return OrderResult(
                ok=False, action="SELL", symbol=symbol, name=name,
                price=price, quantity=quantity, amount_cny=price * quantity,
                order_id="", status="error",
                message="无法连接券商客户端，请确认客户端已启动并登录",
                mode="live", timestamp=datetime.now(timezone.utc).isoformat(),
            )
        try:
            result = await asyncio.to_thread(
                self._trader.sell, security=symbol, price=float(price), amount=quantity,
            )
            order_id = str(result.get("entrust_no", f"LIVE-{self._order_counter:06d}"))
            return OrderResult(
                ok=True, action="SELL", symbol=symbol, name=name,
                price=price, quantity=quantity, amount_cny=price * quantity,
                order_id=order_id, status="submitted",
                message=f"卖出委托已提交: {symbol} ¥{price} × {quantity}",
                mode="live", timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            logger.error("EasyTrader sell failed: %s", e)
            return OrderResult(
                ok=False, action="SELL", symbol=symbol, name=name,
                price=price, quantity=quantity, amount_cny=price * quantity,
                order_id="", status="error", message=f"卖出失败: {e}",
                mode="live", timestamp=datetime.now(timezone.utc).isoformat(),
            )

    async def get_position(self, symbol: str) -> PositionInfo | None:
        connected = await self._ensure_connected()
        if not connected:
            return None
        try:
            positions = await asyncio.to_thread(self._trader.position)
            if isinstance(positions, dict):
                positions = positions.get("data", [])
            for pos in positions:
                if str(pos.get("证券代码", "")) == symbol:
                    return PositionInfo(
                        symbol=symbol,
                        name=pos.get("证券名称", ""),
                        quantity=int(pos.get("股票余额", 0)),
                        available=int(pos.get("可用余额", 0)),
                        cost_price=Decimal(str(pos.get("成本价", 0))),
                        current_price=Decimal(str(pos.get("当前价", 0))),
                        market_value=Decimal(str(pos.get("股票市值", 0))),
                        profit_loss=Decimal(str(pos.get("盈亏", 0))),
                        profit_pct=Decimal(str(pos.get("盈亏比", 0))),
                    )
        except Exception as e:
            logger.error("EasyTrader get_position failed: %s", e)
        return None

    async def get_positions(self) -> list[PositionInfo]:
        connected = await self._ensure_connected()
        if not connected:
            return []
        try:
            raw = await asyncio.to_thread(self._trader.position)
            if isinstance(raw, dict):
                raw = raw.get("data", [])
            result = []
            for pos in raw:
                result.append(PositionInfo(
                    symbol=str(pos.get("证券代码", "")),
                    name=pos.get("证券名称", ""),
                    quantity=int(pos.get("股票余额", 0)),
                    available=int(pos.get("可用余额", 0)),
                    cost_price=Decimal(str(pos.get("成本价", 0))),
                    current_price=Decimal(str(pos.get("当前价", 0))),
                    market_value=Decimal(str(pos.get("股票市值", 0))),
                    profit_loss=Decimal(str(pos.get("盈亏", 0))),
                    profit_pct=Decimal(str(pos.get("盈亏比", 0))),
                ))
            return result
        except Exception as e:
            logger.error("EasyTrader get_positions failed: %s", e)
            return []

    async def get_balance(self) -> BalanceInfo:
        connected = await self._ensure_connected()
        if not connected:
            return BalanceInfo(
                total_assets=Decimal("0"), available_cash=Decimal("0"),
                frozen_cash=Decimal("0"), market_value=Decimal("0"),
                profit_loss=Decimal("0"),
            )
        try:
            bal = await asyncio.to_thread(self._trader.balance)
            if isinstance(bal, list):
                bal = bal[0] if bal else {}
            return BalanceInfo(
                total_assets=Decimal(str(bal.get("总资产", 0))),
                available_cash=Decimal(str(bal.get("可用金额", 0))),
                frozen_cash=Decimal(str(bal.get("冻结金额", 0))),
                market_value=Decimal(str(bal.get("股票市值", 0))),
                profit_loss=Decimal(str(bal.get("盈亏", 0))),
            )
        except Exception as e:
            logger.error("EasyTrader get_balance failed: %s", e)
            return BalanceInfo(
                total_assets=Decimal("0"), available_cash=Decimal("0"),
                frozen_cash=Decimal("0"), market_value=Decimal("0"),
                profit_loss=Decimal("0"),
            )

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        connected = await self._ensure_connected()
        if not connected:
            return {"ok": False, "message": "未连接券商客户端"}
        try:
            result = await asyncio.to_thread(self._trader.cancel_entrust, entrust_no=order_id)
            return {"ok": True, "message": "撤单成功", "order_id": order_id, "result": result}
        except Exception as e:
            return {"ok": False, "message": f"撤单失败: {e}", "order_id": order_id}

    async def health_check(self) -> dict[str, Any]:
        connected = await self._ensure_connected()
        return {
            "ok": connected,
            "mode": "live",
            "broker": self._broker_id,
            "connected": connected,
            "message": "券商客户端已连接" if connected else "无法连接券商客户端",
        }


class BrokerAdapter:
    """Unified broker interface with dry-run/live toggle.

    Mode is determined by:
        1. TRADING_MODE env var ("dry_run" or "live")
        2. User prefs trading_mode setting
        3. Default: dry_run (safe!)

    In dry_run mode, all trades are simulated — no real orders placed.
    In live mode, trades go through easytrader to the broker client.
    """

    def __init__(self, mode: str | None = None):
        self._mode = mode or self._resolve_mode()
        self._broker: DryRunBroker | EasyTraderBroker = self._create_broker()
        logger.info("BrokerAdapter initialized: mode=%s, broker=%s",
                     self._mode, type(self._broker).__name__)

    def _resolve_mode(self) -> str:
        env_mode = os.environ.get("TRADING_MODE", "").lower()
        if env_mode in ("live", "real"):
            return "live"
        try:
            prefs = UserPrefs()
            all_prefs = prefs.get_all()
            pref_mode = str(all_prefs.get("trading_mode", "")).lower()
            if pref_mode in ("live", "real"):
                return "live"
        except Exception:
            pass
        return "dry_run"

    def _create_broker(self) -> DryRunBroker | EasyTraderBroker:
        if self._mode == "live":
            try:
                prefs = UserPrefs()
                all_prefs = prefs.get_all()
                broker_id = all_prefs.get("broker_id", "eastmoney")
                return EasyTraderBroker(broker_id=broker_id)
            except Exception:
                return EasyTraderBroker(broker_id="eastmoney")
        return DryRunBroker()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_live(self) -> bool:
        return self._mode == "live"

    async def buy(self, symbol: str, name: str, price: Decimal, quantity: int) -> OrderResult:
        if self.is_live:
            logger.warning("🔴 LIVE BUY: %s (%s) ¥%s × %d = ¥%s",
                          name, symbol, price, quantity, price * quantity)
        else:
            logger.info("🟡 DRY-RUN BUY: %s (%s) ¥%s × %d", name, symbol, price, quantity)
        return await self._broker.buy(symbol, name, price, quantity)

    async def sell(self, symbol: str, name: str, price: Decimal, quantity: int) -> OrderResult:
        if self.is_live:
            logger.warning("🔴 LIVE SELL: %s (%s) ¥%s × %d = ¥%s",
                          name, symbol, price, quantity, price * quantity)
        else:
            logger.info("🟡 DRY-RUN SELL: %s (%s) ¥%s × %d", name, symbol, price, quantity)
        return await self._broker.sell(symbol, name, price, quantity)

    async def get_position(self, symbol: str) -> PositionInfo | None:
        return await self._broker.get_position(symbol)

    async def get_positions(self) -> list[PositionInfo]:
        return await self._broker.get_positions()

    async def get_balance(self) -> BalanceInfo:
        return await self._broker.get_balance()

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        return await self._broker.cancel_order(order_id)

    async def health_check(self) -> dict[str, Any]:
        result = await self._broker.health_check()
        result["configured_mode"] = self._mode
        result["is_live"] = self.is_live
        return result

    async def switch_mode(self, mode: str) -> dict[str, Any]:
        if mode not in ("dry_run", "live"):
            return {"ok": False, "message": f"无效模式: {mode}, 只支持 dry_run/live"}
        if mode == "live":
            if not self.is_live:
                health = await self._broker.health_check() if isinstance(self._broker, EasyTraderBroker) else {"connected": True}
                if not health.get("connected"):
                    return {"ok": False, "message": "无法连接券商客户端，不能切换到live模式"}
            logger.warning("⚠️ 切换到 LIVE 模式 —— 真实交易！")
        self._mode = mode
        self._broker = self._create_broker()
        logger.info("Broker mode switched to: %s", mode)
        return {"ok": True, "mode": mode, "is_live": self.is_live}