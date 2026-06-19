"""MCP server for normsync.

Start:  python -m normsync.mcp_server
Or:     normsync-mcp

Add to Claude Desktop (~/.config/claude/claude_desktop_config.json):
    {
        "mcpServers": {
            "normsync": {
                "command": "normsync-mcp"
            }
        }
    }
"""

from __future__ import annotations

import sys
import time
from typing import Any

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, WorldNorm
from normsync.store import NormStore

try:
    import mcp.server.stdio as _mcp_stdio
    import mcp.types as _mcp_types
    from mcp.server import Server as _Server

    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False

_store = NormStore()
_monitor = NormMonitor()


def _require_mcp() -> None:
    """Call sys.exit(1) if the mcp package is not installed."""
    if not _HAS_MCP:
        print(
            "MCP server requires: pip install 'normsync[mcp]'",
            file=sys.stderr,
        )
        sys.exit(1)


def run_server() -> None:
    """Start the MCP server on stdio."""
    _require_mcp()

    server = _Server("normsync")

    @server.list_tools()
    async def list_tools() -> list[_mcp_types.Tool]:
        return [
            _mcp_types.Tool(
                name="add_norm",
                description="Add a normative rule to the world constitution",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "condition": {"type": "string"},
                        "prohibited": {"type": "string"},
                    },
                    "required": ["name", "description", "condition", "prohibited"],
                },
            ),
            _mcp_types.Tool(
                name="check_action",
                description="Check an agent action against active norms",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "action": {"type": "string"},
                        "location": {"type": "string"},
                    },
                    "required": ["agent_id", "action"],
                },
            ),
            _mcp_types.Tool(
                name="list_violations",
                description="List all recorded norm violations",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[_mcp_types.TextContent]:
        if name == "add_norm":
            norm = WorldNorm(
                name=arguments["name"],
                description=arguments["description"],
                condition=arguments["condition"],
                prohibited=arguments["prohibited"],
            )
            _store.save_norm(norm)
            _monitor.add_norm(norm)
            return [
                _mcp_types.TextContent(
                    type="text",
                    text=f"Added norm '{norm.name}' (id={norm.id})",
                )
            ]
        elif name == "check_action":
            act = AgentAction(
                agent_id=arguments["agent_id"],
                action=arguments["action"],
                location=arguments.get("location", ""),
                timestamp=time.time(),
            )
            violations = _monitor.check(act)
            for v in violations:
                _store.save_violation(v)
            if violations:
                lines = [f"Found {len(violations)} violation(s):"]
                for v in violations:
                    lines.append(f"  - {v.description}")
                return [_mcp_types.TextContent(type="text", text="\n".join(lines))]
            return [_mcp_types.TextContent(type="text", text="No violations detected.")]
        elif name == "list_violations":
            violations = _store.get_violations()
            if not violations:
                return [_mcp_types.TextContent(type="text", text="No violations recorded.")]
            lines = [f"Total violations: {len(violations)}"]
            for v in violations:
                lines.append(f"  - [{v.agent_id}] {v.norm_name}: {v.description[:60]}")
            return [_mcp_types.TextContent(type="text", text="\n".join(lines))]
        raise ValueError(f"Unknown tool: {name}")

    import asyncio

    async def _main() -> None:
        async with _mcp_stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_main())


if __name__ == "__main__":
    run_server()
