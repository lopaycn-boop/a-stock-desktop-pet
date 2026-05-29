"""Trade journal & review engine — 小土豆专业复盘系统.

Every professional trader reviews every trade. This engine:
1. Records every trade with full context (thesis, entry, target, stop, market condition)
2. Tracks open positions & monitors stop-loss / take-profit in real-time
3. Computes P&L on close — realized & unrealized
4. Generates daily/weekly reviews with win rate, profit factor, max drawdown
5. AI-driven post-trade reflection: "what went right, what went wrong, what to change"
6. Feeds review outcomes back into future analysis quality

This is NOT a toy. This is how real traders improve.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from potato.trading.analyzer import fetch_realtime_quote

logger = logging.getLogger("potato.trading.journal")

BJT = timezone(timedelta(hours=8))
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
JOURNAL_DIR = DATA_DIR / "journal"


@dataclass
class TradeRecord:
    """A single trade — recorded at entry, updated at exit."""

    id: str = ""
    symbol: str = ""
    name: str = ""
    direction: str = ""

    entry_time: str = ""
    entry_price: Decimal = Decimal("0")
    quantity: int = 0
    amount_cny: Decimal = Decimal("0")

    target_price: Decimal = Decimal("0")
    stop_loss_price: Decimal = Decimal("0")
    confidence: Decimal = Decimal("0")

    thesis: str = ""
    market_context: str = ""
    strategy_tags: list[str] = field(default_factory=list)

    exit_time: str = ""
    exit_price: Decimal = Decimal("0")
    exit_reason: str = ""
    realized_pnl: Decimal = Decimal("0")
    realized_pnl_pct: Decimal = Decimal("0")
    hold_duration_minutes: int = 0

    prediction_correct: bool | None = None
    stop_hit: bool = False
    target_hit: bool = False

    ai_review: str = ""
    user_notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = str(v)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> TradeRecord:
        for k in ("entry_price", "target_price", "stop_loss_price",
                   "amount_cny", "confidence", "realized_pnl",
                   "realized_pnl_pct", "exit_price"):
            if k in d and d[k] is not None:
                try:
                    d[k] = Decimal(str(d[k]))
                except Exception:
                    d[k] = Decimal("0")
        if "quantity" in d and d["quantity"] is not None:
            d["quantity"] = int(d["quantity"])
        if "hold_duration_minutes" in d and d["hold_duration_minutes"] is not None:
            d["hold_duration_minutes"] = int(d["hold_duration_minutes"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class DailyReview:
    """End-of-day review — the core of 复盘."""

    date: str = ""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    profit_factor: Decimal = Decimal("0")
    max_single_win: Decimal = Decimal("0")
    max_single_loss: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")

    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: Decimal = Decimal("0")
    short_win_rate: Decimal = Decimal("0")

    best_trade_id: str = ""
    worst_trade_id: str = ""
    ai_summary: str = ""
    ai_lessons: list[str] = field(default_factory=list)
    strategy_adjustments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = str(v)
        return d


@dataclass
class PositionStatus:
    """Open position being monitored."""

    symbol: str = ""
    name: str = ""
    direction: str = ""
    entry_price: Decimal = Decimal("0")
    quantity: int = 0
    target_price: Decimal = Decimal("0")
    stop_loss_price: Decimal = Decimal("0")
    current_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    unrealized_pnl_pct: Decimal = Decimal("0")
    distance_to_target_pct: Decimal = Decimal("0")
    distance_to_stop_pct: Decimal = Decimal("0")
    held_since: str = ""
    trade_id: str = ""


def _now_bjt() -> datetime:
    return datetime.now(tz=BJT)


class TradeJournal:
    """Persistent trade journal — the backbone of 复盘.

    - Records every trade at entry with full thesis
    - Tracks open positions, monitors stops/targets
    - Computes P&L on exit
    - Generates daily reviews with pro metrics
    - AI reflection engine: what went right, what went wrong, what to change
    """

    def __init__(self):
        self._trades: dict[str, TradeRecord] = {}
        self._open_positions: dict[str, TradeRecord] = {}
        self._equity_curve: list[dict] = []
        self._running_pnl: Decimal = Decimal("0")
        self._peak_pnl: Decimal = Decimal("0")
        self._max_drawdown_pct: Decimal = Decimal("0")
        self._consecutive_losses: int = 0
        self._load()

    def _load(self):
        JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        trades_file = JOURNAL_DIR / "trades.json"
        tmp_file = JOURNAL_DIR / "trades.json.tmp"

        # Crash recovery: if tmp exists and trades.json doesn't, recover from tmp
        if tmp_file.exists() and not trades_file.exists():
            logger.warning("Found trades.json.tmp without trades.json — recovering from backup")
            try:
                tmp_file.replace(trades_file)
            except Exception as e:
                logger.error("Failed to recover journal from tmp: %s", e)

        if trades_file.exists():
            try:
                data = json.loads(trades_file.read_text(encoding="utf-8"))
                for td in data.get("closed", []):
                    rec = TradeRecord.from_dict(td)
                    self._trades[rec.id] = rec
                for td in data.get("open", []):
                    rec = TradeRecord.from_dict(td)
                    self._open_positions[rec.id] = rec
                    self._trades[rec.id] = rec
                self._running_pnl = Decimal(str(data.get("running_pnl", "0")))
                self._peak_pnl = Decimal(str(data.get("peak_pnl", "0")))
                self._max_drawdown_pct = Decimal(str(data.get("max_drawdown_pct", "0")))
                self._consecutive_losses = data.get("consecutive_losses", 0)
                logger.info("Loaded %d closed + %d open trades from journal",
                            len(data.get("closed", [])),
                            len(data.get("open", [])))
            except Exception as e:
                logger.warning("Failed to load journal: %s", e)

    def _save(self):
        JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        closed = [t.to_dict() for t in self._trades.values() if t.exit_time]
        open_list = [t.to_dict() for t in self._open_positions.values()]
        data = {
            "closed": closed,
            "open": open_list,
            "running_pnl": str(self._running_pnl),
            "peak_pnl": str(self._peak_pnl),
            "max_drawdown_pct": str(self._max_drawdown_pct),
            "consecutive_losses": self._consecutive_losses,
        }
        tmp = JOURNAL_DIR / "trades.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        target = JOURNAL_DIR / "trades.json"
        tmp.replace(target)

    def record_entry(
        self,
        symbol: str,
        name: str,
        direction: str,
        price: Decimal,
        quantity: int,
        amount_cny: Decimal,
        target_price: str | Decimal = "0",
        stop_loss_price: str | Decimal = "0",
        confidence: Decimal = Decimal("0"),
        thesis: str = "",
        market_context: str = "",
        strategy_tags: list[str] | None = None,
    ) -> TradeRecord:
        """Record a trade at entry time with full thesis context."""
        now = _now_bjt()
        trade_id = f"{symbol}_{direction}_{now.strftime('%Y%m%d%H%M%S')}"

        tp = Decimal(str(target_price)) if target_price else Decimal("0")
        sl = Decimal(str(stop_loss_price)) if stop_loss_price else Decimal("0")

        rec = TradeRecord(
            id=trade_id,
            symbol=symbol,
            name=name,
            direction=direction,
            entry_time=now.isoformat(),
            entry_price=price,
            quantity=quantity,
            amount_cny=amount_cny,
            target_price=tp,
            stop_loss_price=sl,
            confidence=confidence,
            thesis=thesis[:2000],
            market_context=market_context[:1000],
            strategy_tags=strategy_tags or [],
        )
        self._trades[trade_id] = rec
        self._open_positions[trade_id] = rec
        try:
            self._save()
        except Exception:
            logger.error("Journal save failed, rolling back entry: %s", trade_id)
            del self._trades[trade_id]
            del self._open_positions[trade_id]
            raise
        logger.info("Journal entry: %s %s %s @ ¥%s (target=%s, stop=%s)",
                    direction, symbol, name, price, tp, sl)
        return rec

    def record_exit(
        self,
        trade_id: str,
        exit_price: Decimal,
        exit_reason: str = "",
    ) -> TradeRecord | None:
        """Close an open position with realized P&L."""
        rec = self._open_positions.pop(trade_id, None)
        if rec is None:
            logger.warning("Exit called for unknown/open trade: %s", trade_id)
            rec = self._trades.get(trade_id)
            if rec is None:
                return None

        now = _now_bjt()
        rec.exit_time = now.isoformat()
        rec.exit_price = exit_price
        rec.exit_reason = exit_reason

        if rec.entry_price > 0 and rec.quantity > 0:
            entry_total = rec.entry_price * rec.quantity
            exit_total = exit_price * rec.quantity
            rec.realized_pnl = exit_total - entry_total
            if entry_total > 0:
                rec.realized_pnl_pct = (exit_total / entry_total - 1) * 100

        try:
            et = datetime.fromisoformat(rec.entry_time)
            hold_min = (now - et).total_seconds() / 60
            rec.hold_duration_minutes = max(int(hold_min), 0)
        except Exception:
            pass

        if rec.target_price > 0:
            rec.target_hit = exit_price >= rec.target_price
        if rec.stop_loss_price > 0:
            rec.stop_hit = exit_price <= rec.stop_loss_price
        rec.prediction_correct = (rec.realized_pnl > 0) if rec.realized_pnl != 0 else None

        old_pnl = self._running_pnl
        old_peak = self._peak_pnl
        old_dd = self._max_drawdown_pct
        old_losses = self._consecutive_losses

        self._running_pnl += rec.realized_pnl
        if self._running_pnl > self._peak_pnl:
            self._peak_pnl = self._running_pnl
        if self._peak_pnl > 0:
            dd_pct = (self._peak_pnl - self._running_pnl) / self._peak_pnl * 100
            if dd_pct > self._max_drawdown_pct:
                self._max_drawdown_pct = dd_pct

        if rec.realized_pnl < 0:
            self._consecutive_losses += 1
        elif rec.realized_pnl > 0:
            self._consecutive_losses = 0

        self._trades[trade_id] = rec
        try:
            self._save()
        except Exception:
            logger.error("Journal save failed, rolling back exit: %s", trade_id)
            del self._trades[trade_id]
            self._open_positions[trade_id] = rec
            rec.exit_time = ""
            rec.exit_price = Decimal("0")
            rec.realized_pnl = Decimal("0")
            rec.realized_pnl_pct = Decimal("0")
            self._running_pnl = old_pnl
            self._peak_pnl = old_peak
            self._max_drawdown_pct = old_dd
            self._consecutive_losses = old_losses
            raise
        logger.info("Journal exit: %s @ ¥%s P&L=%s (%s)",
                    trade_id, exit_price, rec.realized_pnl, exit_reason)
        return rec

    async def check_stops_targets(self) -> list[dict]:
        """Check all open positions against current prices.

        Returns list of triggered alerts: stop-loss or take-profit hits.
        This is the monitoring heartbeat — call every minute during market hours.
        """
        if not self._open_positions:
            return []

        alerts = []
        for trade_id, pos in list(self._open_positions.items()):
            try:
                quote = await fetch_realtime_quote(pos.symbol)
            except Exception:
                quote = None
            if not quote or not quote.get("price"):
                continue

            current = Decimal(str(quote["price"]))
            trigger = None

            if pos.stop_loss_price > 0 and current <= pos.stop_loss_price:
                trigger = "stop_loss"
            elif pos.target_price > 0 and current >= pos.target_price:
                trigger = "take_profit"

            if trigger:
                pnl = (current - pos.entry_price) * pos.quantity
                pnl_pct = ((current / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else Decimal("0")
                dist_stop = ((current - pos.stop_loss_price) / pos.entry_price * 100) if pos.stop_loss_price > 0 and pos.entry_price > 0 else Decimal("0")
                dist_target = ((pos.target_price - current) / pos.entry_price * 100) if pos.target_price > 0 and pos.entry_price > 0 else Decimal("0")

                alerts.append({
                    "trade_id": pos.id,
                    "symbol": pos.symbol,
                    "name": pos.name,
                    "direction": pos.direction,
                    "trigger": trigger,
                    "entry_price": str(pos.entry_price),
                    "current_price": str(current),
                    "target_price": str(pos.target_price),
                    "stop_loss_price": str(pos.stop_loss_price),
                    "unrealized_pnl": str(pnl),
                    "unrealized_pnl_pct": str(round(float(pnl_pct), 2)),
                    "distance_to_stop_pct": str(round(float(dist_stop), 2)),
                    "distance_to_target_pct": str(round(float(dist_target), 2)),
                    "confidence": str(pos.confidence),
                    "held_since": pos.entry_time,
                })

        return alerts

    async def get_position_statuses(self) -> list[PositionStatus]:
        """Get current status of all open positions with live prices."""
        positions = []
        for pos in self._open_positions.values():
            try:
                quote = await fetch_realtime_quote(pos.symbol)
                current = Decimal(str(quote["price"])) if quote and quote.get("price") else pos.entry_price
            except Exception:
                current = pos.entry_price

            pnl = (current - pos.entry_price) * pos.quantity
            pnl_pct = ((current / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else Decimal("0")
            dist_target = ((pos.target_price - current) / pos.entry_price * 100) if pos.target_price > 0 and pos.entry_price > 0 else Decimal("0")
            dist_stop = ((current - pos.stop_loss_price) / pos.entry_price * 100) if pos.stop_loss_price > 0 and pos.entry_price > 0 else Decimal("0")

            positions.append(PositionStatus(
                symbol=pos.symbol,
                name=pos.name,
                direction=pos.direction,
                entry_price=pos.entry_price,
                quantity=pos.quantity,
                target_price=pos.target_price,
                stop_loss_price=pos.stop_loss_price,
                current_price=current,
                unrealized_pnl=pnl,
                unrealized_pnl_pct=pnl_pct,
                distance_to_target_pct=dist_target,
                distance_to_stop_pct=dist_stop,
                held_since=pos.entry_time,
                trade_id=pos.id,
            ))
        return positions

    def get_consecutive_losses(self) -> int:
        return self._consecutive_losses

    def get_running_pnl(self) -> Decimal:
        return self._running_pnl

    def generate_daily_review(self, date_str: str | None = None) -> DailyReview:
        """Generate a professional-grade daily review.

        This is the 复盘 core — every metric a real trader checks:
        - Win rate, profit factor, max drawdown
        - Best/worst trade identification
        - Long vs short performance breakdown
        - P&L attribution
        """
        target_date = date_str or _now_bjt().strftime("%Y-%m-%d")
        day_trades = [
            t for t in self._trades.values()
            if t.entry_time.startswith(target_date) and t.exit_time
        ]

        if not day_trades:
            return DailyReview(date=target_date)

        wins = [t for t in day_trades if t.realized_pnl > 0]
        losses = [t for t in day_trades if t.realized_pnl < 0]
        even = [t for t in day_trades if t.realized_pnl == 0]

        total_pnl = sum(t.realized_pnl for t in day_trades)
        avg_win = (sum(t.realized_pnl for t in wins) / len(wins)) if wins else Decimal("0")
        avg_loss = (sum(t.realized_pnl for t in losses) / len(losses)) if losses else Decimal("0")
        gross_profit = sum(t.realized_pnl for t in wins)
        gross_loss = abs(sum(t.realized_pnl for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else Decimal("999") if gross_profit > 0 else Decimal("0")

        win_rate = Decimal(str(len(wins) / len(day_trades) * 100)) if day_trades else Decimal("0")

        longs = [t for t in day_trades if t.direction == "BUY"]
        shorts = [t for t in day_trades if t.direction == "SELL"]
        long_wins = [t for t in longs if t.realized_pnl > 0]
        short_wins = [t for t in shorts if t.realized_pnl > 0]

        best = max(day_trades, key=lambda t: t.realized_pnl)
        worst = min(day_trades, key=lambda t: t.realized_pnl)

        review = DailyReview(
            date=target_date,
            total_trades=len(day_trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=round(win_rate, 1),
            total_pnl=round(total_pnl, 2),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            profit_factor=round(profit_factor, 2),
            max_single_win=best.realized_pnl,
            max_single_loss=worst.realized_pnl,
            max_drawdown_pct=round(self._max_drawdown_pct, 2),
            long_trades=len(longs),
            short_trades=len(shorts),
            long_win_rate=Decimal(str(round(len(long_wins) / len(longs) * 100, 1))) if longs else Decimal("0"),
            short_win_rate=Decimal(str(round(len(short_wins) / len(shorts) * 100, 1))) if shorts else Decimal("0"),
            best_trade_id=best.id,
            worst_trade_id=worst.id,
        )

        review.ai_lessons = self._generate_lessons(day_trades, review)
        return review

    def _generate_lessons(self, trades: list[TradeRecord], review: DailyReview) -> list[str]:
        """Generate concrete, actionable lessons from the day's trades."""
        lessons = []

        if review.win_rate < 40:
            lessons.append(f"胜率仅{review.win_rate}%，低于40%警戒线——选股条件需要收紧，confidence阈值应该提高")
        elif review.win_rate > 65:
            lessons.append(f"胜率{review.win_rate}%表现优秀，当前策略可以继续")

        if review.profit_factor < 1.5:
            lessons.append(f"盈亏比{review.profit_factor}偏低——需要扩大止盈空间或缩小止损距离")
        elif review.profit_factor > 3.0:
            lessons.append(f"盈亏比{review.profit_factor}优秀——赚到时赚得多，亏到时亏得少")

        stop_hits = [t for t in trades if t.stop_hit]
        if len(stop_hits) > 1:
            lessons.append(f"今日{len(stop_hits)}笔止损——检查入场时机是否在追高")

        target_hits = [t for t in trades if t.target_hit]
        if len(target_hits) > 0 and len(target_hits) == len(trades):
            lessons.append(f"今日所有{len(target_hits)}笔交易都到达目标价——目标设定可能偏低")

        avg_hold = sum(t.hold_duration_minutes for t in trades) / len(trades) if trades else 0
        if avg_hold < 30:
            lessons.append(f"平均持仓{avg_hold:.0f}分钟——超短线风格，确认是否是策略意图")
        elif avg_hold > 240:
            lessons.append(f"平均持仓{avg_hold:.0f}分钟——长线风格，注意盘中波动风险")

        low_conf_losses = [t for t in trades if t.realized_pnl < 0 and t.confidence < Decimal("0.7")]
        if low_conf_losses:
            lessons.append(f"有{len(low_conf_losses)}笔低置信度亏损——confidence<0.7的交易不应该执行")

        if self._consecutive_losses >= 3:
            lessons.append(f"连续{self._consecutive_losses}笔亏损——建议暂停交易，复盘策略是否存在系统性问题")

        if review.max_drawdown_pct > 10:
            lessons.append(f"最大回撤{review.max_drawdown_pct}%超过10%——仓位控制需要收紧")

        if not lessons:
            lessons.append("今日交易纪律良好，无明显问题——保持节奏")

        return lessons

    async def ai_deep_review(self, trade_records: list[TradeRecord], review: DailyReview, send_func=None) -> str:
        """AI-driven deep review: what went right, what went wrong, what to change.

        This is the TURING TEST of trading — can the AI honestly evaluate itself?
        """
        from potato.llm import chat

        trade_summaries = []
        for t in trade_records[:20]:
            result_emoji = "✅赚" if t.realized_pnl > 0 else ("❌亏" if t.realized_pnl < 0 else "➖平")
            thesis_trunc = t.thesis[:200] if t.thesis else "无"
            trade_summaries.append(
                f"  {result_emoji} {t.symbol} {t.name} {t.direction}"
                f" 入场¥{t.entry_price} 出场¥{t.exit_price}"
                f" P&L=¥{t.realized_pnl}({t.realized_pnl_pct:.1f}%)"
                f" 持仓{t.hold_duration_minutes}分钟"
                f" 置信度{float(t.confidence):.0%}"
                f" 止损价¥{t.stop_loss_price} 目标价¥{t.target_price}"
                f" | 逻辑: {thesis_trunc}"
            )

        prompt = f"""你是专业交易员复盘系统。请对以下交易数据做深度复盘。

关键指标:
- 总交易: {review.total_trades}笔 ({review.winning_trades}赚 {review.losing_trades}亏)
- 胜率: {review.win_rate}%
- 总盈亏: ¥{review.total_pnl}
- 盈亏比(利润因子): {review.profit_factor}
- 平均盈利: ¥{review.avg_win}
- 平均亏损: ¥{review.avg_loss}
- 最大回撤: {review.max_drawdown_pct}%
- 最佳交易: {review.best_trade_id}
- 最差交易: {review.worst_trade_id}

逐笔交易:
{chr(10).join(trade_summaries)}

请输出:
1. 【总体评价】一句话总结今日表现
2. 【做对的】哪些判断对了？为什么？
3. 【做错的】哪些判断错了？为什么？是逻辑问题还是执行问题？
4. 【模式发现】从赢/亏的交易中，你能看到什么规律？
5. 【具体改进】明天应该调整什么？给出3条可执行的规则
6. 【风险提醒】当前最大风险是什么？

用中文回复，专业、直接、不废话。"""

        try:
            result = await asyncio.to_thread(
                chat, prompt,
                system="你是专业交易员复盘系统，诚实评估交易表现，用中文输出。",
                max_tokens=2500, task="analysis", use_json=False,
            )
            if result and isinstance(result, dict) and result.get("ok"):
                content = result.get("content", "")
                if content:
                    return content.strip()
            elif result and isinstance(result, str):
                return result.strip()
        except Exception as e:
            logger.error("AI deep review failed: %s", e)
            return "AI复盘暂时不可用，请参考上方数据指标自行复盘。"

        return ""

    def get_recent_trades(self, n: int = 20) -> list[TradeRecord]:
        """Get most recent N closed trades sorted by exit time."""
        closed = [t for t in self._trades.values() if t.exit_time]
        closed.sort(key=lambda t: t.exit_time, reverse=True)
        return closed[:n]

    def get_open_positions_summary(self) -> list[dict]:
        """Simple summary of open positions for frontend display."""
        result = []
        for pos in self._open_positions.values():
            result.append({
                "trade_id": pos.id,
                "symbol": pos.symbol,
                "name": pos.name,
                "direction": pos.direction,
                "entry_price": str(pos.entry_price),
                "target_price": str(pos.target_price),
                "stop_loss_price": str(pos.stop_loss_price),
                "quantity": pos.quantity,
                "amount_cny": str(pos.amount_cny),
                "confidence": str(pos.confidence),
                "held_since": pos.entry_time,
                "thesis": pos.thesis[:200],
            })
        return result