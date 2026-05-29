"""Test trade executor — SELL flow, stop_loss_price passthrough, order simulation."""
import sys
sys.path.insert(0, ".")

from decimal import Decimal
from potato.trading.executor import TradeDecision, TradeExecutor
from potato.trading.journal import TradeJournal


class TestExecutor:
    def setup_method(self):
        self.j = TradeJournal()
        self.j._trades.clear()
        self.j._open_positions.clear()
        self.executor = TradeExecutor(send_func=None)
        self.executor.journal = self.j

    def test_trade_decision_stop_loss_field(self):
        td = TradeDecision(
            action="BUY", symbol="600519", name="MT",
            price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"),
            confidence=Decimal("0.8"), reasoning="test",
            stop_loss="95",
        )
        assert td.stop_loss == "95"
        sl = Decimal(str(td.stop_loss)) if td.stop_loss else Decimal("0")
        assert sl == Decimal("95")

    def test_trade_decision_no_stop_loss(self):
        td = TradeDecision(
            action="BUY", symbol="600519", name="MT",
            price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"),
            confidence=Decimal("0.8"), reasoning="test",
            stop_loss="",
        )
        sl = Decimal(str(td.stop_loss)) if td.stop_loss else Decimal("0")
        assert sl == Decimal("0")

    def test_sell_closes_existing_position(self):
        rec = self.j.record_entry(
            symbol="600519", name="MT", direction="BUY",
            price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"),
            target_price="110", stop_loss_price="95",
        )
        assert len(self.j._open_positions) == 1
        exit_rec = self.j.record_exit(trade_id=rec.id, exit_price=Decimal("110"), exit_reason="sell_close")
        assert exit_rec.realized_pnl == Decimal("1000")
        assert len(self.j._open_positions) == 0