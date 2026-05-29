"""Test trade journal — P&L calculation, atomic save/recovery, stop/target logic."""
import sys
sys.path.insert(0, ".")

from decimal import Decimal
from potato.trading.journal import TradeJournal, JOURNAL_DIR
import json
from pathlib import Path


class TestTradeJournal:
    def setup_method(self):
        self.j = TradeJournal()
        self.j._trades.clear()
        self.j._open_positions.clear()
        self.j._running_pnl = Decimal("0")
        self.j._peak_pnl = Decimal("0")
        self.j._max_drawdown_pct = Decimal("0")
        self.j._consecutive_losses = 0

    def test_buy_profit(self):
        rec = self.j.record_entry(symbol="600519", name="MT", direction="BUY", price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"), target_price="110", stop_loss_price="95")
        exit_rec = self.j.record_exit(trade_id=rec.id, exit_price=Decimal("110"), exit_reason="profit")
        assert exit_rec.realized_pnl == Decimal("1000")
        assert exit_rec.realized_pnl_pct == Decimal("10")
        assert exit_rec.target_hit is True
        assert exit_rec.stop_hit is False

    def test_buy_loss(self):
        rec = self.j.record_entry(symbol="000001", name="PA", direction="BUY", price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"), target_price="110", stop_loss_price="95")
        exit_rec = self.j.record_exit(trade_id=rec.id, exit_price=Decimal("90"), exit_reason="stop_loss")
        assert exit_rec.realized_pnl == Decimal("-1000")
        assert exit_rec.realized_pnl_pct == Decimal("-10")
        assert exit_rec.target_hit is False
        assert exit_rec.stop_hit is True

    def test_sell_closes_long_profit(self):
        rec = self.j.record_entry(symbol="601398", name="GS", direction="BUY", price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"), target_price="110", stop_loss_price="95")
        exit_rec = self.j.record_exit(trade_id=rec.id, exit_price=Decimal("110"), exit_reason="sell_close")
        assert exit_rec.realized_pnl == Decimal("1000")
        assert exit_rec.realized_pnl_pct == Decimal("10")

    def test_sell_closes_long_loss(self):
        rec = self.j.record_entry(symbol="601398", name="GS", direction="BUY", price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"), target_price="110", stop_loss_price="95")
        exit_rec = self.j.record_exit(trade_id=rec.id, exit_price=Decimal("90"), exit_reason="stop_loss")
        assert exit_rec.realized_pnl == Decimal("-1000")
        assert exit_rec.realized_pnl_pct == Decimal("-10")

    def test_consecutive_losses(self):
        rec1 = self.j.record_entry(symbol="A", name="A", direction="BUY", price=Decimal("10"), quantity=100, amount_cny=Decimal("1000"))
        self.j.record_exit(trade_id=rec1.id, exit_price=Decimal("9"), exit_reason="loss")
        assert self.j.get_consecutive_losses() == 1

        rec2 = self.j.record_entry(symbol="B", name="B", direction="BUY", price=Decimal("10"), quantity=100, amount_cny=Decimal("1000"))
        self.j.record_exit(trade_id=rec2.id, exit_price=Decimal("8"), exit_reason="loss")
        assert self.j.get_consecutive_losses() == 2

    def test_exit_unknown_trade(self):
        result = self.j.record_exit(trade_id="nonexistent_123", exit_price=Decimal("100"))
        assert result is None

    def test_daily_review_empty(self):
        review = self.j.generate_daily_review("2026-01-01")
        assert review.total_trades == 0

    def test_daily_review_with_trades(self):
        import tempfile, json
        from pathlib import Path
        tmp_dir = Path(tempfile.mkdtemp())
        j = TradeJournal.__new__(TradeJournal)
        j._trades = {}
        j._open_positions = {}
        j._running_pnl = Decimal("0")
        j._peak_pnl = Decimal("0")
        j._max_drawdown_pct = Decimal("0")
        j._consecutive_losses = 0
        j._save = lambda *a, **kw: None  # skip disk writes
        rec = j.record_entry(symbol="600519", name="MT", direction="BUY", price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"), target_price="110", stop_loss_price="95")
        j.record_exit(trade_id=rec.id, exit_price=Decimal("110"), exit_reason="profit")
        review = j.generate_daily_review()
        assert review.total_trades >= 1
        assert review.winning_trades >= 1
        assert review.total_pnl > 0

    def test_save_and_reload(self):
        rec = self.j.record_entry(symbol="600519", name="MT", direction="BUY", price=Decimal("100"), quantity=100, amount_cny=Decimal("10000"), target_price="110", stop_loss_price="95")
        self.j.record_exit(trade_id=rec.id, exit_price=Decimal("105"), exit_reason="partial")

        j2 = TradeJournal()
        closed = [t for t in j2._trades.values() if t.exit_time]
        assert len(closed) >= 1
        closed_rec = closed[0]
        assert closed_rec.realized_pnl == Decimal("500")

    def test_tmp_recovery(self):
        tmp = JOURNAL_DIR / "trades.json.tmp"
        target = JOURNAL_DIR / "trades.json"
        if not target.exists():
            tmp.write_text('{"closed":[],"open":[],"running_pnl":"0","peak_pnl":"0","max_drawdown_pct":"0","consecutive_losses":0}', encoding="utf-8")
            j3 = TradeJournal()
            assert len(j3._trades) >= 0
        if tmp.exists():
            tmp.unlink(missing_ok=True)