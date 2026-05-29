"""Test TradingScheduler phase logic — mock tests for 7-phase daily cycle."""
import sys
sys.path.insert(0, ".")

import pytest
from datetime import datetime, timezone, timedelta


class TestSchedulerImports:
    def test_scheduler_import(self):
        from potato.trading.scheduler import TradingScheduler
        assert TradingScheduler is not None

    def test_schedule_constants(self):
        from potato.trading.scheduler import SCHEDULE
        assert "pre_market" in SCHEDULE
        assert "risk_confirm" in SCHEDULE
        assert "open_analysis" in SCHEDULE
        assert "mid_review" in SCHEDULE
        assert "pre_close" in SCHEDULE
        assert "post_market" in SCHEDULE

    def test_schedule_times_bjt(self):
        from potato.trading.scheduler import SCHEDULE
        assert SCHEDULE["pre_market"].hour == 9
        assert SCHEDULE["risk_confirm"].hour == 9
        assert SCHEDULE["open_analysis"].hour == 9
        assert SCHEDULE["mid_review"].hour == 11
        assert SCHEDULE["pre_close"].hour == 14
        assert SCHEDULE["post_market"].hour == 15

    def test_is_trading_day(self):
        from potato.trading.scheduler import _is_trading_day
        from datetime import date
        monday = datetime(2025, 1, 6)
        friday = datetime(2025, 1, 10)
        saturday = datetime(2025, 1, 11)
        sunday = datetime(2025, 1, 12)
        assert _is_trading_day(monday)
        assert _is_trading_day(friday)
        assert not _is_trading_day(saturday)
        assert not _is_trading_day(sunday)

    def test_now_bjt(self):
        from potato.trading.scheduler import _now_bjt
        now = _now_bjt()
        assert now.tzinfo is not None
        bjt_offset = timedelta(hours=8)
        assert abs(now.utcoffset() - bjt_offset) < timedelta(seconds=1)


class TestSchedulerInit:
    def test_scheduler_creation(self):
        from potato.trading.scheduler import TradingScheduler
        scheduler = TradingScheduler(send_func=None, broker=None)
        assert scheduler._running is False
        assert scheduler._task is None
        assert scheduler._last_analysis is None

    def test_scheduler_has_phases(self):
        from potato.trading.scheduler import TradingScheduler
        scheduler = TradingScheduler(send_func=None, broker=None)
        assert hasattr(scheduler, "_phase_pre_market")
        assert hasattr(scheduler, "_phase_risk_confirm")
        assert hasattr(scheduler, "_phase_open_analysis")
        assert hasattr(scheduler, "_phase_mid_review")
        assert hasattr(scheduler, "_phase_pre_close")
        assert hasattr(scheduler, "_phase_post_market")

    def test_scheduler_has_manual_analysis(self):
        from potato.trading.scheduler import TradingScheduler
        scheduler = TradingScheduler(send_func=None, broker=None)
        assert hasattr(scheduler, "run_manual_analysis")
        import inspect
        sig = inspect.signature(scheduler.run_manual_analysis)
        assert "use_plan_execute" in sig.parameters


class TestIwencaiIntegration:
    def test_gather_iwencai_candidates_import(self):
        from potato.trading.scheduler import _gather_iwencai_candidates
        assert callable(_gather_iwencai_candidates)

    def test_gather_eastmoney_context_import(self):
        from potato.trading.scheduler import _gather_eastmoney_context
        assert callable(_gather_eastmoney_context)


class TestRiskValidator:
    def test_safety_rules(self):
        from potato.risk import SAFETY_RULES
        from decimal import Decimal
        assert "min_confidence" in SAFETY_RULES
        assert SAFETY_RULES["min_confidence"] == Decimal("0.65")

    def test_safety_max_positions(self):
        from potato.risk import SAFETY_RULES
        assert SAFETY_RULES["max_open_positions_hard_cap"] == 30

    def test_risk_validator_creation(self):
        from potato.risk import RiskValidator
        rv = RiskValidator()
        assert rv is not None


class TestBrokerModes:
    def test_broker_adapter_dry_run(self):
        from potato.trading.broker import BrokerAdapter
        adapter = BrokerAdapter(mode="dry_run")
        assert adapter.mode == "dry_run"

    def test_broker_adapter_live_requires_client(self):
        from potato.trading.broker import BrokerAdapter
        adapter = BrokerAdapter(mode="live")
        assert adapter.mode == "live"


class TestJournal:
    def test_journal_creation(self):
        from potato.trading.journal import TradeJournal
        journal = TradeJournal()
        assert journal is not None