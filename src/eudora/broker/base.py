"""Broker abstraction.

The engine talks to this interface only, so the same strategy/risk code runs
identically against the in-process PaperBroker and the live Robinhood MCP
broker. Swapping one for the other is the *only* difference between a dry run
and live trading.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Dict, Optional

from ..strategy.base import Side


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    avg_price: float


@dataclass(frozen=True)
class OrderResult:
    accepted: bool
    order_id: Optional[str]
    filled_price: Optional[float]
    raw: Optional[dict] = None


class Broker(abc.ABC):
    @abc.abstractmethod
    def get_cash(self) -> float:
        ...

    @abc.abstractmethod
    def get_positions(self) -> Dict[str, Position]:
        ...

    @abc.abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        ...

    @abc.abstractmethod
    def place_order(self, symbol: str, side: Side, quantity: float) -> OrderResult:
        ...

    def get_position_qty(self, symbol: str) -> float:
        pos = self.get_positions().get(symbol)
        return pos.quantity if pos else 0.0
