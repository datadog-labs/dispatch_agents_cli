"""HTTP client utilities with version headers for dispatch CLI."""

import os

from .version import get_cli_version

# Client identifier for API requests
DISPATCH_CLIENT_NAME = "cli"


def get_api_headers(api_key: str | None = None) -> dict[str, str]:
    """Get HTTP headers including authentication and version information.

    Args:
        api_key: Optional API key for authorization

    Returns:
        Dict of HTTP headers with version info and optionally authorization
    """
    headers = {
        "x-dispatch-client": DISPATCH_CLIENT_NAME,
        "x-dispatch-client-version": get_cli_version(),
        "x-dispatch-client-commit": os.getenv("GIT_COMMIT", "unknown")[:8],
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return headers
