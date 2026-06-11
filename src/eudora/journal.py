"""Append-only trade journal (JSON Lines).

Every decision — placed, skipped, or rejected — is recorded with its reason so
the bot's behaviour can be reconstructed and audited after the fact. This is
non-negotiable for anything touching real money.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class JournalEntry:
    ts: float
    mode: str  # "dry_run" | "live"
    symbol: str
    side: str
    quantity: float
    price: float
    notional: float
    status: str  # "placed" | "skipped" | "rejected" | "error"
    reason: str
    order_id: Optional[str] = None


class Journal:
    def __init__(self, path: str = "trades.jsonl") -> None:
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)

    def write(self, entry: JournalEntry) -> None:
        line = json.dumps(asdict(entry), separators=(",", ":"))
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def record(
        self,
        mode: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        status: str,
        reason: str,
        order_id: Optional[str] = None,
    ) -> JournalEntry:
        entry = JournalEntry(
            ts=time.time(),
            mode=mode,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            notional=quantity * price,
            status=status,
            reason=reason,
            order_id=order_id,
        )
        self.write(entry)
        return entry
