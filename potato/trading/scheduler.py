"""Auto-trading scheduler — 小土豆自动操盘调度器.

Manages the full autonomous trading cycle:
    1. Pre-market scan (9:00) — fetch news, queue candidates
    2. Market open analysis (9:25) — deep analysis with technicals
    3. Trade execution (9:30-14:45) — validate & execute via risk gate
    4. Mid-day review (11:30) — check positions, adjust stops
    5. Pre-close review (14:30) — evaluate holdings, plan next day
    6. Post-market summary (15:10) — daily P&L report

Every step is broadcast to the frontend for transparency.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, time, timezone, timedelta
from typing import Any

from potato.trading.analyzer import (
    deep_analysis,
    fetch_realtime_quote,
    fetch_kline,
    format_trade_decision_for_pet,
    format_trade_signal_message,
)
from potato.trading.executor import TradeDecision, TradeExecutor
from potato.trading.journal import TradeJournal
from potato.risk import RiskValidator, RiskState, TradeRequest, SAFETY_RULES
from potato.user_prefs import UserPrefs
from decimal import Decimal

logger = logging.getLogger("potato.trading.scheduler")

BJT = timezone(timedelta(hours=8))

SCHEDULE = {
    "pre_market": time(9, 0),
    "risk_confirm": time(9, 10),
    "open_analysis": time(9, 25),
    "mid_review": time(11, 30),
    "pre_close": time(14, 30),
    "post_market": time(15, 10),
}


def _now_bjt() -> datetime:
    return datetime.now(tz=BJT)


def _is_trading_day(dt: datetime | None = None) -> bool:
    d = dt or _now_bjt()
    return d.weekday() < 5


class TradingScheduler:
    """Schedules and runs the autonomous trading cycle.

    STRICT DAILY PROTOCOL — no step may be skipped:
    1. PRE_MARKET (9:00): Scan news, check positions, prepare analysis
    2. RISK_CONFIRM (9:10): Ask user for today's limits, wait 10 min
       - If user confirms → use new limits
       - If no response → use yesterday's confirmed limits
       - If no limits at all → NO TRADING, keep waiting
    3. OPEN_ANALYSIS (9:25): Deep analysis after user confirms
    4. MID_REVIEW (11:30): Position monitoring, stop/target alerts
    5. PRE_CLOSE (14:30): End-of-day evaluation
    6. POST_MARKET (15:10): Full daily review
    """

    def __init__(self, send_func=None):
        self.send_func = send_func
        self.executor = TradeExecutor(send_func)
        self.journal = TradeJournal()
        self._running = False
        self._task = None
        self._last_analysis = None

    async def _emit(self, event_type: str, data: dict):
        if self.send_func:
            await self.send_func(event_type, data)

    async def _emit_step(self, phase: str, status: str, detail: str = ""):
        await self._emit("schedule_step", {"phase": phase, "status": status, "detail": detail})

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Trading scheduler started")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Trading scheduler stopped")

    async def _run_loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error("Scheduler tick error: %s", e)
            await asyncio.sleep(60)

    async def _tick(self):
        now = _now_bjt()
        if not _is_trading_day(now):
            return

        now_time = now.time()
        phase = None
        for name, scheduled in SCHEDULE.items():
            if now_time.hour == scheduled.hour and now_time.minute == scheduled.minute:
                phase = name
                break

        if phase == "pre_market":
            await self._phase_pre_market()
        elif phase == "risk_confirm":
            await self._phase_risk_confirm()
        elif phase == "open_analysis":
            await self._phase_open_analysis()
        elif phase == "mid_review":
            await self._phase_mid_review()
        elif phase == "pre_close":
            await self._phase_pre_close()
        elif phase == "post_market":
            await self._phase_post_market()

    async def run_manual_analysis(
        self,
        symbols: list[str],
        user_prefs: dict | None = None,
        news_items: list[dict] | None = None,
        portfolio_text: str = "",
        platform_names: str = "",
    ) -> dict[str, Any]:
        await self._emit_step("analysis", "running", f"分析中: {', '.join(symbols)}")

        result = await deep_analysis(
            symbols=symbols,
            user_prefs=user_prefs,
            news_items=news_items,
            portfolio_text=portfolio_text,
            platform_names=platform_names,
        )

        if result.get("ok"):
            self._last_analysis = result
            analysis = result.get("analysis", {})

            picks = analysis.get("stock_picks", [])
            for pick in picks:
                signal_msg = format_trade_signal_message(pick)
                if signal_msg:
                    await self._emit("trade_signal", {
                        "symbol": pick.get("symbol", ""),
                        "name": pick.get("name", ""),
                        "action": pick.get("action", "HOLD"),
                        "confidence": pick.get("confidence", 0),
                        "message": signal_msg,
                    })

            formatted = format_trade_decision_for_pet(result)
            await self._emit("analysis_result", {
                "analysis": analysis,
                "formatted": formatted,
                "symbols": symbols,
            })
            await self._emit_step("analysis", "done", f"分析完成: {len(picks)}只股票")
        else:
            await self._emit_step("analysis", "error", f"分析失败: {result.get('error', '')}")

        return result

    async def execute_trade_decision(self, pick: dict[str, Any], user_prefs: dict | None = None) -> dict[str, Any]:
        prefs = user_prefs or {}
        max_single_cny = None
        raw_max = prefs.get("max_single_cny") or prefs.get("max_single_trade_cny")
        if raw_max:
            try:
                max_single_cny = Decimal(str(raw_max))
            except Exception:
                logger.warning("Invalid max_single_cny: %s", raw_max)
        price = Decimal("0")
        entry_str = pick.get("entry_price") or pick.get("price") or "0"
        try:
            price = Decimal(str(entry_str).replace(",", ""))
        except Exception:
            price = Decimal("0")
        if price <= 0:
            try:
                quote = await fetch_realtime_quote(pick.get("symbol", ""))
                if quote and quote.get("price"):
                    price = Decimal(str(quote["price"]))
            except Exception:
                pass
        if price <= 0:
            return {"ok": False, "reason": f"无法获取 {pick.get('symbol')} 的价格"}

        pct_str = str(pick.get("position_size", "20"))
        pct_str = pct_str.replace("%", "").strip()
        try:
            pct = float(pct_str)
            if pct > 1:
                pct = pct / 100
        except Exception:
            pct = 0.2
        pct = min(max(pct, 0.01), 0.5)
        if max_single_cny:
            amount_cny = max_single_cny * Decimal(str(pct))
        else:
            amount_cny = price * 100 * Decimal(str(pct))
        if price > 0:
            quantity = max(int(amount_cny / price / 100) * 100, 100)
        else:
            quantity = 100
        if quantity <= 0:
            quantity = 100
        amount_cny = price * quantity

        conf = Decimal(str(pick.get("confidence", 0)))
        if conf <= 0:
            conf = Decimal("0.65")

        trade = TradeDecision(
            action=pick.get("action", "HOLD"),
            symbol=pick.get("symbol", ""),
            name=pick.get("name", ""),
            price=price,
            quantity=quantity,
            amount_cny=amount_cny,
            confidence=conf,
            reasoning=pick.get("reasoning", "")[:500],
            entry_price=str(price),
            target_price=pick.get("target_price", ""),
            stop_loss=pick.get("stop_loss", ""),
            platform_id=prefs.get("platform_id", "eastmoney"),
        )

        result = await self.executor.validate_and_execute(trade)
        return result

    async def _phase_pre_market(self):
        await self._emit_step("pre_market", "running", "盘前扫描中...")
        await self._emit_step("pre_market", "done", "盘前扫描完成")

    async def _phase_open_analysis(self):
        await self._emit_step("open_analysis", "running", "开盘分析中...")

    async def _phase_risk_confirm(self):
        """STRICT: Ask user for today's limits. 10 min timeout → use yesterday's."""
        await self._emit_step("risk_confirm", "running", "确认今日风控参数...")

        try:
            from potato.user_prefs import UserPrefs
            prefs = UserPrefs()
            all_prefs = prefs.get_all()
        except Exception:
            all_prefs = {}

        risk_confirmed = bool(all_prefs.get("risk_confirmed", False))
        if risk_confirmed:
            single = all_prefs.get("max_single_trade_cny") or all_prefs.get("max_single_cny")
            daily = all_prefs.get("max_daily_trade_cny") or all_prefs.get("max_daily_cny")
            positions = all_prefs.get("max_open_positions")
            sl = all_prefs.get("stop_loss_pct")
            tp = all_prefs.get("take_profit_pct")
            rl = all_prefs.get("risk_level", "")

            rl_cn = {"conservative": "保守", "moderate": "稳健", "aggressive": "激进"}.get(rl, rl or "未设置")
            lines = [f"✅ 昨日风控已确认，沿用: 风险等级{rl_cn}"]
            if single: lines.append(f"  单笔限额: ¥{single}")
            if daily: lines.append(f"  日限额: ¥{daily}")
            if positions: lines.append(f"  最多持仓: {positions}只")
            if sl: lines.append(f"  止损: {float(sl)*100:.0f}%")
            if tp: lines.append(f"  止盈: {float(tp)*100:.0f}%")

            await self._emit("risk_confirm_prompt", {
                "confirmed": True,
                "source": "yesterday",
                "params": all_prefs,
                "summary": "\n".join(lines),
                "message": "沿用昨日风控参数（10分钟内无新确认自动沿用）。如需调整请告诉我。",
            })
            await self._emit_step("risk_confirm", "done", "沿用昨日风控参数")
            return

        await self._emit("risk_confirm_prompt", {
            "confirmed": False,
            "source": "new",
            "params": {},
            "summary": "⚠️ 风控参数未确认！请告诉我：1) 单笔最多投多少？2) 每天最多投多少？3) 最多同时持几只股？4) 止损比例设多少？",
            "message": "开启新一天——请确认今日风控参数。10分钟无回复将沿用昨日设置。",
        })
        await self._emit_step("risk_confirm", "waiting", "等待用户确认风控参数（10分钟超时→沿用昨日）")

    async def _phase_mid_review(self):
        await self._emit_step("mid_review", "running", "午间复盘中...")
        positions = self.journal.get_open_positions_summary()
        if not positions:
            await self._emit_step("mid_review", "done", "午间复盘：无持仓")
            return

        alerts = await self.journal.check_stops_targets()
        if alerts:
            for a in alerts:
                trigger_cn = "🎯 止盈触发" if a["trigger"] == "take_profit" else "🛑 止损触发"
                await self._emit("trade_alert", {
                    "type": a["trigger"],
                    "symbol": a["symbol"],
                    "name": a["name"],
                    "message": f"{trigger_cn}: {a['name']}({a['symbol']}) 当前¥{a['current_price']} "
                               f"{'→止损价' if a['trigger'] == 'stop_loss' else '→目标价'} "
                               f"盈亏¥{a['unrealized_pnl']}({a['unrealized_pnl_pct']}%)",
                    "trade_id": a["trade_id"],
                })

        pos_lines = []
        for pos in positions:
            pnl_icon = "🟢" if pos.get("direction") == "BUY" else "🔴"
            pos_lines.append(f"{pnl_icon} {pos['name']}({pos['symbol']}) "
                            f"入场¥{pos['entry_price']} 止损¥{pos['stop_loss_price']} 目标¥{pos['target_price']}")

        summary = f"午间复盘：{len(positions)}只持仓\n" + "\n".join(pos_lines)
        if alerts:
            summary += f"\n⚠️ {len(alerts)}个触发信号！"

        await self._emit("mid_review_result", {
            "positions": len(positions),
            "alerts": len(alerts),
            "alert_details": alerts,
            "summary": summary,
        })
        await self._emit_step("mid_review", "done", summary[:80])

    async def _phase_pre_close(self):
        await self._emit_step("pre_close", "running", "尾盘评估中...")
        positions = self.journal.get_open_positions_summary()
        if not positions:
            await self._emit_step("pre_close", "done", "尾盘评估：无持仓")
            return

        alerts = await self.journal.check_stops_targets()

        stop_alerts = [a for a in alerts if a["trigger"] == "stop_loss"]
        target_alerts = [a for a in alerts if a["trigger"] == "take_profit"]

        recs = []
        for a in stop_alerts:
            recs.append(f"🛑 建议{a['name']}({a['symbol']})止损——当前¥{a['current_price']}已破止损价¥{a['stop_loss_price']}")
        for a in target_alerts:
            recs.append(f"🎯 建议{a['name']}({a['symbol']})止盈——当前¥{a['current_price']}已达目标价")

        near_close = []
        for pos in positions:
            if pos.get("stop_loss_price") and pos.get("entry_price"):
                try:
                    sl_dist = abs(float(pos["stop_loss_price"]) - float(pos["entry_price"])) / float(pos["entry_price"]) * 100
                    if sl_dist < 2:
                        near_close.append(f"⚠️ {pos['name']} 止损距离仅{sl_dist:.1f}%")
                except Exception:
                    pass

        summary_lines = [f"尾盘评估：{len(positions)}只持仓"]
        if recs:
            summary_lines.append("需要操作的：")
            summary_lines.extend(recs)
        if near_close:
            summary_lines.append("距离止损近的：")
            summary_lines.extend(near_close)
        if not recs and not near_close:
            summary_lines.append("所有持仓风控正常，无需操作")

        summary = "\n".join(summary_lines)
        await self._emit("pre_close_result", {
            "positions": len(positions),
            "stop_alerts": len(stop_alerts),
            "target_alerts": len(target_alerts),
            "recommendations": recs,
            "near_stop_loss": near_close,
            "summary": summary,
        })
        await self._emit_step("pre_close", "done", summary[:80])

    async def _phase_post_market(self):
        await self._emit_step("post_market", "running", "盘后深度复盘中...")

        review = self.journal.generate_daily_review()

        today_trades = self.journal.get_recent_trades(n=50)
        today = [t for t in today_trades if t.entry_time.startswith(_now_bjt().strftime("%Y-%m-%d"))]

        summary = (
            f"📊 今日复盘\n"
            f"交易{review.total_trades}笔 | "
            f"胜率{review.win_rate}% | "
            f"盈亏¥{review.total_pnl} | "
            f"利润因子{review.profit_factor} | "
            f"最大回撤{review.max_drawdown_pct}%"
        )
        if review.winning_trades > 0:
            summary += f"\n✅ 赚{review.winning_trades}笔 均赚¥{review.avg_win}"
        if review.losing_trades > 0:
            summary += f"\n❌ 亏{review.losing_trades}笔 均亏¥{review.avg_loss}"

        for lesson in review.ai_lessons:
            summary += f"\n💡 {lesson}"

        if today:
            ai_review = await self.journal.ai_deep_review(today, review, self.send_func)
            if ai_review:
                summary += f"\n\n🧠 AI复盘:\n{ai_review}"

        positions = self.journal.get_open_positions_summary()
        if positions:
            summary += f"\n\n📈 当前持仓{len(positions)}只:"
            for pos in positions:
                summary += f"\n  {pos['name']}({pos['symbol']}) 入场¥{pos['entry_price']} 目标¥{pos['target_price']} 止损¥{pos['stop_loss_price']}"

        await self._emit("daily_summary", {
            "trades": review.total_trades,
            "winning": review.winning_trades,
            "losing": review.losing_trades,
            "win_rate": str(review.win_rate),
            "total_pnl": str(review.total_pnl),
            "profit_factor": str(review.profit_factor),
            "max_drawdown_pct": str(review.max_drawdown_pct),
            "avg_win": str(review.avg_win),
            "avg_loss": str(review.avg_loss),
            "best_trade": review.best_trade_id,
            "worst_trade": review.worst_trade_id,
            "lessons": review.ai_lessons,
            "open_positions": len(positions),
            "summary": summary,
        })
        await self._emit_step("post_market", "done", f"复盘完成: {review.total_trades}笔 胜率{review.win_rate}% P&L¥{review.total_pnl}")

    def get_status(self) -> dict[str, Any]:
        today = _now_bjt().strftime("%Y-%m-%d")
        recent = self.journal.get_recent_trades(n=1000)
        today_trades = [t for t in recent if t.entry_time.startswith(today)]
        open_positions = len(self.journal._open_positions)
        return {
            "running": self._running,
            "last_analysis": self._last_analysis is not None,
            "trades_today": len(today_trades),
            "total_trades": len(recent),
            "open_positions": open_positions,
            "running_pnl": str(self.journal.get_running_pnl()),
            "consecutive_losses": self.journal.get_consecutive_losses(),
        }