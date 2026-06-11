"""Historical price feed abstraction.

Indicators need a window of recent closes. Where those bars come from is
deliberately decoupled from execution: backtests read from CSV, and live runs
can use any provider you wire up. Keeping the feed separate from the broker
means the strategy math is identical in both.
"""
from __future__ import annotations

import abc
import csv
from typing import Dict, List


class PriceFeed(abc.ABC):
    @abc.abstractmethod
    def closes(self, symbol: str, lookback: int) -> List[float]:
        """Return the most recent ``lookback`` daily closes, oldest -> newest."""
        ...


class CsvPriceFeed(PriceFeed):
    """Reads closes from ``data/<symbol>.csv`` with a ``close`` column.

    Useful offline for backtests and for the dry-run loop without a live data
    provider. Columns are case-insensitive; rows are assumed chronological.
    """

    def __init__(self, directory: str = "data") -> None:
        self.directory = directory
        self._cache: Dict[str, List[float]] = {}

    def _load(self, symbol: str) -> List[float]:
        if symbol in self._cache:
            return self._cache[symbol]
        path = f"{self.directory}/{symbol}.csv"
        closes: List[float] = []
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            field = next((c for c in (reader.fieldnames or []) if c.lower() == "close"), None)
            if field is None:
                raise ValueError(f"{path} has no 'close' column")
            for row in reader:
                closes.append(float(row[field]))
        self._cache[symbol] = closes
        return closes

    def closes(self, symbol: str, lookback: int) -> List[float]:
        data = self._load(symbol)
        return data[-lookback:]
