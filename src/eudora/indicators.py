"""Pure-Python technical indicators (no numpy/pandas dependency).

Each function takes a list of floats (oldest -> newest) and returns a list of
the same length where the warm-up period is padded with ``None``. Keeping the
output aligned with the input makes the indicators trivial to unit test and to
zip together in strategies.
"""
from __future__ import annotations

from typing import List, Optional

Series = List[Optional[float]]


def sma(values: List[float], period: int) -> Series:
    """Simple moving average."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    window_sum = sum(values[:period])
    out[period - 1] = window_sum / period
    for i in range(period, len(values)):
        window_sum += values[i] - values[i - period]
        out[i] = window_sum / period
    return out


def ema(values: List[float], period: int) -> Series:
    """Exponential moving average, seeded with an SMA of the first window."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    prev = sum(values[:period]) / period  # seed
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def rsi(values: List[float], period: int = 14) -> Series:
    """Relative Strength Index using Wilder's smoothing."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    if len(values) <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from(avg_gain, avg_loss)

    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def crossed_above(fast: Series, slow: Series, index: int) -> bool:
    """True if ``fast`` crossed above ``slow`` on the bar at ``index``."""
    if index < 1:
        return False
    f0, f1 = fast[index - 1], fast[index]
    s0, s1 = slow[index - 1], slow[index]
    if None in (f0, f1, s0, s1):
        return False
    return f0 <= s0 and f1 > s1


def crossed_below(fast: Series, slow: Series, index: int) -> bool:
    """True if ``fast`` crossed below ``slow`` on the bar at ``index``."""
    if index < 1:
        return False
    f0, f1 = fast[index - 1], fast[index]
    s0, s1 = slow[index - 1], slow[index]
    if None in (f0, f1, s0, s1):
        return False
    return f0 >= s0 and f1 < s1
