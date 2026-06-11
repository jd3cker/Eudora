"""Strategy interface and the signal type strategies emit."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Signal:
    """A trading intent produced by a strategy.

    The strategy decides *direction and conviction*, not size — sizing and the
    final go/no-go are the risk manager's job. ``reason`` is recorded in the
    trade journal so every order is auditable after the fact.
    """

    symbol: str
    side: Side
    reason: str
    # Optional 0..1 strength hint the sizer may use; defaults to full size.
    strength: float = 1.0


class Strategy(abc.ABC):
    """Base class for rule-based strategies.

    Implementations are pure functions of (price history, current position):
    given the same inputs they always return the same signal. No I/O, no
    randomness — that is what keeps a rule-based bot testable and auditable.
    """

    name: str = "strategy"

    @abc.abstractmethod
    def evaluate(
        self,
        symbol: str,
        closes: List[float],
        position_qty: float,
    ) -> Optional[Signal]:
        """Return a Signal to act on, or None to do nothing this bar.

        ``closes`` is oldest -> newest. ``position_qty`` is the currently held
        quantity (0 if flat). Strategies should only emit a BUY when flat and a
        SELL when long, but the risk manager enforces that regardless.
        """
        raise NotImplementedError
