"""Tests for 7-phase trading loop — mock validation of the complete daily cycle.

Validates that each phase can execute end-to-end with mocked external dependencies.
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone, timedelta, time
from unittest.mock import AsyncMock, MagicMock, patch

from potato.trading.scheduler import TradingScheduler, SCHEDULE, BJT


class MockSendFunc:
    def __init__(self):
        self.events = []

    async def __call__(self, event_type, data):
        self.events.append({"type": event_type, "data": data})


class TestScheduleConstants:
    """Validate schedule configuration."""

    def test_schedule_has_six_phases(self):
        assert len(SCHEDULE) == 6

    def test_schedule_phases_match_expected(self):
        expected = {"pre_market", "risk_confirm", "open_analysis", "mid_review", "pre_close", "post_market"}
        assert set(SCHEDULE.keys()) == expected

    def test_schedule_times_are_time_objects(self):
        for phase, t in SCHEDULE.items():
            assert isinstance(t, time), f"Phase {phase} value should be datetime.time"

    def test_schedule_times_are_bjt_business_hours(self):
        for phase, t in SCHEDULE.items():
            assert 9 <= t.hour <= 15, f"Phase {phase} at {t.hour}:{t.minute:02d} outside trading hours"

    def test_bjt_is_utc_plus_8(self):
        assert BJT.utcoffset(datetime(2025, 1, 1)).total_seconds() == 8 * 3600


class TestSchedulerInit:
    """Test scheduler constructor and defaults."""

    def test_default_init(self):
        sched = TradingScheduler()
        assert sched.send_func is None
        assert sched._running is False
        assert sched._last_analysis is None
        assert hasattr(sched, "journal")
        assert hasattr(sched, "executor")

    def test_init_with_send_func(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        assert sched.send_func is sf


class TestRiskConfirm:
    """Test risk confirmation phase."""

    @pytest.mark.asyncio
    async def test_risk_confirm_auto_when_capital_set(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        with patch("potato.trading.scheduler.UserPrefs", create=True) as MockPrefs:
            mock_prefs = MagicMock()
            mock_prefs.get_all.return_value = {
                "max_single_cny": 10000,
                "max_daily_cny": 30000,
                "risk_level": "moderate",
                "max_open_positions": 3,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.10,
                "risk_confirmed": True,
            }
            MockPrefs.return_value = mock_prefs
            with patch.dict("sys.modules", {"potato.user_prefs": MagicMock(UserPrefs=MockPrefs)}):
                await sched._phase_risk_confirm()
        assert any(e["type"] == "risk_confirm_prompt" for e in sf.events)
        confirm_event = next(e for e in sf.events if e["type"] == "risk_confirm_prompt")
        assert confirm_event["data"]["confirmed"] is True
        assert confirm_event["data"]["source"] == "auto"

    @pytest.mark.asyncio
    async def test_risk_confirm_prompt_when_no_capital(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        with patch("potato.trading.scheduler.UserPrefs", create=True) as MockPrefs:
            mock_prefs = MagicMock()
            mock_prefs.get_all.return_value = {}
            MockPrefs.return_value = mock_prefs
            with patch.dict("sys.modules", {"potato.user_prefs": MagicMock(UserPrefs=MockPrefs)}):
                await sched._phase_risk_confirm()
        assert any(e["type"] == "risk_confirm_prompt" for e in sf.events)
        prompt_event = next(e for e in sf.events if e["type"] == "risk_confirm_prompt")
        assert prompt_event["data"]["confirmed"] is False


class TestExecuteTradeDecision:
    """Test trade execution logic."""

    @pytest.mark.asyncio
    async def test_execute_trade_declines_zero_price(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        pick = {
            "symbol": "999999", "action": "BUY", "confidence": 0.80,
            "name": "不存在", "position_size": 0.2,
        }
        with patch("potato.trading.scheduler.fetch_realtime_quote", new_callable=AsyncMock, return_value=None):
            result = await sched.execute_trade_decision(pick)
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_execute_trade_with_price(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        mock_exec = AsyncMock(return_value={
            "ok": True, "action": "BUY", "symbol": "600519", "quantity": 100, "price": 1500.0,
        })
        with patch.object(sched.executor, "validate_and_execute", mock_exec):
            pick = {
                "symbol": "600519", "action": "BUY", "confidence": 0.80,
                "name": "贵州茅台", "price": 1500.0, "position_size": 0.2,
            }
            result = await sched.execute_trade_decision(pick, user_prefs={"max_single_cny": 10000})
        assert result["ok"] is True


class TestPreMarket:
    """Test pre-market scan phase."""

    @pytest.mark.asyncio
    async def test_pre_market_emits_step_events(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        with patch("potato.trading.scheduler.get_stock_changes", new_callable=AsyncMock, return_value=[]), \
             patch("potato.trading.scheduler.get_hot_tables", new_callable=AsyncMock, return_value=[]), \
             patch("potato.trading.scheduler.IwencaiClient") as mock_ic_cls, \
             patch("potato.trading.scheduler.analyze_sentiment", new_callable=AsyncMock, return_value="偏多 (60/100)"), \
             patch.object(sched, "run_manual_analysis", new_callable=AsyncMock, return_value={
                 "ok": True, "analysis": {"stock_picks": []}, "raw_text": "今日观望",
             }):
            mock_ic = MagicMock()
            mock_ic.select_stocks.return_value = []
            mock_ic_cls.return_value = mock_ic
            with patch.dict("sys.modules", {"potato.intel": MagicMock(fetch_headlines=lambda **kw: [])}):
                await sched._phase_pre_market()
        step_events = [e for e in sf.events if e["type"] == "schedule_step"]
        assert len(step_events) >= 1


class TestMidReview:
    """Test mid-day review phase."""

    @pytest.mark.asyncio
    async def test_mid_review_no_positions(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        with patch.object(sched.journal, "check_stops_targets", new_callable=AsyncMock, return_value=[]):
            await sched._phase_mid_review()
        step_events = [e for e in sf.events if e["type"] == "schedule_step"]
        assert len(step_events) >= 1

    @pytest.mark.asyncio
    async def test_mid_review_stop_loss_trigger(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        mock_exec = AsyncMock(return_value={"ok": True, "action": "SELL"})
        with patch.object(sched.journal, "get_open_positions_summary", return_value=[
            {"symbol": "600519", "name": "贵州茅台", "entry_price": 1500.0,
             "current_price": 1400.0, "stop_loss_price": 1425.0, "target_price": 1650.0},
        ]), \
             patch.object(sched.journal, "check_stops_targets", new_callable=AsyncMock, return_value=[
            {"symbol": "600519", "trigger": "stop_loss", "name": "贵州茅台",
             "entry_price": 1500.0, "current_price": 1400.0, "stop_loss_price": 1425.0},
        ]), \
             patch.object(sched, "execute_trade_decision", mock_exec), \
             patch.dict("sys.modules", {"potato.user_prefs": MagicMock()}):
            await sched._phase_mid_review()
        assert mock_exec.called


class TestPreClose:
    """Test pre-close review phase."""

    @pytest.mark.asyncio
    async def test_pre_close_with_positions(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        with patch.object(sched.journal, "check_stops_targets", new_callable=AsyncMock, return_value=[]):
            await sched._phase_pre_close()
        assert any(e["type"] in ("schedule_step", "position_summary") for e in sf.events)


class TestPostMarket:
    """Test post-market review phase."""

    @pytest.mark.asyncio
    async def test_post_market_daily_review(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        from potato.trading.journal import DailyReview
        from decimal import Decimal
        mock_review = DailyReview(
            date="2025-01-01", total_trades=0, winning_trades=0, losing_trades=0,
            win_rate=Decimal("0"), total_pnl=Decimal("0"), avg_win=Decimal("0"),
            avg_loss=Decimal("0"), profit_factor=Decimal("0"), max_single_win=Decimal("0"),
            max_single_loss=Decimal("0"), max_drawdown_pct=Decimal("0"),
            long_trades=0, short_trades=0, long_win_rate=Decimal("0"), short_win_rate=Decimal("0"),
            best_trade_id="", worst_trade_id="", ai_summary="", ai_lessons=[], strategy_adjustments=[],
        )
        with patch.object(sched.journal, "generate_daily_review", return_value=mock_review), \
             patch.object(sched, "run_manual_analysis", new_callable=AsyncMock, return_value={
                 "ok": True, "analysis": {"stock_picks": []}, "raw_text": "复盘完成",
             }):
            await sched._phase_post_market()
        step_events = [e for e in sf.events if e["type"] == "schedule_step"]
        assert any(s["data"].get("phase") == "post_market" for s in step_events)


class TestRunManualAnalysis:
    """Test run_manual_analysis with both analysis paths."""

    @pytest.mark.asyncio
    async def test_run_manual_analysis_standard(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        with patch("potato.trading.scheduler.deep_analysis", new_callable=AsyncMock, return_value={
            "ok": True, "analysis": {"stock_picks": []}, "raw_text": "分析完成",
        }):
            result = await sched.run_manual_analysis(symbols=["600519"])
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_run_manual_analysis_plan_execute(self):
        sf = MockSendFunc()
        sched = TradingScheduler(send_func=sf)
        mock_result = {"ok": True, "analysis": {"stock_picks": []}, "raw_text": "深度分析完成"}
        with patch("potato.trading.scheduler.run_plan_execute_analysis", new_callable=AsyncMock, return_value=mock_result), \
             patch("potato.trading.scheduler._gather_eastmoney_context", new_callable=AsyncMock, return_value="行情数据"), \
             patch("potato.trading.scheduler.analyze_sentiment", new_callable=AsyncMock, return_value="偏多 (60/100)"):
            result = await sched.run_manual_analysis(symbols=["600519"], use_plan_execute=True)
        assert result["ok"] is True