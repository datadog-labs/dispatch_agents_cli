## Bug Fixes

- Fixed agent builds to use the correct platform architecture (`TARGETARCH`), resolving issues with cross-platform image builds.

## Breaking Changes

- Removed built-in Dockerfile template, entrypoint script, and MCP config merge helper. Projects relying on these bundled templates will need to provide their own.

## Other Changes

- Standardized observability tags and canonical invocation events to improve monitoring consistency.
