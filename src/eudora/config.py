"""Load and assemble bot components from a TOML config file.

Uses the standard library ``tomllib`` (Python 3.11+), so configuration adds no
dependency. See ``config.example.toml`` for every option.
"""
from __future__ import annotations

import tomllib
from typing import Any, Dict

from .broker.robinhood_mcp import RobinhoodMCPBroker, ToolMap
from .engine import EngineConfig
from .risk import RiskLimits, RiskManager
from . import strategy as strategy_mod


def load_toml(path: str) -> Dict[str, Any]:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def build_strategy(cfg: Dict[str, Any]) -> strategy_mod.Strategy:
    section = cfg.get("strategy", {})
    name = section.get("name", "sma_crossover")
    params = {k: v for k, v in section.items() if k != "name"}
    return strategy_mod.build(name, **params)


def build_risk(cfg: Dict[str, Any]) -> RiskManager:
    section = cfg.get("risk", {})
    limits = RiskLimits(
        max_order_notional=section.get("max_order_notional", 200.0),
        max_daily_notional=section.get("max_daily_notional", 500.0),
        max_daily_orders=section.get("max_daily_orders", 20),
        max_orders_in_window=section.get("max_orders_in_window", 5),
        max_orders_window_sec=section.get("max_orders_window_sec", 60.0),
        allow_short=section.get("allow_short", False),
        kill_switch_file=section.get("kill_switch_file", "KILL_SWITCH"),
    )
    return RiskManager(limits=limits)


def build_engine_config(cfg: Dict[str, Any]) -> EngineConfig:
    section = cfg.get("engine", {})
    return EngineConfig(
        symbols=section.get("symbols", []),
        lookback=section.get("lookback", 200),
        order_notional=section.get("order_notional", 100.0),
        dry_run=section.get("dry_run", True),
    )


def build_live_broker(cfg: Dict[str, Any]) -> RobinhoodMCPBroker:
    tcfg = cfg.get("broker", {}).get("tools", {})
    tools = ToolMap(
        get_account=tcfg.get("get_account", "TODO_get_account"),
        get_positions=tcfg.get("get_positions", "TODO_get_positions"),
        get_quote=tcfg.get("get_quote", "TODO_get_quote"),
        place_order=tcfg.get("place_order", "TODO_place_order"),
        confirmed=tcfg.get("confirmed", False),
    )
    return RobinhoodMCPBroker(tools=tools)
