"""Risk controls — the last line of defence before an order is sent.

Even though Robinhood's Agentic Trading account has its own daily cap, we keep
an independent software-side set of limits here. Defence in depth: a bug in the
strategy or a runaway loop should hit *our* circuit breaker long before it ever
reaches the broker's.
"""
from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Tuple

from .strategy.base import Side


@dataclass
class RiskLimits:
    #: Max notional ($) for any single order.
    max_order_notional: float = 200.0
    #: Max total notional ($) of orders placed in a rolling 24h window.
    max_daily_notional: float = 500.0
    #: Max number of orders per rolling 24h window.
    max_daily_orders: int = 20
    #: Circuit breaker: max orders allowed within max_orders_window_sec.
    max_orders_in_window: int = 5
    max_orders_window_sec: float = 60.0
    #: Long-only by default — never open shorts.
    allow_short: bool = False
    #: If this file exists on disk, ALL orders are blocked (manual kill switch).
    kill_switch_file: str = "KILL_SWITCH"


@dataclass
class RiskManager:
    limits: RiskLimits = field(default_factory=RiskLimits)
    _order_times: Deque[float] = field(default_factory=deque, init=False)
    _daily_notional: float = field(default=0.0, init=False)
    _daily_orders: int = field(default=0, init=False)
    # Seeded lazily from the first timestamp observed (which may be simulated
    # bar-time in a backtest, not wall-clock), so the 24h window is anchored to
    # the data rather than to object-construction time.
    _day_started: Optional[float] = field(default=None, init=False)

    def _roll_day(self, now: float) -> None:
        if self._day_started is None:
            self._day_started = now
            return
        if now - self._day_started >= 24 * 3600:
            self._daily_notional = 0.0
            self._daily_orders = 0
            self._day_started = now

    def check(
        self,
        side: Side,
        quantity: float,
        price: float,
        position_qty: float,
        now: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """Return (allowed, reason). ``reason`` explains a rejection."""
        now = time.time() if now is None else now
        self._roll_day(now)
        notional = quantity * price

        if os.path.exists(self.limits.kill_switch_file):
            return False, f"kill switch active ({self.limits.kill_switch_file} present)"

        if quantity <= 0:
            return False, "non-positive quantity"

        if not self.limits.allow_short:
            if side is Side.SELL and quantity > position_qty:
                return False, (
                    f"would short: sell {quantity} but only hold {position_qty}"
                )

        if notional > self.limits.max_order_notional:
            return False, (
                f"order notional ${notional:.2f} exceeds per-order cap "
                f"${self.limits.max_order_notional:.2f}"
            )

        if self._daily_notional + notional > self.limits.max_daily_notional:
            return False, (
                f"would exceed daily notional cap "
                f"(${self._daily_notional:.2f} + ${notional:.2f} > "
                f"${self.limits.max_daily_notional:.2f})"
            )

        if self._daily_orders + 1 > self.limits.max_daily_orders:
            return False, (
                f"would exceed daily order count cap "
                f"({self._daily_orders + 1} > {self.limits.max_daily_orders})"
            )

        # Rolling-window circuit breaker.
        window_start = now - self.limits.max_orders_window_sec
        while self._order_times and self._order_times[0] < window_start:
            self._order_times.popleft()
        if len(self._order_times) + 1 > self.limits.max_orders_in_window:
            return False, (
                f"circuit breaker: more than {self.limits.max_orders_in_window} "
                f"orders within {self.limits.max_orders_window_sec:.0f}s"
            )

        return True, "ok"

    def record_fill(self, quantity: float, price: float, now: Optional[float] = None) -> None:
        """Record an order that was actually placed, for the rolling counters."""
        now = time.time() if now is None else now
        self._roll_day(now)
        self._order_times.append(now)
        self._daily_notional += quantity * price
        self._daily_orders += 1
