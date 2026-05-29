"""Autonomous trade executor — 小土豆自主操盘执行器.

Executes validated trade decisions through browser automation or Bytebot desktop.
Every execution step is reported to the frontend for real-time visibility.

Flow:
    1. Receive validated TradeDecision from risk validator
    2. Open trading platform (desktop app or browser)
    3. Navigate to stock page
    4. Read current price, confirm within acceptable range
    5. Fill order form (buy/sell, price, quantity)
    6. Screenshot before confirm
    7. Confirm order
    8. Screenshot after confirm
    9. Report result to frontend
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from potato.risk import RiskValidator, RiskState, TradeRequest
from potato.trading.analyzer import (
    fetch_realtime_quote,
    fetch_kline,
    technical_summary,
)
from potato.trading.broker import BrokerAdapter
from potato.trading.journal import TradeJournal
from potato.user_prefs import UserPrefs

logger = logging.getLogger("potato.trading.executor")


@dataclass
class TradeDecision:
    action: str
    symbol: str
    name: str
    price: Decimal
    quantity: int
    amount_cny: Decimal
    confidence: Decimal
    reasoning: str
    entry_price: str = ""
    target_price: str = ""
    stop_loss: str = ""
    platform_id: str = ""


@dataclass
class ExecutionStep:
    step: str
    status: str  # running, done, error, blocked
    detail: str = ""
    screenshot_b64: str = ""


class TradeExecutor:
    """Execute trades autonomously via browser or Bytebot.

    Every step is broadcast to the frontend so the user can see
    exactly what the AI is doing in real time.
    """

    def __init__(self, send_func=None, broker: BrokerAdapter | None = None):
        self.send_func = send_func
        self._broker = broker or BrokerAdapter()
        self._risk_state = RiskState(date=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        self.journal = TradeJournal()
        self._refresh_validator()

    def _refresh_validator(self):
        """Rebuild RiskValidator with latest user prefs so risk_confirmed is current."""
        try:
            prefs = UserPrefs()
            self.risk_validator = RiskValidator(user_prefs=prefs.get_all())
        except Exception:
            self.risk_validator = RiskValidator()

    async def _emit(self, event_type: str, data: dict):
        if self.send_func:
            await self.send_func(event_type, data)

    async def _emit_step(self, step: str, status: str, detail: str = "", screenshot: bytes | None = None):
        data = {"step": step, "status": status, "detail": detail}
        if screenshot:
            data["screenshot_b64"] = base64.b64encode(screenshot).decode()
        await self._emit("trade_step", data)

    def _update_risk_state(self, trade: TradeDecision):
        self._risk_state.trade_count += 1
        self._risk_state.total_traded_cny += trade.amount_cny

    async def validate_and_execute(self, trade: TradeDecision) -> dict[str, Any]:
        self._risk_state.date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._refresh_validator()

        await self._emit_step("risk_check", "running", f"风控检查: {trade.action} {trade.symbol} ¥{trade.amount_cny}")
        req = TradeRequest(
            action=trade.action,
            symbol=trade.symbol,
            name=trade.name,
            price=trade.price,
            quantity=trade.quantity,
            amount_cny=trade.amount_cny,
            confidence=trade.confidence,
            reasoning=trade.reasoning,
            stop_loss_price=Decimal(str(trade.stop_loss)) if trade.stop_loss else Decimal("0"),
        )
        verdict = self.risk_validator.validate_trade(req, self._risk_state, open_positions=self.journal.get_open_positions_summary())

        if not verdict.allowed:
            await self._emit_step("risk_check", "blocked", f"风控拦截: {verdict.reason}")
            await self._emit("trade_result", {
                "ok": False,
                "action": trade.action,
                "symbol": trade.symbol,
                "reason": verdict.reason,
                "warnings": verdict.warnings,
            })
            return {"ok": False, "reason": verdict.reason, "warnings": verdict.warnings}

        await self._emit_step("risk_check", "done", f"风控通过 ✓ {', '.join(verdict.warnings) if verdict.warnings else ''}")

        real_price = await self._verify_price(trade)
        if real_price is not None:
            price_diff_pct = abs(float(trade.price) - real_price) / real_price
            if price_diff_pct > 0.03:
                await self._emit_step("price_verify", "error", f"价格偏差过大: 分析价{trade.price} vs 实时价{real_price} ({price_diff_pct:.1%})")
                return {"ok": False, "reason": f"价格偏差{price_diff_pct:.1%}，建议价{trade.price} vs 实时价{real_price}"}
            trade.price = Decimal(str(real_price))
            await self._emit_step("price_verify", "done", f"实时价确认: ¥{real_price}")
        else:
            await self._emit_step("price_verify", "done", "无法获取实时价，使用分析价继续")

        self._update_risk_state(trade)

        platform = trade.platform_id or "eastmoney"
        result = await self._execute_on_platform(trade, platform)
        return result

    async def _verify_price(self, trade: TradeDecision) -> float | None:
        try:
            quote = await fetch_realtime_quote(trade.symbol)
            if quote and quote.get("price"):
                return quote["price"]
        except Exception as e:
            logger.warning("Price verification failed: %s", e)
        return None

    async def _execute_on_platform(self, trade: TradeDecision, platform_id: str) -> dict[str, Any]:
        mode_label = "真实交易" if self._broker.is_live else "模拟交易"
        action_label = "买入" if trade.action == "BUY" else "卖出"

        await self._emit_step("broker_connect", "running", f"连接券商（{mode_label}模式）...")
        health = await self._broker.health_check()
        if not health.get("ok"):
            await self._emit_step("broker_connect", "error", f"券商连接失败: {health.get('message', '未知')}")
            return {"ok": False, "reason": f"券商连接失败: {health.get('message', '')}"}
        await self._emit_step("broker_connect", "done", f"券商已连接（{mode_label}模式）")

        await self._emit_step("order_submit", "running",
                              f"{action_label} {trade.name}({trade.symbol}) ¥{trade.price} × {trade.quantity}股 = ¥{trade.amount_cny}")

        if trade.action == "BUY":
            order = await self._broker.buy(
                symbol=trade.symbol, name=trade.name,
                price=trade.price, quantity=trade.quantity,
            )
        elif trade.action == "SELL":
            order = await self._broker.sell(
                symbol=trade.symbol, name=trade.name,
                price=trade.price, quantity=trade.quantity,
            )
        else:
            await self._emit_step("order_submit", "error", f"未知操作: {trade.action}")
            return {"ok": False, "reason": f"未知操作: {trade.action}"}

        if not order.ok:
            await self._emit_step("order_submit", "error", f"下单失败: {order.message}")
            return {"ok": False, "reason": order.message}

        await self._emit_step("order_submit", "done",
                              f"{action_label}委托成功: {trade.name}({trade.symbol}) ¥{trade.amount_cny} [{order.order_id}]")

        await self._emit("trade_result", {
            "ok": True,
            "action": trade.action,
            "symbol": trade.symbol,
            "name": trade.name,
            "price": str(trade.price),
            "quantity": trade.quantity,
            "amount_cny": str(trade.amount_cny),
            "confidence": str(trade.confidence),
            "reasoning": trade.reasoning,
            "entry_price": trade.entry_price,
            "target_price": trade.target_price,
            "stop_loss": trade.stop_loss,
            "platform": platform_id,
            "order_id": order.order_id,
            "mode": order.mode,
            "timestamp": order.timestamp or datetime.now(timezone.utc).isoformat(),
        })

        logger.info("Trade executed [%s]: %s %s ¥%s (confidence=%.2f, mode=%s, order_id=%s)",
                     order.mode, trade.action, trade.symbol, trade.amount_cny,
                     float(trade.confidence), order.mode, order.order_id)

        if trade.action == "BUY":
            self.journal.record_entry(
                symbol=trade.symbol,
                name=trade.name,
                direction="BUY",
                price=trade.price,
                quantity=trade.quantity,
                amount_cny=trade.amount_cny,
                target_price=trade.target_price,
                stop_loss_price=trade.stop_loss,
                confidence=trade.confidence,
                thesis=trade.reasoning,
            )
        elif trade.action == "SELL":
            open_pos = None
            for tid, pos in list(self.journal._open_positions.items()):
                if pos.symbol == trade.symbol:
                    open_pos = pos
                    break
            if open_pos:
                self.journal.record_exit(
                    trade_id=open_pos.id,
                    exit_price=trade.price,
                    exit_reason="auto_sell",
                )
            else:
                self.journal.record_entry(
                    symbol=trade.symbol,
                    name=trade.name,
                    direction="BUY",
                    price=trade.price,
                    quantity=trade.quantity,
                    amount_cny=trade.amount_cny,
                    target_price=trade.target_price,
                    stop_loss_price=trade.stop_loss,
                    confidence=trade.confidence,
                    thesis=trade.reasoning,
                )

        self._risk_state.consecutive_losses = self.journal.get_consecutive_losses()

        return {
            "ok": True,
            "action": trade.action,
            "symbol": trade.symbol,
            "name": trade.name,
            "amount_cny": str(trade.amount_cny),
            "order_id": order.order_id,
            "mode": order.mode,
        }

    async def execute_bytebot_desktop_trade(
        self, trade: TradeDecision, bytebot_client,
    ) -> dict[str, Any]:
        bytebot_avail = await bytebot_client.is_desktop_available()

        mode_label = "真实交易" if self._broker.is_live else "模拟交易"
        action_label = "买入" if trade.action == "BUY" else "卖出"

        if not bytebot_avail and self._broker.is_live:
            await self._emit_step("bytebot_connect", "running", "Bytebot桌面不可用，直接通过券商API下单...")
            result = await self._execute_on_platform(trade, trade.platform_id or "eastmoney")
            return result

        if bytebot_avail:
            await self._emit_step("bytebot_connect", "running", "连接Bytebot桌面...")
            await self._emit_step("bytebot_connect", "done", "Bytebot桌面已连接")

            await self._emit_step("open_platform", "running", f"在Bytebot桌面打开 {trade.platform_id or 'eastmoney'}")

            try:
                result = await bytebot_client.computer_use("application", application="google-chrome")
                if not result.get("ok"):
                    return {"ok": False, "reason": f"无法打开浏览器: {result.get('error')}"}
                await asyncio.sleep(1)

                from potato.browser.platforms import BUILTIN_PLATFORMS
                platform = BUILTIN_PLATFORMS.get(trade.platform_id or "eastmoney")
                if platform:
                    await self._emit_step("navigate", "running", f"导航到 {platform.name}")
                    await bytebot_client.computer_use("type_text", text=platform.url)
                    await bytebot_client.computer_use("type_text", text="\n")
                    await asyncio.sleep(2)

                    for _ in range(10):
                        scr = await bytebot_client.computer_use("screenshot")
                        await asyncio.sleep(1)
                        if scr.get("ok"):
                            break

                screenshot = await bytebot_client.computer_use("screenshot")
                if screenshot.get("image"):
                    await self._emit("trade_screenshot", {
                        "step": "platform_loaded",
                        "image": screenshot["image"],
                    })
            except Exception as e:
                await self._emit_step("bytebot_connect", "error", f"Bytebot操作失败: {e}")

        if self._broker.is_live:
            broker_result = await self._execute_on_platform(trade, trade.platform_id or "eastmoney")
            return broker_result

        await self._emit_step("trade_action", "running",
                               f"{action_label}: {trade.name}({trade.symbol}) [{mode_label}]")
        result = await self._execute_on_platform(trade, trade.platform_id or "eastmoney")
        return result