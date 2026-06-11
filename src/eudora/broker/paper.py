"""In-process paper broker.

Fills market orders instantly at the last quote it was given. Used for dry runs
and for end-to-end tests of the engine without touching a real account. Prices
are fed in via ``set_quote`` (normally from the data feed) so the paper broker
stays deterministic.
"""
from __future__ import annotations

from typing import Dict

from ..strategy.base import Side
from .base import Broker, OrderResult, Position, Quote


class PaperBroker(Broker):
    def __init__(self, starting_cash: float = 10_000.0) -> None:
        self._cash = starting_cash
        self._positions: Dict[str, Position] = {}
        self._quotes: Dict[str, float] = {}
        self._order_seq = 0

    def set_quote(self, symbol: str, price: float) -> None:
        self._quotes[symbol] = price

    def get_cash(self) -> float:
        return self._cash

    def get_positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    def get_quote(self, symbol: str) -> Quote:
        if symbol not in self._quotes:
            raise KeyError(f"no quote set for {symbol}")
        return Quote(symbol=symbol, price=self._quotes[symbol])

    def place_order(self, symbol: str, side: Side, quantity: float) -> OrderResult:
        price = self._quotes[symbol]
        self._order_seq += 1
        order_id = f"paper-{self._order_seq}"

        if side is Side.BUY:
            cost = price * quantity
            if cost > self._cash:
                return OrderResult(False, None, None, {"error": "insufficient cash"})
            self._cash -= cost
            existing = self._positions.get(symbol)
            if existing:
                total_qty = existing.quantity + quantity
                avg = (
                    existing.avg_price * existing.quantity + price * quantity
                ) / total_qty
                self._positions[symbol] = Position(symbol, total_qty, avg)
            else:
                self._positions[symbol] = Position(symbol, quantity, price)
        else:  # SELL
            existing = self._positions.get(symbol)
            held = existing.quantity if existing else 0.0
            if quantity > held:
                return OrderResult(False, None, None, {"error": "insufficient shares"})
            self._cash += price * quantity
            remaining = held - quantity
            if remaining == 0:
                self._positions.pop(symbol, None)
            else:
                self._positions[symbol] = Position(symbol, remaining, existing.avg_price)

        return OrderResult(True, order_id, price)
