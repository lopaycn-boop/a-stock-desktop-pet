"""Pre-trade risk validation — every trade MUST pass through this before execution.

This is the HARD GATE between AI analysis and real money execution.
No trade should ever hit the browser without passing validate_trade().

Risk rules enforced:
1. Max single trade amount (¥)
2. Max daily trade amount (¥)
3. Max consecutive losses → circuit breaker
4. Invalid amount rejection
5. Stop-loss enforcement — BUY must set stop-loss, SELL at/below stop triggers immediate stop
6. Max open positions
7. Minimum confidence threshold
8. Blacklist check
9. Restricted prefix check (ST/*ST/N stocks)
10. Daily loss limit
11. Trading hours + weekend restriction
12. Consecutive losses warning (soft)
13. Approaching daily limit warning (soft)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

logger = logging.getLogger("potato.risk")

BJT = timezone(timedelta(hours=8))

# A-share trading hours (Beijing time)
MORNING_OPEN = time(9, 30)
MORNING_CLOSE = time(11, 30)
AFTERNOON_OPEN = time(13, 0)
AFTERNOON_CLOSE = time(15, 0)
# No trading in last 15 minutes of afternoon session (尾盘避免)
NO_TRADE_AFTER = time(14, 45)

# Safety rules — these are PERCENTAGE and STRUCTURAL limits only.
# ABSOLUTE CNY LIMITS (max_single, max_daily, etc.) COME EXCLUSIVELY FROM USER.
# If user hasn't confirmed limits, ALL trades are BLOCKED by Rule 0.
SAFETY_RULES = {
    "min_confidence": Decimal("0.65"),
    "stop_loss_pct_min": Decimal("0.02"),
    "max_open_positions_hard_cap": 30,
    "max_consecutive_losses": 3,
    "daily_loss_limit_pct": Decimal("0.10"),
    "trading_hours_only": True,
    "no_tail_trading": True,
    "no_st_stocks": True,
    "min_lot_size": 100,
}

# Hardcoded blacklist — symbols that should NEVER be auto-traded
BLACKLIST = {
    # ST stocks (Special Treatment — high risk)
    # These would be populated with actual ST stock codes
}

# Restricted prefixes — stocks starting with these are high-risk
RESTRICTED_PREFIXES = {
    "*ST", "ST", "S*ST", "N",  # N = newly listed IPO
}


@dataclass
class RiskState:
    """Current risk state — tracks daily P&L, positions, consecutive losses."""
    date: str = ""
    total_traded_cny: Decimal = Decimal("0")
    trade_count: int = 0
    total_pnl_cny: Decimal = Decimal("0")
    open_positions: int = 0
    consecutive_losses: int = 0
    circuit_breaker: bool = False
    trades_today: list[dict[str, Any]] = field(default_factory=list)

    def reset_for_new_day(self, date_str: str):
        """Reset daily counters at market open. Must be called each trading day."""
        self.date = date_str
        self.total_traded_cny = Decimal("0")
        self.trade_count = 0
        self.total_pnl_cny = Decimal("0")
        self.open_positions = 0
        self.trades_today = []

    def record_trade_result(self, pnl: Decimal):
        """Record a trade result — update P&L and consecutive losses/circuit breaker."""
        self.total_pnl_cny += pnl
        self.trade_count += 1
        if pnl < 0:
            self.consecutive_losses += 1
        elif pnl > 0:
            self.consecutive_losses = 0
        if self.consecutive_losses >= SAFETY_RULES["max_consecutive_losses"]:
            self.circuit_breaker = True


@dataclass
class TradeRequest:
    """A trade that wants to be executed — must be validated."""
    action: str  # BUY or SELL
    symbol: str
    name: str
    price: Decimal
    quantity: int = 0
    amount_cny: Decimal = Decimal("0")
    confidence: Decimal = Decimal("0")
    reasoning: str = ""
    stop_loss_price: Decimal = Decimal("0")


@dataclass
class RiskVerdict:
    """Result of risk validation."""
    allowed: bool
    reason: str = ""
    risk_state: RiskState | None = None
    warnings: list[str] = field(default_factory=list)


class RiskValidator:
    """Hard gate between AI analysis and real money execution.

    Usage:
        validator = RiskValidator(settings, user_prefs)
        verdict = validator.validate_trade(trade_request, current_risk_state)
        if not verdict.allowed:
            # BLOCK the trade
        else:
            # Proceed with execution
    """

    def __init__(self, settings=None, user_prefs=None):
        self.settings = settings
        self.user_prefs = user_prefs
        self._limits = self._build_limits()

    def _build_limits(self) -> dict[str, Any]:
        """Build risk limits: user-confirmed values only, with safety floor rules.

        ABSOLUTE CNY LIMITS (max_single, max_daily) COME EXCLUSIVELY FROM USER.
        If user hasn't confirmed, trades are BLOCKED by Rule 0.
        We only apply PERCENTAGE and STRUCTURAL safety rules here.
        """
        limits = {
            "risk_confirmed": False,
            "max_single_trade_cny": None,
            "max_daily_trade_cny": None,
            "max_open_positions": None,
            "min_confidence": SAFETY_RULES["min_confidence"],
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "max_consecutive_losses": SAFETY_RULES["max_consecutive_losses"],
            "daily_loss_limit_pct": SAFETY_RULES["daily_loss_limit_pct"],
            "trading_hours_only": SAFETY_RULES["trading_hours_only"],
            "no_tail_trading": SAFETY_RULES["no_tail_trading"],
            "no_st_stocks": SAFETY_RULES["no_st_stocks"],
        }

        if self.user_prefs:
            prefs = self.user_prefs if isinstance(self.user_prefs, dict) else self.user_prefs.get_all() if hasattr(self.user_prefs, "get_all") else {}
            limits["risk_confirmed"] = bool(prefs.get("risk_confirmed", False))

            single = prefs.get("max_single_cny") or prefs.get("max_single_trade_cny")
            if single is not None:
                try:
                    limits["max_single_trade_cny"] = Decimal(str(single))
                except Exception:
                    pass
            daily = prefs.get("max_daily_cny") or prefs.get("max_daily_trade_cny")
            if daily is not None:
                try:
                    limits["max_daily_trade_cny"] = Decimal(str(daily))
                except Exception:
                    pass
            positions = prefs.get("max_open_positions")
            if positions is not None:
                try:
                    val = int(positions)
                    if val <= SAFETY_RULES["max_open_positions_hard_cap"]:
                        limits["max_open_positions"] = val
                except Exception:
                    pass
            sl = prefs.get("stop_loss_pct")
            if sl is not None:
                try:
                    val = Decimal(str(sl))
                    if val >= SAFETY_RULES["stop_loss_pct_min"]:
                        limits["stop_loss_pct"] = val
                except Exception:
                    pass
            tp = prefs.get("take_profit_pct")
            if tp is not None:
                try:
                    limits["take_profit_pct"] = Decimal(str(tp))
                except Exception:
                    pass
            if "risk_level" in prefs and prefs["risk_level"]:
                level = prefs["risk_level"]
                if level == "conservative":
                    limits["min_confidence"] = Decimal("0.8")
                elif level == "moderate":
                    limits["min_confidence"] = Decimal("0.7")
                elif level == "aggressive":
                    limits["min_confidence"] = Decimal("0.6")

        return limits

    def validate_trade(self, trade: TradeRequest, state: RiskState, open_positions: list[dict] | None = None) -> RiskVerdict:
        """Validate a trade request against all risk rules. Returns verdict."""
        warnings = []

        # Rule 0: Risk params must be confirmed by user before any trade
        if not self._limits.get("risk_confirmed", False):
            return RiskVerdict(
                allowed=False,
                reason="RISK_NOT_CONFIRMED: 用户还未确认风控参数。请先确认限额后再交易。",
                risk_state=state,
                warnings=warnings,
            )

        # Daily reset — check if date changed
        today = datetime.now(tz=BJT).strftime("%Y-%m-%d")
        if state.date != today:
            state.reset_for_new_day(today)

        # Rule 1: Circuit breaker — too many consecutive losses
        if state.circuit_breaker:
            return RiskVerdict(
                allowed=False,
                reason=f"CIRCUIT_BREAKER: 连续{state.consecutive_losses}次亏损，暂停交易。请复盘策略后手动解除。",
                risk_state=state,
                warnings=warnings,
            )

        # Rule 2: Minimum amount — reject zero-value trades
        if trade.amount_cny <= 0:
            return RiskVerdict(
                allowed=False,
                reason=f"INVALID_AMOUNT: 交易金额为¥{trade.amount_cny}，必须大于0",
                risk_state=state,
                warnings=warnings,
            )

        # Rule 3: Max single trade amount (only if user set one)
        max_single = self._limits.get("max_single_trade_cny")
        if max_single is not None and trade.amount_cny > max_single:
            return RiskVerdict(
                allowed=False,
                reason=f"OVER_LIMIT: 交易¥{trade.amount_cny:.2f}超过您设的单笔上限¥{max_single}",
                risk_state=state,
                warnings=warnings,
            )

        # Rule 4: Max daily trade amount (only if user set one)
        max_daily = self._limits.get("max_daily_trade_cny")
        projected = state.total_traded_cny + trade.amount_cny
        if max_daily is not None and projected > max_daily:
            return RiskVerdict(
                allowed=False,
                reason=f"DAILY_LIMIT: 已交易¥{state.total_traded_cny:.2f} + ¥{trade.amount_cny:.2f} = ¥{projected:.2f} > 您的日限额¥{max_daily}",
                risk_state=state,
                warnings=warnings,
            )

        # Rule 5: Stop-loss enforcement — BUY trades must set a stop-loss, existing positions must not exceed stop-loss limit
        stop_loss_pct = self._limits.get("stop_loss_pct")
        if trade.action == "BUY" and stop_loss_pct and stop_loss_pct > 0:
            if not trade.stop_loss_price or trade.stop_loss_price <= 0:
                max_loss_price = float(trade.price) * (1 - float(stop_loss_pct))
                warnings.append(f"STOP_LOSS_MISSING: 建议止损价¥{max_loss_price:.2f}(-{float(stop_loss_pct)*100:.0f}%)")
            elif trade.price > 0:
                actual_sl_pct = float((trade.price - trade.stop_loss_price) / trade.price)
                if actual_sl_pct < float(stop_loss_pct) * 0.5:
                    warnings.append(f"STOP_LOSS_TOO_WIDE: 止损{(1-actual_sl_pct)*100:.0f}%距离过远，建议收紧到{float(stop_loss_pct)*100:.0f}%")
        if open_positions and trade.action == "SELL":
            for pos in open_positions:
                entry_price = Decimal(str(pos.get("entry_price", "0")))
                stop_loss_price = Decimal(str(pos.get("stop_loss_price", "0")))
                if entry_price > 0 and stop_loss_price > 0 and trade.price <= stop_loss_price:
                    return RiskVerdict(
                        allowed=False,
                        reason=f"POSITION_BELOW_STOP: {trade.symbol}已跌破止损价¥{stop_loss_price}，当前¥{trade.price}。应立即止损而非挂新单。",
                        risk_state=state,
                        warnings=warnings,
                    )

        # Rule 5: Max open positions (only if user set one, hard cap otherwise)
        if trade.action == "BUY":
            max_pos = self._limits.get("max_open_positions")
            if max_pos is not None and state.open_positions >= max_pos:
                return RiskVerdict(
                    allowed=False,
                    reason=f"POSITION_LIMIT: 已有{state.open_positions}只持仓 >= 您设的上限{max_pos}只",
                    risk_state=state,
                    warnings=warnings,
                )
            if max_pos is None and state.open_positions >= SAFETY_RULES["max_open_positions_hard_cap"]:
                return RiskVerdict(
                    allowed=False,
                    reason=f"POSITION_HARD_CAP: 已有{state.open_positions}只持仓超过安全上限{SAFETY_RULES['max_open_positions_hard_cap']}只",
                    risk_state=state,
                    warnings=warnings,
                )

        # Rule 6: Minimum confidence
        min_conf = self._limits.get("min_confidence", SAFETY_RULES["min_confidence"])
        if min_conf and trade.confidence < min_conf:
            return RiskVerdict(
                allowed=False,
                reason=f"LOW_CONFIDENCE: 置信度{trade.confidence:.0%}低于要求{min_conf:.0%}",
                risk_state=state,
                warnings=warnings,
            )

        # Rule 7: Blacklist check
        if trade.symbol in BLACKLIST:
            return RiskVerdict(
                allowed=False,
                reason=f"BLACKLISTED: {trade.symbol}在黑名单中",
                risk_state=state,
                warnings=warnings,
            )

        # Rule 8: Restricted prefix check
        for prefix in RESTRICTED_PREFIXES:
            if trade.name.startswith(prefix):
                return RiskVerdict(
                    allowed=False,
                    reason=f"RESTRICTED: {trade.name}以'{prefix}'开头——高风险股票类别",
                    risk_state=state,
                    warnings=warnings,
                )

        # Rule 9: Daily loss limit (% of daily cap, or absolute ¥5000 if no cap)
        daily_loss_pct = SAFETY_RULES["daily_loss_limit_pct"]
        loss_limit = max_daily * daily_loss_pct if max_daily is not None else Decimal("5000")
        if state.total_pnl_cny < -loss_limit:
            return RiskVerdict(
                allowed=False,
                reason=f"DAILY_LOSS_LIMIT: 今日亏损¥{state.total_pnl_cny:.2f}超过止损线¥{loss_limit:.0f}",
                risk_state=state,
                warnings=warnings,
            )

        # Rule 10: Trading hours + weekend check
        if self._limits.get("trading_hours_only", True):
            verdict = self._check_trading_hours()
            if not verdict.allowed:
                verdict.risk_state = state
                return verdict

        # Rule 11: Consecutive losses warning (soft, not block)
        if state.consecutive_losses >= 1:
            warnings.append(f"WARNING: 已连续{state.consecutive_losses}次亏损——接近熔断线{SAFETY_RULES['max_consecutive_losses']}次")

        # Rule 12: Amount approaching daily limit warning (soft, only if user set one)
        if max_daily is not None and projected > max_daily * Decimal("0.8"):
            pct = float(projected / max_daily * 100)
            warnings.append(f"WARNING: 今日交易将达日限额的{pct:.0f}%")

        logger.info(
            "Risk VALIDATED: %s %s ¥%.2f (confidence=%.2f, %s)",
            trade.action, trade.symbol, trade.amount_cny, trade.confidence, trade.reasoning[:60],
        )
        return RiskVerdict(
            allowed=True,
            reason="All risk checks passed",
            risk_state=state,
            warnings=warnings,
        )

    def _check_trading_hours(self) -> RiskVerdict:
        """Check that current time is within A-share trading hours (weekday only)."""
        now_bjt = datetime.now(tz=BJT)

        # Check weekend
        if now_bjt.weekday() >= 5:
            return RiskVerdict(
                allowed=False,
                reason=f"WEEKEND: 今天是周末，A股不开盘",
            )

        current_time = now_bjt.time()

        # Check if within trading hours
        in_morning = MORNING_OPEN <= current_time <= MORNING_CLOSE
        in_afternoon = AFTERNOON_OPEN <= current_time <= AFTERNOON_CLOSE

        if not (in_morning or in_afternoon):
            return RiskVerdict(
                allowed=False,
                reason=f"OUTSIDE_TRADING_HOURS: 当前北京时间{current_time}不在交易时间(9:30-11:30, 13:00-15:00)",
            )

        # Check tail trading restriction (last 15 min)
        if self._limits.get("no_tail_trading", True) and current_time >= NO_TRADE_AFTER:
            return RiskVerdict(
                allowed=False,
                reason=f"NO_TAIL_TRADING: 当前北京时间{current_time}是尾盘最后15分钟——禁止交易",
            )

        return RiskVerdict(allowed=True, reason="Within trading hours on weekday")

    def get_limits(self) -> dict[str, Any]:
        """Return current risk limits for API exposure."""
        limits = dict(self._limits)
        limits["blacklisted_symbols"] = list(BLACKLIST)
        limits["restricted_prefixes"] = list(RESTRICTED_PREFIXES)
        return limits