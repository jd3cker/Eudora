"""The trading loop: data -> strategy -> risk -> (maybe) execute.

The engine is broker-agnostic and mode-agnostic. ``dry_run=True`` (the default)
runs every step *except* sending the order, journaling exactly what it would
have done. This is the recommended way to shake out a strategy before risking
real capital.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

from .broker.base import Broker
from .feed.base import PriceFeed
from .journal import Journal
from .risk import RiskManager
from .strategy.base import Side, Strategy


@dataclass
class EngineConfig:
    symbols: List[str]
    lookback: int = 200
    #: Target dollars to deploy per BUY (capped again by the risk manager).
    order_notional: float = 100.0
    dry_run: bool = True


class Engine:
    def __init__(
        self,
        strategy: Strategy,
        broker: Broker,
        feed: PriceFeed,
        risk: RiskManager,
        journal: Journal,
        config: EngineConfig,
    ) -> None:
        self.strategy = strategy
        self.broker = broker
        self.feed = feed
        self.risk = risk
        self.journal = journal
        self.config = config

    @property
    def mode(self) -> str:
        return "dry_run" if self.config.dry_run else "live"

    def _size_order(self, side: Side, price: float, position_qty: float) -> float:
        if side is Side.SELL:
            return position_qty  # exit the full position
        if price <= 0:
            return 0.0
        # Whole shares only; floor to stay under the notional target.
        return float(math.floor(self.config.order_notional / price))

    def run_once(self) -> None:
        """Evaluate every symbol exactly once. Call this on your schedule."""
        for symbol in self.config.symbols:
            try:
                self._process(symbol)
            except Exception as exc:  # never let one symbol kill the loop
                self.journal.record(
                    self.mode, symbol, "-", 0.0, 0.0, "error", f"{type(exc).__name__}: {exc}"
                )

    def _process(self, symbol: str) -> None:
        closes = self.feed.closes(symbol, self.config.lookback)
        position_qty = self.broker.get_position_qty(symbol)

        signal = self.strategy.evaluate(symbol, closes, position_qty)
        if signal is None:
            return

        price = self.broker.get_quote(symbol).price
        quantity = self._size_order(signal.side, price, position_qty)
        if quantity <= 0:
            self.journal.record(
                self.mode, symbol, signal.side.value, 0.0, price, "skipped",
                f"{signal.reason}; sized to 0 shares at ${price:.2f}",
            )
            return

        allowed, reason = self.risk.check(signal.side, quantity, price, position_qty)
        if not allowed:
            self.journal.record(
                self.mode, symbol, signal.side.value, quantity, price, "rejected",
                f"{signal.reason}; risk: {reason}",
            )
            return

        if self.config.dry_run:
            self.journal.record(
                self.mode, symbol, signal.side.value, quantity, price, "skipped",
                f"{signal.reason}; DRY RUN (no order sent)",
            )
            return

        result = self.broker.place_order(symbol, signal.side, quantity)
        if result.accepted:
            fill = result.filled_price if result.filled_price is not None else price
            self.risk.record_fill(quantity, fill)
            self.journal.record(
                self.mode, symbol, signal.side.value, quantity, fill, "placed",
                signal.reason, order_id=result.order_id,
            )
        else:
            self.journal.record(
                self.mode, symbol, signal.side.value, quantity, price, "error",
                f"{signal.reason}; broker rejected: {result.raw}",
            )
