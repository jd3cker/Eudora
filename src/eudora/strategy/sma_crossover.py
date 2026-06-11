"""Moving-average crossover strategy with an optional RSI filter.

Rules (long-only):
  * BUY  when the fast SMA crosses above the slow SMA, and (if enabled) RSI is
    not already overbought.
  * SELL when the fast SMA crosses below the slow SMA.

Long-only and one-position-per-symbol keeps the behaviour easy to reason about
for a first live deployment.
"""
from __future__ import annotations

from typing import List, Optional

from ..indicators import crossed_above, crossed_below, rsi, sma
from .base import Side, Signal, Strategy


class SmaCrossover(Strategy):
    name = "sma_crossover"

    def __init__(
        self,
        fast: int = 20,
        slow: int = 50,
        rsi_period: int = 14,
        rsi_overbought: Optional[float] = 70.0,
    ) -> None:
        if fast >= slow:
            raise ValueError("fast period must be shorter than slow period")
        self.fast = fast
        self.slow = slow
        self.rsi_period = rsi_period
        # Accept False (e.g. from TOML `rsi_overbought = false`) or None to mean
        # "disabled". Without this, `r >= False` would compare against 0 and
        # suppress every buy.
        self.rsi_overbought = (
            None if rsi_overbought in (None, False) else float(rsi_overbought)
        )

    def evaluate(
        self,
        symbol: str,
        closes: List[float],
        position_qty: float,
    ) -> Optional[Signal]:
        if len(closes) <= self.slow:
            return None  # not enough history to be meaningful

        fast = sma(closes, self.fast)
        slow = sma(closes, self.slow)
        i = len(closes) - 1  # evaluate on the latest closed bar

        flat = position_qty == 0
        long = position_qty > 0

        if flat and crossed_above(fast, slow, i):
            if self.rsi_overbought is not None:
                r = rsi(closes, self.rsi_period)[i]
                if r is not None and r >= self.rsi_overbought:
                    return None  # skip chasing an overbought breakout
            return Signal(
                symbol=symbol,
                side=Side.BUY,
                reason=f"SMA{self.fast} crossed above SMA{self.slow}",
            )

        if long and crossed_below(fast, slow, i):
            return Signal(
                symbol=symbol,
                side=Side.SELL,
                reason=f"SMA{self.fast} crossed below SMA{self.slow}",
            )

        return None
