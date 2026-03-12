"""Merge MCP configuration files at container startup.

Combines a user-provided .mcp.json.base (baked into the image at build time)
with the deploy-time MCP_CONFIG_JSON environment variable (containing gateway
URLs and authentication). Deploy-time servers override same-named user servers.

Output is written to /tmp/.mcp.json, which is symlinked from /app/.mcp.json
so both the Dispatch SDK and Claude Code CLI can find it.
"""

import json
import os


def merge_mcp_config() -> None:
    base: dict = {}
    base_path = "/app/.mcp.json.base"
    if os.path.exists(base_path):
        with open(base_path) as f:
            base = json.load(f)

    inject = json.loads(os.environ.get("MCP_CONFIG_JSON", "{}"))
    servers = {**base.get("mcpServers", {}), **inject.get("mcpServers", {})}

    if servers:
        base["mcpServers"] = servers
        with open("/tmp/.mcp.json", "w") as f:
            json.dump(base, f)
        print(f"MCP config written to /tmp/.mcp.json ({len(servers)} server(s))")
    else:
        print("No MCP servers configured")


if __name__ == "__main__":
    merge_mcp_config()
