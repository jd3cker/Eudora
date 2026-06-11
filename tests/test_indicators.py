import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from eudora.indicators import (  # noqa: E402
    crossed_above,
    crossed_below,
    ema,
    rsi,
    sma,
)


class TestSma(unittest.TestCase):
    def test_warmup_padding(self):
        result = sma([1, 2, 3, 4], 3)
        self.assertEqual(result[:2], [None, None])

    def test_values(self):
        result = sma([1, 2, 3, 4, 5], 3)
        self.assertAlmostEqual(result[2], 2.0)
        self.assertAlmostEqual(result[3], 3.0)
        self.assertAlmostEqual(result[4], 4.0)

    def test_too_short(self):
        self.assertEqual(sma([1, 2], 5), [None, None])

    def test_rejects_bad_period(self):
        with self.assertRaises(ValueError):
            sma([1, 2, 3], 0)


class TestEma(unittest.TestCase):
    def test_seed_is_sma(self):
        result = ema([1, 2, 3, 4, 5], 3)
        self.assertAlmostEqual(result[2], 2.0)  # seed = SMA of first 3

    def test_responds_to_trend(self):
        result = ema([10, 11, 12, 13, 14, 15], 3)
        # In a rising series the EMA keeps climbing.
        self.assertTrue(result[5] > result[4] > result[3])


class TestRsi(unittest.TestCase):
    def test_all_gains_is_100(self):
        result = rsi([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16], 14)
        self.assertAlmostEqual(result[-1], 100.0)

    def test_bounds(self):
        prices = [
            44, 44.25, 44.5, 43.75, 44.5, 45, 47, 47.5,
            46, 46.5, 46, 47, 47.5, 48, 47.5, 47, 46.5, 46,
        ]
        result = rsi(prices, 14)
        for v in result:
            if v is not None:
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 100.0)


class TestCrosses(unittest.TestCase):
    def test_cross_above(self):
        fast = [1.0, 3.0]
        slow = [2.0, 2.0]
        self.assertTrue(crossed_above(fast, slow, 1))
        self.assertFalse(crossed_below(fast, slow, 1))

    def test_cross_below(self):
        fast = [3.0, 1.0]
        slow = [2.0, 2.0]
        self.assertTrue(crossed_below(fast, slow, 1))
        self.assertFalse(crossed_above(fast, slow, 1))

    def test_none_safe(self):
        self.assertFalse(crossed_above([None, 1.0], [None, 0.5], 1))


if __name__ == "__main__":
    unittest.main()
