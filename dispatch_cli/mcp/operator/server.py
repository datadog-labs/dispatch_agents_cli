"""Operator MCP server for platform management."""

from ..client import DispatchAPIClient
from ..config import MCPConfig
from .tools import create_operator_mcp


def run_operator_server(config: MCPConfig):
    """Run operator MCP server (blocking)."""
    client = DispatchAPIClient(config)
    mcp = create_operator_mcp(client, config)
    mcp.run()
