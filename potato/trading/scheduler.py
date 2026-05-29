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
from potato.trading.plan_execute import run_plan_execute_analysis
from potato.eastmoney import (
    EastMoneyClient,
    analyze_sentiment,
    get_stock_changes,
    get_hot_tables,
    get_realtime_quote as em_get_realtime_quote,
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


async def _gather_eastmoney_context(symbols: list[str]) -> str:
    blocks = []
    em = EastMoneyClient()
    try:
        for symbol in symbols[:5]:
            q = await asyncio.to_thread(em_get_realtime_quote, symbol)
            if q and q.get("name"):
                chg = q.get("change_pct", 0)
                blocks.append(f"- {q['name']}({symbol}): ¥{q.get('price', 'N/A')} {chg:+.2f}%")
    except Exception:
        pass
    try:
        changes = await asyncio.to_thread(get_stock_changes)
        if changes:
            hot = [c for c in changes[:8] if c.get("name")]
            if hot:
                blocks.append("\n异动监控:")
                for c in hot:
                    blocks.append(f"- {c.get('name','?')}({c.get('code','?')}): {c.get('type','?')} {c.get('desc','')}")
    except Exception:
        pass
    try:
        hot_data = await asyncio.to_thread(get_hot_tables)
        if hot_data:
            items = hot_data[:6]
            if items:
                blocks.append("\n龙虎榜:")
                for h in items:
                    blocks.append(f"- {h.get('name','?')}({h.get('code','?')}): 买入{h.get('buy','?')} 卖出{h.get('sell','?')}")
    except Exception:
        pass
    return "\n".join(blocks) if blocks else ""


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

    def __init__(self, send_func=None, broker=None):
        self.send_func = send_func
        self.executor = TradeExecutor(send_func, broker=broker)
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
            try:
                await self._phase_pre_market()
            except Exception as e:
                logger.error("Phase pre_market error: %s", e)
                await self._emit("chat", {"text": f"⚠️ 盘前分析异常: {e}", "emotion": "worried"})
        elif phase == "risk_confirm":
            try:
                await self._phase_risk_confirm()
            except Exception as e:
                logger.error("Phase risk_confirm error: %s", e)
        elif phase == "open_analysis":
            try:
                await self._phase_open_analysis()
            except Exception as e:
                logger.error("Phase open_analysis error: %s", e)
                await self._emit("chat", {"text": f"⚠️ 开盘分析异常: {e}", "emotion": "worried"})
        elif phase == "mid_review":
            try:
                await self._phase_mid_review()
            except Exception as e:
                logger.error("Phase mid_review error: %s", e)
        elif phase == "pre_close":
            try:
                await self._phase_pre_close()
            except Exception as e:
                logger.error("Phase pre_close error: %s", e)
        elif phase == "post_market":
            try:
                await self._phase_post_market()
            except Exception as e:
                logger.error("Phase post_market error: %s", e)

    async def run_manual_analysis(
        self,
        symbols: list[str],
        user_prefs: dict | None = None,
        news_items: list[dict] | None = None,
        portfolio_text: str = "",
        platform_names: str = "",
        use_plan_execute: bool = False,
    ) -> dict[str, Any]:
        await self._emit_step("analysis", "running", f"分析中: {', '.join(symbols)}")

        if use_plan_execute:
            await self._emit_step("analysis", "running", "计划-执行分析模式启动...")
            em_context = ""
            sentiment_block = ""
            try:
                em_ctx_data = await _gather_eastmoney_context(symbols)
                if em_ctx_data:
                    em_context = em_ctx_data
            except Exception:
                pass
            try:
                news_text = " ".join(n.get("title", "") for n in (news_items or [])[:8])
                if news_text.strip():
                    sent = await asyncio.to_thread(analyze_sentiment, news_text)
                    sentiment_block = (
                        f"市场情绪: {sent['category']} (得分{sent['score']:.1f})\n"
                        f"正面词: {', '.join(w for w, _ in sent.get('positive_words', [])[:5])}\n"
                        f"负面词: {', '.join(w for w, _ in sent.get('negative_words', [])[:5])}"
                    )
            except Exception:
                pass

            result = await run_plan_execute_analysis(
                symbols=symbols,
                user_prefs=user_prefs,
                news_items=news_items,
                em_context=em_context,
                sentiment_block=sentiment_block,
            )
        else:
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
        try:
            from potato.user_prefs import UserPrefs
            from potato.intel import fetch_headlines
            prefs = UserPrefs()
            all_prefs = prefs.get_all()
        except Exception:
            all_prefs = {}
        symbols = all_prefs.get("watchlist") or all_prefs.get("watchlist_symbols") or []
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.split(",") if s.strip()]
        if not symbols:
            symbols = ["600519", "000858", "601318"]

        news_items = None
        try:
            news_items = fetch_headlines(limit_per_feed=4)
            await self._emit_step("pre_market", "running", f"获取到{len(news_items)}条资讯，分析{len(symbols)}只自选股...")
        except Exception as e:
            logger.warning("Pre-market news fetch failed: %s", e)

        em_summary = ""
        try:
            changes = await asyncio.to_thread(get_stock_changes)
            if changes:
                top_changes = changes[:5]
                em_summary = f"，{len(changes)}只异动股"
                change_msgs = [f"{c.get('name','?')}({c.get('code','?')}): {c.get('type','?')}" for c in top_changes]
                await self._emit("stock_changes", {"changes": changes[:20], "count": len(changes)})
                await self._emit_step("pre_market", "running", f"异动监控: {', '.join(change_msgs[:3])}")
        except Exception as e:
            logger.warning("Pre-market stock changes fetch failed: %s", e)

        try:
            hot_data = await asyncio.to_thread(get_hot_tables)
            if hot_data:
                await self._emit("hot_tables", {"data": hot_data[:10]})
        except Exception:
            pass

        try:
            news_text = " ".join(n.get("title", "") for n in (news_items or [])[:8])
            if news_text.strip():
                sent = await asyncio.to_thread(analyze_sentiment, news_text)
                await self._emit("sentiment_analysis", sent)
                sentiment_emoji = {"看涨": "🟢", "看跌": "🔴"}.get(sent.get("category", ""), "⚪")
                em_summary += f"，情绪{sentiment_emoji}{sent['category']}({sent['score']:.1f})"
        except Exception:
            pass

        result = await self.run_manual_analysis(
            symbols=symbols,
            user_prefs=all_prefs,
            news_items=news_items,
        )

        analysis = result.get("analysis", {}) if result.get("ok") else {}
        picks = analysis.get("stock_picks", [])
        summary = f"盘前扫描完成：{len(symbols)}只自选股，{len(news_items or [])}条资讯{em_summary}"
        if picks:
            buy_signals = [p for p in picks if p.get("action") == "BUY" and p.get("confidence", 0) >= 0.65]
            summary += f"，{len(buy_signals)}只买入信号"

        await self._emit("chat", {
            "text": f"🌅 盘前扫描完成\n分析了{len(symbols)}只自选股 + {len(news_items or [])}条资讯\n"
                    + (f"发现{len([p for p in picks if p.get('action') in ('BUY','SELL')])}个操作信号" if picks else "暂无明确信号"),
            "expression": "happy" if picks else "neutral",
        })
        await self._emit_step("pre_market", "done", summary)

    async def _phase_open_analysis(self):
        await self._emit_step("open_analysis", "running", "开盘分析中...")

        try:
            from potato.user_prefs import UserPrefs
            from potato.intel import fetch_headlines
            prefs = UserPrefs()
            all_prefs = prefs.get_all()
        except Exception:
            all_prefs = {}

        symbols = all_prefs.get("watchlist") or all_prefs.get("watchlist_symbols") or []
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.split(",") if s.strip()]
        if not symbols:
            symbols = ["600519", "000858", "601318"]

        await self._emit_step("open_analysis", "running", f"抓取资讯中...")

        news_items = []
        try:
            news_items = fetch_headlines(limit_per_feed=6)
            news_count = len(news_items)
            await self._emit_step("open_analysis", "running", f"获取到{news_count}条资讯，开始分析{len(symbols)}只股票...")
        except Exception as e:
            logger.warning("News fetch failed: %s", e)

        try:
            changes = await asyncio.to_thread(get_stock_changes)
            if changes:
                await self._emit("stock_changes", {"changes": changes[:20], "count": len(changes)})
        except Exception:
            pass

        try:
            news_text = " ".join(n.get("title", "") for n in news_items[:8])
            if news_text.strip():
                sent = await asyncio.to_thread(analyze_sentiment, news_text)
                await self._emit("sentiment_analysis", sent)
        except Exception:
            pass

        result = await self.run_manual_analysis(
            symbols=symbols[:5],
            user_prefs=all_prefs,
            news_items=news_items if news_items else None,
        )

        analysis = result.get("analysis", {}) if result.get("ok") else {}
        picks = analysis.get("stock_picks", [])

        if result.get("ok") and picks:
            formatted = format_trade_decision_for_pet(result)
            await self._emit("chat", {
                "text": f"📊 开盘分析完成\n\n{formatted}",
                "expression": "happy",
            })

            for pick in picks:
                action = pick.get("action", "WATCH")
                if action in ("BUY", "SELL"):
                    signal_msg = format_trade_signal_message(pick)
                    if signal_msg:
                        await self._emit("trade_signal", {
                            "symbol": pick.get("symbol", ""),
                            "name": pick.get("name", ""),
                            "action": action,
                            "confidence": pick.get("confidence", 0),
                            "message": signal_msg,
                        })

            await self._emit_step("open_analysis", "done", f"分析完成: {len(picks)}只选股, {len([p for p in picks if p.get('action') in ('BUY','SELL')])}只操作信号")

            risk_confirmed = bool(all_prefs.get("risk_confirmed", False))
            has_capital = bool(all_prefs.get("max_single_cny") or all_prefs.get("max_daily_cny"))

            if risk_confirmed and has_capital:
                for pick in picks:
                    if pick.get("action") in ("BUY", "SELL") and pick.get("confidence", 0) >= 0.65:
                        trade_result = await self.execute_trade_decision(pick, user_prefs=all_prefs)
                        await self._emit("trade_result", {
                            "ok": trade_result.get("ok", False),
                            "action": trade_result.get("action", pick.get("action")),
                            "symbol": trade_result.get("symbol", pick.get("symbol")),
                            "name": trade_result.get("name", pick.get("name")),
                            "amount_cny": str(trade_result.get("amount_cny", "")),
                            "reason": trade_result.get("reason", ""),
                        })
        else:
            error_msg = result.get("error", "分析未返回结果") if not result.get("ok") else "无选股信号"
            await self._emit("chat", {
                "text": f"📊 开盘分析: {error_msg}",
                "expression": "neutral",
            })
            await self._emit_step("open_analysis", "done", f"分析完成: {error_msg}")

        self._last_analysis = result

    async def _phase_risk_confirm(self):
        """Auto-confirm with defaults, only ask user if capital amount is unset.
        
        AI自主操盘原则：只问资金金额，其他全部AI自动决定。
        - 如果用户已经设定过金额 → 自动沿用，不需确认
        - 如果从未设过 → 问用户"你要投入多少？"
        - 止损5%/止盈10%/最多3只持仓 → AI自动设，不用问
        """
        await self._emit_step("risk_confirm", "running", "确认今日风控参数...")

        try:
            from potato.user_prefs import UserPrefs
            prefs = UserPrefs()
            all_prefs = prefs.get_all()
        except Exception:
            all_prefs = {}

        # Default values — AI decides these, not user
        defaults = {
            "risk_level": "moderate",
            "max_open_positions": 3,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "risk_confirmed": False,
        }

        # Check if user has ever set capital amounts
        has_capital = bool(all_prefs.get("max_single_cny") or all_prefs.get("max_single_trade_cny") or all_prefs.get("max_daily_cny") or all_prefs.get("max_daily_trade_cny"))

        # Apply user's capital settings or defaults
        for key, default_val in defaults.items():
            if key not in all_prefs or all_prefs[key] is None:
                all_prefs[key] = default_val

        if has_capital:
            single = all_prefs.get("max_single_trade_cny") or all_prefs.get("max_single_cny")
            daily = all_prefs.get("max_daily_trade_cny") or all_prefs.get("max_daily_cny")

            rl = all_prefs.get("risk_level", "moderate")
            rl_cn = {"conservative": "保守", "moderate": "稳健", "aggressive": "激进"}.get(rl, rl)

            summary_lines = [f"✅ 今日操盘参数已自动确认（{rl_cn}模式）"]
            if single:
                summary_lines.append(f"  单笔限额: ¥{single}")
            if daily:
                summary_lines.append(f"  日限额: ¥{daily}")
            summary_lines.append(f"  最多持仓: {all_prefs.get('max_open_positions', 3)}只")
            summary_lines.append(f"  止损: {float(all_prefs.get('stop_loss_pct', 0.05))*100:.0f}%")
            summary_lines.append(f"  止盈: {float(all_prefs.get('take_profit_pct', 0.10))*100:.0f}%")

            await self._emit("risk_confirm_prompt", {
                "confirmed": True,
                "source": "auto",
                "params": all_prefs,
                "summary": "\n".join(summary_lines),
                "message": "操盘参数已自动设置。如需调整金额，直接告诉我就行。",
            })
            await self._emit_step("risk_confirm", "done", "参数自动确认，开始操盘")
            return

        # First time — ask user for capital amount
        await self._emit("risk_confirm_prompt", {
            "confirmed": False,
            "source": "first_time",
            "params": defaults,
            "summary": "🔐 首次操盘——只需告诉我一件事：你准备投入多少钱？\n\n其他参数AI自动设置：\n  💹 稳健模式\n  📊 最多同时3只股票\n  🛑 止损5% / 止盈10%\n\n直接回复金额即可，如：\n  「单笔最多1万，每天最多3万」\n  「投入5千」\n  「全部激进模式」",
            "message": "首次操盘请确认资金金额。止损止盈等参数AI自动设置。",
        })
        await self._emit_step("risk_confirm", "waiting", "等待用户确认资金金额")

    async def _phase_mid_review(self):
        await self._emit_step("mid_review", "running", "午间复盘中...")

        positions = self.journal.get_open_positions_summary()
        if not positions:
            await self._emit("chat", {
                "text": "📊 午间复盘：当前无持仓，继续观望",
                "expression": "neutral",
            })
            await self._emit_step("mid_review", "done", "午间复盘：无持仓")
            return

        alerts = await self.journal.check_stops_targets()

        pos_lines = []
        for pos in positions:
            pnl_pct = 0
            try:
                entry = float(pos.get("entry_price", 0))
                current = float(pos.get("current_price", 0) or pos.get("entry_price", 0))
                if entry > 0:
                    pnl_pct = (current - entry) / entry * 100
            except Exception:
                pass
            pnl_icon = "🟢" if pnl_pct > 0 else "🔴" if pnl_pct < 0 else "⚪"
            pos_lines.append(f"{pnl_icon} {pos['name']}({pos['symbol']}) "
                          f"入场¥{pos.get('entry_price','-')} 当前¥{pos.get('current_price','-')} "
                          f"{'+' if pnl_pct>=0 else ''}{pnl_pct:.1f}% "
                          f"止损¥{pos.get('stop_loss_price','-')} 目标¥{pos.get('target_price','-')}")

        alert_lines = []
        for a in alerts:
            trigger_cn = "🎯 止盈触发" if a["trigger"] == "take_profit" else "🛑 止损触发"
            alert_lines.append(f"{trigger_cn}: {a['name']}({a['symbol']}) 当前¥{a['current_price']}")

        summary = f"📊 午间复盘：{len(positions)}只持仓\n" + "\n".join(pos_lines)
        if alert_lines:
            summary += f"\n\n⚠️ 触发信号：\n" + "\n".join(alert_lines)
            summary += "\n\nAI正在自动处理触发信号..."

        await self._emit("chat", {
            "text": summary,
            "expression": "thinking" if alerts else "happy",
        })

        await self._emit("mid_review_result", {
            "positions": len(positions),
            "alerts": len(alerts),
            "alert_details": alerts,
            "summary": summary,
        })

        try:
            from potato.user_prefs import UserPrefs
            prefs = UserPrefs()
            all_prefs = prefs.get_all()
        except Exception:
            all_prefs = {}

        for a in alerts:
            if a["trigger"] == "stop_loss":
                trade_result = await self.execute_trade_decision({
                    "action": "SELL",
                    "symbol": a.get("symbol", ""),
                    "name": a.get("name", ""),
                    "entry_price": str(a.get("entry_price", "0")),
                    "current_price": str(a.get("current_price", "0")),
                    "confidence": 0.95,
                    "reasoning": f"止损触发：当前价¥{a.get('current_price')}已跌破止损价¥{a.get('stop_loss_price')}",
                }, user_prefs=all_prefs)
                await self._emit("trade_result", {
                    "ok": trade_result.get("ok", False),
                    "action": "SELL",
                    "symbol": a.get("symbol", ""),
                    "name": a.get("name", ""),
                    "reason": f"🛑 止损卖出: {trade_result.get('reason', '止损触发')}",
                    "amount_cny": str(trade_result.get("amount_cny", "")),
                })
            elif a["trigger"] == "take_profit":
                trade_result = await self.execute_trade_decision({
                    "action": "SELL",
                    "symbol": a.get("symbol", ""),
                    "name": a.get("name", ""),
                    "entry_price": str(a.get("entry_price", "0")),
                    "current_price": str(a.get("current_price", "0")),
                    "confidence": 0.9,
                    "reasoning": f"止盈触发：当前价¥{a.get('current_price')}已达目标价¥{a.get('target_price')}",
                }, user_prefs=all_prefs)
                await self._emit("trade_result", {
                    "ok": trade_result.get("ok", False),
                    "action": "SELL",
                    "symbol": a.get("symbol", ""),
                    "name": a.get("name", ""),
                    "reason": f"🎯 止盈卖出: {trade_result.get('reason', '止盈触发')}",
                    "amount_cny": str(trade_result.get("amount_cny", "")),
                })

        await self._emit_step("mid_review", "done", summary[:80])

    async def _phase_pre_close(self):
        await self._emit_step("pre_close", "running", "尾盘评估中...")
        positions = self.journal.get_open_positions_summary()
        if not positions:
            await self._emit("chat", {
                "text": "📊 尾盘评估：当前无持仓，全天观望",
                "expression": "neutral",
            })
            await self._emit_step("pre_close", "done", "尾盘评估：无持仓")
            return

        alerts = await self.journal.check_stops_targets()

        stop_alerts = [a for a in alerts if a["trigger"] == "stop_loss"]
        target_alerts = [a for a in alerts if a["trigger"] == "take_profit"]

        try:
            from potato.user_prefs import UserPrefs
            prefs = UserPrefs()
            all_prefs = prefs.get_all()
        except Exception:
            all_prefs = {}

        executed_trades = []
        for a in stop_alerts:
            result = await self.execute_trade_decision({
                "action": "SELL",
                "symbol": a.get("symbol", ""),
                "name": a.get("name", ""),
                "entry_price": str(a.get("entry_price", "0")),
                "current_price": str(a.get("current_price", "0")),
                "confidence": 0.95,
                "reasoning": f"尾盘止损触发：当前价¥{a.get('current_price')}已跌破止损价¥{a.get('stop_loss_price')}",
            }, user_prefs=all_prefs)
            executed_trades.append(("🛑 止损卖出", a.get("name", ""), a.get("symbol", ""), result))

        for a in target_alerts:
            result = await self.execute_trade_decision({
                "action": "SELL",
                "symbol": a.get("symbol", ""),
                "name": a.get("name", ""),
                "entry_price": str(a.get("entry_price", "0")),
                "current_price": str(a.get("current_price", "0")),
                "confidence": 0.9,
                "reasoning": f"尾盘止盈触发：当前价¥{a.get('current_price')}已达目标价¥{a.get('target_price')}",
            }, user_prefs=all_prefs)
            executed_trades.append(("🎯 止盈卖出", a.get("name", ""), a.get("symbol", ""), result))

        near_close = []
        for pos in positions:
            if pos.get("stop_loss_price") and pos.get("entry_price"):
                try:
                    sl_dist = abs(float(pos["stop_loss_price"]) - float(pos["entry_price"])) / float(pos["entry_price"]) * 100
                    if sl_dist < 2:
                        near_close.append(f"⚠️ {pos['name']} 止损距离仅{sl_dist:.1f}%")
                except Exception:
                    pass

        summary_lines = [f"📊 尾盘评估：{len(positions)}只持仓"]
        if executed_trades:
            summary_lines.append("AI自动执行：")
            for label, name, symbol, result in executed_trades:
                status = "✅" if result.get("ok") else "❌"
                summary_lines.append(f"  {status} {label} {name}({symbol})")
        if near_close:
            summary_lines.append("距离止损近的：")
            summary_lines.extend(near_close)
        remaining = [pos for pos in positions if not any(
            a.get("symbol") == pos.get("symbol") for a in (stop_alerts + target_alerts)
        )]
        if remaining:
            summary_lines.append(f"继续持有{len(remaining)}只过夜")

        summary = "\n".join(summary_lines)
        await self._emit("chat", {
            "text": summary,
            "expression": "thinking" if executed_trades else "happy",
        })

        await self._emit("pre_close_result", {
            "positions": len(positions),
            "stop_alerts": len(stop_alerts),
            "target_alerts": len(target_alerts),
            "executed": len(executed_trades),
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

        await self._emit("chat", {
            "text": summary,
            "expression": "happy" if review.total_pnl and float(review.total_pnl) >= 0 else "sad",
        })

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