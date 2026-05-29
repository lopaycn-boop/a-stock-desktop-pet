"""E2E smoke tests — verify full system integration paths.

Run with: python -m pytest tests/test_e2e.py -v

These tests verify that core system paths work end-to-end
without requiring running services (they test module integration, not HTTP).
"""
import sys
sys.path.insert(0, ".")

from decimal import Decimal
from potato.risk import RiskValidator, TradeRequest, RiskState
from potato.trading.journal import TradeJournal
from potato.trading.executor import TradeDecision, TradeExecutor
from potato.vault import _encrypt, _decrypt


class TestE2ETradeFlow:
    """End-to-end trade flow: analysis → validation → execution → journal."""

    def setup_method(self):
        self.journal = TradeJournal()
        self.journal._trades.clear()
        self.journal._open_positions.clear()
        self.journal._running_pnl = Decimal("0")

    def test_full_buy_trade_flow(self):
        # 1. Validate trade through risk
        rv = RiskValidator(user_prefs={
            "risk_confirmed": True, "max_single_cny": 50000,
            "max_daily_cny": 200000, "max_open_positions": 3, "stop_loss_pct": 0.05,
        })
        rv._check_trading_hours = lambda: type("obj", (object,), {"allowed": True, "reason": "p"})()
        state = RiskState(date="2026-05-27")

        req = TradeRequest(
            action="BUY", symbol="600519", name="test",
            price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"),
            confidence=Decimal("0.8"), stop_loss_price=Decimal("95"),
        )
        verdict = rv.validate_trade(req, state)
        assert verdict.allowed, f"Trade should pass: {verdict.reason}"

        # 2. Record entry in journal
        rec = self.journal.record_entry(
            symbol="600519", name="test", direction="BUY",
            price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"),
            target_price="110", stop_loss_price="95",
        )
        assert rec.id
        assert len(self.journal._open_positions) == 1

        # 3. Record exit with profit
        exit_rec = self.journal.record_exit(
            trade_id=rec.id, exit_price=Decimal("110"), exit_reason="take_profit",
        )
        assert exit_rec.realized_pnl == Decimal("1000")
        assert exit_rec.realized_pnl_pct == Decimal("10")
        assert exit_rec.target_hit is True
        assert len(self.journal._open_positions) == 0

        # 4. Generate daily review
        review = self.journal.generate_daily_review()
        assert review.total_trades >= 1
        assert review.winning_trades >= 1


class TestE2EVaultFlow:
    """End-to-end vault encryption flow."""

    def test_store_retrieve_cycle(self):
        encrypted = _encrypt("sk-test-api-key-12345678")
        assert encrypted != "sk-test-api-key-12345678"
        decrypted = _decrypt(encrypted)
        assert decrypted == "sk-test-api-key-12345678"

    def test_decrypt_garbage_fails(self):
        try:
            _decrypt("not-encrypted-garbage-data!!!")
            assert False, "Should raise RuntimeError"
        except RuntimeError:
            pass

    def test_special_characters(self):
        for val in ["p@ss:w0rd!", "中文密钥", "key-with-hyphens_123"]:
            assert _decrypt(_encrypt(val)) == val


class TestE2ERiskFlow:
    """End-to-end risk gate flow with all rules."""

    def test_weekend_blocks_trade(self):
        rv = RiskValidator(user_prefs={"risk_confirmed": True})
        req = TradeRequest(
            action="BUY", symbol="600519", name="test",
            price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"),
            confidence=Decimal("0.8"),
        )
        state = RiskState(date="2026-05-30")
        v = rv.validate_trade(req, state)
        assert not v.allowed or "WEEKEND" in v.reason or "OUTSIDE_TRADING" in v.reason

    def test_unconfirmed_blocks_all(self):
        rv = RiskValidator(user_prefs={"risk_confirmed": False})
        rv._check_trading_hours = lambda: type("obj", (object,), {"allowed": True, "reason": "p"})()
        req = TradeRequest(
            action="BUY", symbol="600519", name="test",
            price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"),
            confidence=Decimal("0.8"),
        )
        state = RiskState(date="2026-05-27")
        v = rv.validate_trade(req, state)
        assert not v.allowed
        assert "RISK_NOT_CONFIRMED" in v.reason

    def test_stop_loss_flows_from_decision_to_request(self):
        td = TradeDecision(
            action="BUY", symbol="600519", name="test",
            price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"),
            confidence=Decimal("0.8"), reasoning="test",
            stop_loss="95",
        )
        sl = Decimal(str(td.stop_loss)) if td.stop_loss else Decimal("0")
        assert sl == Decimal("95")

        from potato.trading.executor import TradeExecutor
        from potato.risk import TradeRequest as TR
        req = TR(
            action=td.action, symbol=td.symbol, name=td.name,
            price=td.price, quantity=td.quantity, amount_cny=td.amount_cny,
            confidence=td.confidence, reasoning=td.reasoning,
            stop_loss_price=Decimal(str(td.stop_loss)) if td.stop_loss else Decimal("0"),
        )
        assert req.stop_loss_price == Decimal("95")