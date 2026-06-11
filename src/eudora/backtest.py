"""Backtester — replay a strategy over historical closes and report results.

The point of this module is to answer "would this strategy have made or lost
money?" *before* a cent of real capital is involved. It reuses the exact same
strategy, sizing, risk checks, and PaperBroker as live trading, so what you
measure here is what the live engine would have done on the same data.

Walk-forward, no look-ahead: at bar ``t`` the strategy sees only closes up to
and including ``t`` and trades at that bar's close.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .broker.paper import PaperBroker
from .risk import RiskManager
from .strategy.base import Side, Strategy


@dataclass
class Trade:
    bar: int
    symbol: str
    side: str
    quantity: float
    price: float
    pnl: Optional[float] = None  # realized P&L, set on the closing SELL


@dataclass
class BacktestResult:
    starting_cash: float
    final_equity: float
    equity_curve: List[float]
    trades: List[Trade]
    benchmark_return: float  # equal-weight buy & hold over the same window

    @property
    def total_return(self) -> float:
        if self.starting_cash == 0:
            return 0.0
        return (self.final_equity - self.starting_cash) / self.starting_cash

    @property
    def max_drawdown(self) -> float:
        peak = float("-inf")
        mdd = 0.0
        for e in self.equity_curve:
            peak = max(peak, e)
            if peak > 0:
                mdd = max(mdd, (peak - e) / peak)
        return mdd

    @property
    def round_trips(self) -> List[Trade]:
        return [t for t in self.trades if t.pnl is not None]

    @property
    def win_rate(self) -> Optional[float]:
        closed = self.round_trips
        if not closed:
            return None
        wins = sum(1 for t in closed if t.pnl > 0)
        return wins / len(closed)

    def summary(self) -> str:
        wr = self.win_rate
        wr_str = f"{wr * 100:.1f}%" if wr is not None else "n/a (no closed trades)"
        realized = sum(t.pnl for t in self.round_trips)
        lines = [
            "Backtest results",
            "-" * 40,
            f"  Starting capital : ${self.starting_cash:,.2f}",
            f"  Final equity     : ${self.final_equity:,.2f}",
            f"  Total return     : {self.total_return * 100:+.2f}%",
            f"  Buy & hold (eq-wt): {self.benchmark_return * 100:+.2f}%",
            f"  Max drawdown     : {self.max_drawdown * 100:.2f}%",
            f"  Orders placed    : {len(self.trades)}",
            f"  Closed round-trips: {len(self.round_trips)}",
            f"  Win rate         : {wr_str}",
            f"  Realized P&L     : ${realized:+,.2f}",
        ]
        return "\n".join(lines)


class Backtester:
    def __init__(
        self,
        strategy: Strategy,
        closes: Dict[str, List[float]],
        starting_cash: float = 500.0,
        order_notional: float = 100.0,
        risk: Optional[RiskManager] = None,
    ) -> None:
        self.strategy = strategy
        self.closes = {s: c for s, c in closes.items() if c}
        self.starting_cash = starting_cash
        self.order_notional = order_notional
        self.risk = risk  # optional: apply the same risk caps as live

    def _size(self, side: Side, price: float, position_qty: float) -> float:
        if side is Side.SELL:
            return position_qty
        if price <= 0:
            return 0.0
        return float(math.floor(self.order_notional / price))

    def run(self) -> BacktestResult:
        broker = PaperBroker(starting_cash=self.starting_cash)
        symbols = list(self.closes)
        n = min(len(self.closes[s]) for s in symbols)
        entry_price: Dict[str, float] = {}
        trades: List[Trade] = []
        equity_curve: List[float] = []

        for t in range(n):
            # Map each bar to one simulated day so the risk manager's rolling
            # 24h / circuit-breaker windows behave as they would live, instead
            # of collapsing into one instant of wall-clock replay time.
            bar_time = t * 86400.0
            for sym in symbols:
                window = self.closes[sym][: t + 1]
                price = window[-1]
                broker.set_quote(sym, price)
                position_qty = broker.get_position_qty(sym)

                signal = self.strategy.evaluate(sym, window, position_qty)
                if signal is None:
                    continue

                qty = self._size(signal.side, price, position_qty)
                if qty <= 0:
                    continue

                if self.risk is not None:
                    ok, _ = self.risk.check(signal.side, qty, price, position_qty, now=bar_time)
                    if not ok:
                        continue

                # Compute realized P&L on the closing sell before the fill.
                pnl = None
                if signal.side is Side.SELL and sym in entry_price:
                    pnl = (price - entry_price[sym]) * qty

                result = broker.place_order(sym, signal.side, qty)
                if not result.accepted:
                    continue
                if self.risk is not None:
                    self.risk.record_fill(qty, price, now=bar_time)

                if signal.side is Side.BUY:
                    entry_price[sym] = price
                else:
                    entry_price.pop(sym, None)
                trades.append(Trade(t, sym, signal.side.value, qty, price, pnl))

            # Mark-to-market portfolio equity at this bar's closes.
            equity = broker.get_cash() + sum(
                p.quantity * self.closes[s][t]
                for s, p in broker.get_positions().items()
            )
            equity_curve.append(equity)

        benchmark = self._benchmark(symbols, n)
        return BacktestResult(
            starting_cash=self.starting_cash,
            final_equity=equity_curve[-1] if equity_curve else self.starting_cash,
            equity_curve=equity_curve,
            trades=trades,
            benchmark_return=benchmark,
        )

    def _benchmark(self, symbols: List[str], n: int) -> float:
        """Equal-weight buy & hold from the first to the last bar of the window."""
        rets = []
        for s in symbols:
            first, last = self.closes[s][0], self.closes[s][n - 1]
            if first > 0:
                rets.append((last - first) / first)
        return sum(rets) / len(rets) if rets else 0.0
