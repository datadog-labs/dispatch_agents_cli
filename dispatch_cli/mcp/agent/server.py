"""Agent MCP server for agent-specific functions."""

import anyio

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from ..client import DispatchAPIClient
from ..config import MCPConfig
from .tools import register_agent_tools


def create_agent_server(config: MCPConfig) -> Server:
    """Create and configure agent MCP server."""
    server = Server("dispatch-agent")

    client = DispatchAPIClient(config)

    # Register agent-specific function tools
    register_agent_tools(server, client, config)

    return server


def run_agent_server(config: MCPConfig):
    """Run agent MCP server (blocking)."""
    server = create_agent_server(config)

    async def arun():
        async with stdio_server() as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )

    anyio.run(arun)
