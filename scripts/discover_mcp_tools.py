"""Introspect the Robinhood Agentic Trading MCP server.

Run this ON YOUR LOCAL MACHINE after you have authenticated the server with the
Claude CLI (`claude mcp add ...` then `/mcp` -> robinhood-trading -> auth) and
exported the bearer token:

    export ROBINHOOD_MCP_TOKEN=...      # token from the authenticated session
    python scripts/discover_mcp_tools.py

It prints every tool's name, description, and input schema. Use the printed
names to fill in the [broker.tools] section of your config and set
confirmed = true. This removes the guesswork from robinhood_mcp.ToolMap.

Requires:  pip install "mcp[cli]"
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

MCP_URL = "https://agent.robinhood.com/mcp/trading"


async def main() -> int:
    token = os.environ.get("ROBINHOOD_MCP_TOKEN")
    if not token:
        print("Set ROBINHOOD_MCP_TOKEN first (see docstring).", file=sys.stderr)
        return 1

    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError:
        print('Install the MCP SDK:  pip install "mcp[cli]"', file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"Found {len(tools.tools)} tools on {MCP_URL}:\n")
            for t in tools.tools:
                print(f"== {t.name} ==")
                if t.description:
                    print(f"  {t.description.strip()}")
                schema = getattr(t, "inputSchema", None)
                if schema:
                    props = schema.get("properties", {})
                    if props:
                        print("  args:")
                        for arg, spec in props.items():
                            print(f"    - {arg}: {json.dumps(spec)}")
                print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
