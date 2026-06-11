import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from eudora.backtest import Backtester  # noqa: E402
from eudora.strategy.sma_crossover import SmaCrossover  # noqa: E402


def _two_cycles():
    # Up, down, up — enough for at least one full buy->sell round trip with a
    # fast(5)/slow(15) crossover strategy.
    series = []
    series += [50.0 - i * 0.3 for i in range(30)]   # decline
    series += [41.0 + i * 0.8 for i in range(40)]   # rally  -> golden cross + buy
    series += [73.0 - i * 0.9 for i in range(40)]   # drop   -> death cross + sell
    series += [37.0 + i * 0.7 for i in range(40)]   # rally  -> buy again
    return series


class TestBacktester(unittest.TestCase):
    def setUp(self):
        self.strat = SmaCrossover(fast=5, slow=15, rsi_overbought=None)
        self.closes = {"X": _two_cycles()}

    def test_runs_and_reports(self):
        bt = Backtester(self.strat, self.closes, starting_cash=500.0, order_notional=100.0)
        result = bt.run()
        self.assertEqual(len(result.equity_curve), len(self.closes["X"]))
        self.assertGreater(len(result.trades), 0)
        # Equity is conserved sensibly: never below zero.
        self.assertTrue(all(e >= 0 for e in result.equity_curve))

    def test_produces_round_trip(self):
        bt = Backtester(self.strat, self.closes, starting_cash=500.0, order_notional=100.0)
        result = bt.run()
        self.assertGreaterEqual(len(result.round_trips), 1)
        wr = result.win_rate
        self.assertIsNotNone(wr)
        self.assertGreaterEqual(wr, 0.0)
        self.assertLessEqual(wr, 1.0)

    def test_no_buy_when_unaffordable(self):
        # order_notional below one share's price => floors to 0 shares => no trades.
        bt = Backtester(self.strat, self.closes, starting_cash=500.0, order_notional=1.0)
        result = bt.run()
        self.assertEqual(len(result.trades), 0)
        self.assertAlmostEqual(result.final_equity, 500.0)

    def test_metrics_bounds(self):
        bt = Backtester(self.strat, self.closes, starting_cash=500.0, order_notional=100.0)
        result = bt.run()
        self.assertGreaterEqual(result.max_drawdown, 0.0)
        self.assertLessEqual(result.max_drawdown, 1.0)
        self.assertIsInstance(result.summary(), str)


if __name__ == "__main__":
    unittest.main()
