"""Live broker backed by Robinhood's Agentic Trading MCP server.

IMPORTANT — read before going live
-----------------------------------
This adapter speaks MCP directly (no LLM in the execution path) so a rule-based
strategy stays deterministic. It connects to:

    https://agent.robinhood.com/mcp/trading

The exact MCP *tool names and argument schemas* are NOT hard-coded here because
they must be confirmed against the live server after you authenticate. Run:

    python scripts/discover_mcp_tools.py

to list the real tools, then fill in ``ToolMap`` (or the ``[broker.tools]``
section of your config) with the actual names. Anything left as a guess is
flagged so it can never silently send a wrong order.

Auth: authenticate the server once locally with the Claude CLI
(`claude mcp add ...` then `/mcp` -> robinhood-trading -> authenticate). Supply
the resulting bearer token to this process via the ROBINHOOD_MCP_TOKEN
environment variable. The OAuth browser flow cannot run in a headless/remote
container, which is why this step happens on your own machine.

This module imports the `mcp` package lazily so the rest of Eudora (indicators,
strategy, risk, paper trading, tests) works with zero third-party dependencies.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..strategy.base import Side
from .base import Broker, OrderResult, Position, Quote

MCP_URL = "https://agent.robinhood.com/mcp/trading"


@dataclass
class ToolMap:
    """Maps Eudora operations to live MCP tool names.

    Defaults are GUESSES. Confirm every one with scripts/discover_mcp_tools.py
    before trading live; ``RobinhoodMCPBroker`` refuses to run while any name is
    still marked unconfirmed.
    """

    get_account: str = "TODO_get_account"
    get_positions: str = "TODO_get_positions"
    get_quote: str = "TODO_get_quote"
    place_order: str = "TODO_place_order"
    confirmed: bool = False  # set True once names are verified against the server

    def assert_ready(self) -> None:
        if not self.confirmed or any(
            v.startswith("TODO_") for v in (
                self.get_account, self.get_positions, self.get_quote, self.place_order
            )
        ):
            raise RuntimeError(
                "Robinhood MCP tool names are not confirmed. Run "
                "scripts/discover_mcp_tools.py, set the real names in your config "
                "[broker.tools], and set confirmed=true before trading live."
            )


class RobinhoodMCPBroker(Broker):
    def __init__(self, tools: Optional[ToolMap] = None, token: Optional[str] = None) -> None:
        self.tools = tools or ToolMap()
        self.token = token or os.environ.get("ROBINHOOD_MCP_TOKEN")
        if not self.token:
            raise RuntimeError(
                "No Robinhood MCP token. Authenticate locally and set "
                "ROBINHOOD_MCP_TOKEN (see module docstring)."
            )
        self.tools.assert_ready()
        self._client_cm = None
        self._session = None

    # -- MCP plumbing -------------------------------------------------------
    def _ensure_session(self):
        """Open a streamable-HTTP MCP session lazily (sync wrapper).

        The `mcp` SDK is async; this keeps a single event loop + session alive
        for the broker's lifetime. Import is local so the dependency is only
        needed when actually trading live.
        """
        if self._session is not None:
            return self._session
        import asyncio

        from mcp import ClientSession  # type: ignore
        from mcp.client.streamable_http import streamablehttp_client  # type: ignore

        self._loop = asyncio.new_event_loop()

        async def _connect():
            headers = {"Authorization": f"Bearer {self.token}"}
            self._client_cm = streamablehttp_client(MCP_URL, headers=headers)
            read, write, _ = await self._client_cm.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            return session

        self._session = self._loop.run_until_complete(_connect())
        return self._session

    def _call(self, tool: str, arguments: Dict[str, Any]) -> Any:
        session = self._ensure_session()
        result = self._loop.run_until_complete(session.call_tool(tool, arguments))
        if getattr(result, "isError", False):
            raise RuntimeError(f"MCP tool {tool} returned error: {result}")
        return _unwrap(result)

    def close(self) -> None:
        if self._session is None:
            return
        async def _close():
            await self._session.__aexit__(None, None, None)
            if self._client_cm is not None:
                await self._client_cm.__aexit__(None, None, None)
        self._loop.run_until_complete(_close())
        self._loop.close()
        self._session = None

    # -- Broker interface ---------------------------------------------------
    # The response-parsing below depends on the live schema; verify field names
    # against real responses (the discovery script prints sample shapes).
    def get_cash(self) -> float:
        data = self._call(self.tools.get_account, {})
        return float(data.get("buying_power", data.get("cash", 0.0)))

    def get_positions(self) -> Dict[str, Position]:
        data = self._call(self.tools.get_positions, {})
        rows = data.get("positions", data) if isinstance(data, dict) else data
        out: Dict[str, Position] = {}
        for r in rows or []:
            sym = r["symbol"]
            qty = float(r.get("quantity", 0))
            if qty == 0:
                continue
            out[sym] = Position(sym, qty, float(r.get("average_price", 0.0)))
        return out

    def get_quote(self, symbol: str) -> Quote:
        data = self._call(self.tools.get_quote, {"symbol": symbol})
        price = data.get("last_price", data.get("price"))
        return Quote(symbol=symbol, price=float(price))

    def place_order(self, symbol: str, side: Side, quantity: float) -> OrderResult:
        data = self._call(
            self.tools.place_order,
            {"symbol": symbol, "side": side.value, "quantity": quantity, "type": "market"},
        )
        order_id = data.get("id") or data.get("order_id")
        filled = data.get("filled_price") or data.get("average_price")
        return OrderResult(
            accepted=bool(order_id),
            order_id=str(order_id) if order_id else None,
            filled_price=float(filled) if filled else None,
            raw=data,
        )


def _unwrap(result: Any) -> Any:
    """Best-effort extraction of structured content from an MCP CallToolResult."""
    structured = getattr(result, "structuredContent", None)
    if structured:
        return structured
    content = getattr(result, "content", None)
    if content:
        import json
        for block in content:
            text = getattr(block, "text", None)
            if text:
                try:
                    return json.loads(text)
                except (ValueError, TypeError):
                    return {"text": text}
    return {}
