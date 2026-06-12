## Features
- The `dispatch_agents.logging` module is now part of the public API, making logging configuration officially supported for use in agent code.

## Bug Fixes
- Dispatch-managed MCP servers are now correctly skipped during local development, preventing conflicts between local and cloud-managed server configurations.