#!/bin/bash
# Entrypoint script for Dispatch agent containers

set -e

# Merge user-provided and deploy-time MCP config → /tmp/.mcp.json
python3 /app/merge_mcp_config.py

# If arguments are provided, run them instead of the default command
# This allows `docker run <image> cat /app/file` to work for schema extraction
if [ $# -gt 0 ]; then
    exec "$@"
fi

# Execute the agent listener (default command)
exec .venv/bin/python .dispatch/__dispatch_listener__.py
