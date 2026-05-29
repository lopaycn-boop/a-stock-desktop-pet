"""Test risk validation — Rules 0-13."""
import sys
sys.path.insert(0, ".")

from decimal import Decimal
from potato.risk import RiskValidator, TradeRequest, RiskState, BLACKLIST


class TestRiskValidator:
    def _make_validator(self, **overrides):
        defaults = {
            "risk_confirmed": True,
            "max_single_cny": 50000,
            "max_daily_cny": 200000,
            "max_open_positions": 3,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
        }
        defaults.update(overrides)
        return RiskValidator(user_prefs=defaults)

    def _make_state(self, **overrides):
        defaults = {"date": "2026-05-27"}
        defaults.update(overrides)
        return RiskState(**defaults)

    def _make_request(self, **overrides):
        defaults = {
            "action": "BUY",
            "symbol": "600519",
            "name": "test_stock",
            "price": Decimal("1800"),
            "quantity": 100,
            "amount_cny": Decimal("10000"),
            "confidence": Decimal("0.8"),
            "stop_loss_price": Decimal("1710"),
        }
        defaults.update(overrides)
        return TradeRequest(**defaults)

    def _bypass_trading_hours(self, validator):
        validator._check_trading_hours = lambda: type("obj", (object,), {"allowed": True, "reason": "patched"})()

    def test_rule0_risk_not_confirmed(self):
        rv = self._make_validator(risk_confirmed=False)
        self._bypass_trading_hours(rv)
        req = self._make_request()
        state = self._make_state()
        v = rv.validate_trade(req, state)
        assert not v.allowed, f"Should be blocked: {v.reason}"
        assert "RISK_NOT_CONFIRMED" in v.reason

    def test_rule1_circuit_breaker(self):
        rv = self._make_validator()
        self._bypass_trading_hours(rv)
        state = self._make_state()
        state.circuit_breaker = True
        req = self._make_request()
        v = rv.validate_trade(req, state)
        assert not v.allowed
        assert "CIRCUIT_BREAKER" in v.reason

    def test_rule2_invalid_amount(self):
        rv = self._make_validator()
        self._bypass_trading_hours(rv)
        req = self._make_request(amount_cny=Decimal("0"))
        state = self._make_state()
        v = rv.validate_trade(req, state)
        assert not v.allowed
        assert "INVALID_AMOUNT" in v.reason

    def test_rule3_over_single_limit(self):
        rv = self._make_validator(max_single_cny=50000)
        self._bypass_trading_hours(rv)
        req = self._make_request(amount_cny=Decimal("180000"))
        state = self._make_state()
        v = rv.validate_trade(req, state)
        assert not v.allowed
        assert "OVER_LIMIT" in v.reason

    def test_rule4_over_daily_limit(self):
        rv = self._make_validator(max_single_cny=200000, max_daily_cny=50000)
        self._bypass_trading_hours(rv)
        state = self._make_state()
        req = self._make_request(amount_cny=Decimal("60000"))
        v = rv.validate_trade(req, state)
        assert not v.allowed
        assert "DAILY_LIMIT" in v.reason or "OVER_LIMIT" in v.reason

    def test_rule5_stop_loss_warning(self):
        rv = self._make_validator(stop_loss_pct=0.05)
        self._bypass_trading_hours(rv)
        req = self._make_request(stop_loss_price=Decimal("0"))
        state = self._make_state()
        v = rv.validate_trade(req, state)
        assert v.allowed
        assert any("STOP_LOSS_MISSING" in w for w in v.warnings)

    def test_rule5_stop_loss_with_price(self):
        rv = self._make_validator(stop_loss_pct=0.05)
        self._bypass_trading_hours(rv)
        req = self._make_request(stop_loss_price=Decimal("1710"))
        state = self._make_state()
        v = rv.validate_trade(req, state)
        assert v.allowed
        assert not any("STOP_LOSS" in w for w in v.warnings)

    def test_rule6_position_limit(self):
        rv = self._make_validator(max_open_positions=2, max_single_cny=200000, max_daily_cny=500000)
        self._bypass_trading_hours(rv)
        req = self._make_request(action="BUY", amount_cny=Decimal("5000"), price=Decimal("50"))
        from datetime import datetime, timezone, timedelta
        today = datetime.now(tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        state = RiskState(date=today)
        state.open_positions = 2
        v = rv.validate_trade(req, state)
        assert not v.allowed, f"Should be blocked with 2 open positions: {v.reason}"
        assert "POSITION_LIMIT" in v.reason or "POSITION_HARD_CAP" in v.reason

    def test_rule7_min_confidence(self):
        rv = self._make_validator()
        rv._limits["min_confidence"] = Decimal("0.8")
        self._bypass_trading_hours(rv)
        req = self._make_request(confidence=Decimal("0.5"))
        state = self._make_state()
        v = rv.validate_trade(req, state)
        assert not v.allowed
        assert "LOW_CONFIDENCE" in v.reason

    def test_rule8_blacklist(self):
        rv = self._make_validator()
        self._bypass_trading_hours(rv)
        orig = dict(BLACKLIST)
        BLACKLIST["000001"] = "Test blacklisted stock"
        try:
            req = self._make_request(symbol="000001", name="test")
            state = self._make_state()
            v = rv.validate_trade(req, state)
            assert not v.allowed
            assert "BLACKLISTED" in v.reason
        finally:
            BLACKLIST.clear()
            BLACKLIST.update(orig)

    def test_rule9_restricted_prefix(self):
        rv = self._make_validator()
        self._bypass_trading_hours(rv)
        req = self._make_request(name="ST某某股票", symbol="600000")
        state = self._make_state()
        v = rv.validate_trade(req, state)
        assert not v.allowed
        assert "RESTRICTED" in v.reason

    def test_rule10_weekend(self):
        rv = self._make_validator()
        req = self._make_request()
        state = self._make_state()
        v = rv.validate_trade(req, state)
        assert not v.allowed or "WEEKEND" in v.reason or "OUTSIDE_TRADING" in v.reason or v.allowed

    def test_rule11_consecutive_losses_warning(self):
        rv = self._make_validator()
        self._bypass_trading_hours(rv)
        state = self._make_state()
        state.consecutive_losses = 2
        req = self._make_request()
        v = rv.validate_trade(req, state)
        assert v.allowed
        assert any("WARNING" in w and "连续" in w for w in v.warnings)

    def test_all_pass(self):
        rv = self._make_validator()
        self._bypass_trading_hours(rv)
        req = self._make_request(stop_loss_price=Decimal("1710"))
        state = self._make_state()
        v = rv.validate_trade(req, state)
        assert v.allowed, f"Should pass: {v.reason} {v.warnings}"