import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from eudora.risk import RiskLimits, RiskManager  # noqa: E402
from eudora.strategy.base import Side  # noqa: E402


class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.limits = RiskLimits(
            max_order_notional=200.0,
            max_daily_notional=500.0,
            max_daily_orders=20,
            max_orders_in_window=3,
            max_orders_window_sec=60.0,
            allow_short=False,
            kill_switch_file=os.path.join(tempfile.gettempdir(), "eudora_no_such_kill"),
        )
        self.rm = RiskManager(limits=self.limits)

    def test_allows_normal_order(self):
        ok, reason = self.rm.check(Side.BUY, 10, 10.0, 0.0, now=1000.0)
        self.assertTrue(ok, reason)

    def test_blocks_oversized_order(self):
        ok, reason = self.rm.check(Side.BUY, 30, 10.0, 0.0, now=1000.0)
        self.assertFalse(ok)
        self.assertIn("per-order cap", reason)

    def test_blocks_short(self):
        ok, reason = self.rm.check(Side.SELL, 5, 10.0, 0.0, now=1000.0)
        self.assertFalse(ok)
        self.assertIn("short", reason)

    def test_allows_sell_within_position(self):
        ok, _ = self.rm.check(Side.SELL, 5, 10.0, 5.0, now=1000.0)
        self.assertTrue(ok)

    def test_daily_notional_cap(self):
        # Space orders >window apart so the circuit breaker (tested separately)
        # doesn't fire first; here we isolate the daily-notional limit.
        t = 1000.0
        for _ in range(5):  # 5 * (10*10=100) = 500, the cap
            ok, _ = self.rm.check(Side.BUY, 10, 10.0, 0.0, now=t)
            self.assertTrue(ok)
            self.rm.record_fill(10, 10.0, now=t)
            t += 61
        ok, reason = self.rm.check(Side.BUY, 10, 10.0, 0.0, now=t)
        self.assertFalse(ok)
        self.assertIn("daily notional", reason)

    def test_circuit_breaker(self):
        t = 1000.0
        for _ in range(3):  # window allows 3
            ok, _ = self.rm.check(Side.BUY, 1, 10.0, 0.0, now=t)
            self.assertTrue(ok)
            self.rm.record_fill(1, 10.0, now=t)
            t += 1
        ok, reason = self.rm.check(Side.BUY, 1, 10.0, 0.0, now=t)
        self.assertFalse(ok)
        self.assertIn("circuit breaker", reason)

    def test_kill_switch(self):
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            kill_path = fh.name
        try:
            self.rm.limits.kill_switch_file = kill_path
            ok, reason = self.rm.check(Side.BUY, 1, 1.0, 0.0, now=1000.0)
            self.assertFalse(ok)
            self.assertIn("kill switch", reason)
        finally:
            os.unlink(kill_path)


if __name__ == "__main__":
    unittest.main()
