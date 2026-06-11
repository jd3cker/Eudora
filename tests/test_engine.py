import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from eudora.broker.paper import PaperBroker  # noqa: E402
from eudora.engine import Engine, EngineConfig  # noqa: E402
from eudora.feed.base import PriceFeed  # noqa: E402
from eudora.journal import Journal  # noqa: E402
from eudora.risk import RiskLimits, RiskManager  # noqa: E402
from eudora.strategy.sma_crossover import SmaCrossover  # noqa: E402


class FakeFeed(PriceFeed):
    def __init__(self, series):
        self.series = series

    def closes(self, symbol, lookback):
        return self.series[-lookback:]


def _golden_cross_series():
    # Flat history (fast SMA == slow SMA == 100), then one bar high enough that
    # the fast SMA crosses above the slow SMA ON THE FINAL bar — which is when a
    # daily bot evaluates. A single close > 100 is sufficient (see arithmetic in
    # SmaCrossover): fast(10) jumps more than slow(30) from one elevated close.
    return [100.0] * 60 + [105.0]


class TestEngine(unittest.TestCase):
    def _engine(self, dry_run, series):
        feed = FakeFeed(series)
        broker = PaperBroker(starting_cash=10_000.0)
        broker.set_quote("TEST", series[-1])
        risk = RiskManager(RiskLimits(
            max_order_notional=10_000.0,
            max_daily_notional=10_000.0,
            kill_switch_file=os.path.join(tempfile.gettempdir(), "eudora_nope"),
        ))
        self.jpath = os.path.join(tempfile.mkdtemp(), "trades.jsonl")
        journal = Journal(self.jpath)
        cfg = EngineConfig(symbols=["TEST"], lookback=200, order_notional=1000.0, dry_run=dry_run)
        strat = SmaCrossover(fast=10, slow=30, rsi_overbought=None)
        return Engine(strat, broker, feed, risk, journal, cfg), broker

    def _read_journal(self):
        with open(self.jpath) as fh:
            import json
            return [json.loads(line) for line in fh if line.strip()]

    def test_dry_run_does_not_trade(self):
        engine, broker = self._engine(dry_run=True, series=_golden_cross_series())
        engine.run_once()
        self.assertEqual(broker.get_positions(), {})  # no real position
        rows = self._read_journal()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "skipped")
        self.assertIn("DRY RUN", rows[0]["reason"])

    def test_live_paper_buys_on_cross(self):
        engine, broker = self._engine(dry_run=False, series=_golden_cross_series())
        engine.run_once()
        pos = broker.get_positions()
        self.assertIn("TEST", pos)
        self.assertGreater(pos["TEST"].quantity, 0)
        rows = self._read_journal()
        self.assertEqual(rows[-1]["status"], "placed")
        self.assertEqual(rows[-1]["side"], "buy")

    def test_no_signal_no_journal(self):
        engine, _ = self._engine(dry_run=False, series=[100.0] * 80)
        engine.run_once()
        self.assertFalse(os.path.exists(self.jpath) and self._read_journal())


if __name__ == "__main__":
    unittest.main()
