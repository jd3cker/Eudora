"""Command-line entry point.

    python -m eudora.cli run        --config config.toml         # dry run (default)
    python -m eudora.cli run --live --config config.toml         # REAL orders
    python -m eudora.cli loop --interval 300 --config config.toml # repeat forever

Going live is intentionally awkward: it requires both the ``--live`` flag and
``--i-understand-the-risk`` so it can never happen by accident.
"""
from __future__ import annotations

import argparse
import sys
import time

from . import config as cfg_mod
from .broker.paper import PaperBroker
from .engine import Engine
from .feed.base import CsvPriceFeed
from .journal import Journal


def _build_engine(args, *, live: bool) -> Engine:
    cfg = cfg_mod.load_toml(args.config)
    strategy = cfg_mod.build_strategy(cfg)
    risk = cfg_mod.build_risk(cfg)
    engine_cfg = cfg_mod.build_engine_config(cfg)
    engine_cfg.dry_run = not live
    journal = Journal(cfg.get("journal", {}).get("path", "trades.jsonl"))
    feed = CsvPriceFeed(cfg.get("feed", {}).get("directory", "data"))

    if live:
        broker = cfg_mod.build_live_broker(cfg)
    else:
        broker = PaperBroker(cfg.get("paper", {}).get("starting_cash", 10_000.0))
        # Seed paper quotes from the latest close so dry runs can fill.
        for sym in engine_cfg.symbols:
            closes = feed.closes(sym, engine_cfg.lookback)
            if closes:
                broker.set_quote(sym, closes[-1])

    return Engine(strategy, broker, feed, risk, journal, engine_cfg)


def _confirm_live(args) -> bool:
    if not args.i_understand_the_risk:
        print(
            "Refusing to trade live without --i-understand-the-risk.\n"
            "Live trading sends REAL orders against your funded Robinhood "
            "Agentic Trading account. Start with a dry run first.",
            file=sys.stderr,
        )
        return False
    return True


def cmd_run(args) -> int:
    live = args.live
    if live and not _confirm_live(args):
        return 2
    engine = _build_engine(args, live=live)
    print(f"[eudora] running once in {engine.mode} mode over {engine.config.symbols}")
    engine.run_once()
    print(f"[eudora] done; see {engine.journal.path}")
    return 0


def cmd_loop(args) -> int:
    live = args.live
    if live and not _confirm_live(args):
        return 2
    engine = _build_engine(args, live=live)
    print(f"[eudora] loop every {args.interval}s in {engine.mode} mode; Ctrl-C to stop")
    try:
        while True:
            engine.run_once()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[eudora] stopped")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eudora", description="Rule-based Robinhood trading bot")
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config.toml")
    common.add_argument("--live", action="store_true", help="send REAL orders")
    common.add_argument("--i-understand-the-risk", action="store_true",
                        help="required acknowledgement to trade live")

    run = sub.add_parser("run", parents=[common], help="evaluate all symbols once")
    run.set_defaults(func=cmd_run)

    loop = sub.add_parser("loop", parents=[common], help="evaluate repeatedly")
    loop.add_argument("--interval", type=float, default=300.0, help="seconds between runs")
    loop.set_defaults(func=cmd_loop)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
