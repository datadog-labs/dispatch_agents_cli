#!/bin/bash
# Entrypoint script for Dispatch agent containers
# Writes MCP config from environment variable to file before starting the agent

set -e

# Debug: log whether MCP_CONFIG_JSON is set
if [ -n "$MCP_CONFIG_JSON" ]; then
    echo "MCP_CONFIG_JSON is set (length: ${#MCP_CONFIG_JSON})"
    echo "$MCP_CONFIG_JSON" > /app/.mcp.json
    echo "MCP config written to /app/.mcp.json"
else
    echo "MCP_CONFIG_JSON is not set - no MCP config will be available"
fi

# If arguments are provided, run them instead of the default command
# This allows `docker run <image> cat /app/file` to work for schema extraction
if [ $# -gt 0 ]; then
    exec "$@"
fi

# Execute the agent listener (default command)
exec .venv/bin/python .dispatch/__dispatch_listener__.py
