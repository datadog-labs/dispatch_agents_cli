"""Operator MCP server for platform management."""

from mcp.server.fastmcp import FastMCP

from ..client import OperatorBackendClient, default_operator_backend_client
from ..config import MCPConfig
from .tools import create_operator_mcp


def create_operator_server(
    config: MCPConfig,
    client: OperatorBackendClient | None = None,
) -> FastMCP:
    """Create and configure the operator MCP server."""
    resolved_client = client or default_operator_backend_client(config)
    return create_operator_mcp(resolved_client, config)


def run_operator_server(
    config: MCPConfig,
    client: OperatorBackendClient | None = None,
) -> None:
    """Run operator MCP server (blocking)."""
    mcp = create_operator_server(config, client=client)
    mcp.run()
