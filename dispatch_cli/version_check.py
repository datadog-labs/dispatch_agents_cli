"""CLI version checking and upgrade notifications.

Checks for CLI updates once per day (cached) and SDK version on every deploy.
Also provides SDK version suggestion for agent projects based on CLI's bundled SDK.
"""

import json
import sys
import time
from datetime import datetime, timedelta
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version
from pathlib import Path

import requests
import typer
from packaging.version import Version
from platformdirs import user_cache_dir

from dispatch_cli.logger import get_logger

# Cache configuration
CACHE_DIR = Path(user_cache_dir("dispatch", "DataDog"))
VERSION_CHECK_CACHE = CACHE_DIR / "version_check.json"
VERSION_CHECK_INTERVAL = timedelta(hours=3)

# Hard minimum-version gate: re-validate at most once per this many seconds so
# a long-running process (e.g. an MCP server in an editor/Claude session) still
# notices a backend minimum bump mid-session, without fetching on every call.
_MIN_VERSION_CHECK_TTL = 60.0
_last_min_version_ok: float | None = None  # monotonic time of last passing check


def _cli_below_minimum(backend_url: str) -> tuple[bool, str, str]:
    """Return (is_below_minimum, current_version, minimum_version).

    is_below_minimum is True ONLY when we positively determined the running CLI
    is older than the backend's minimum. Every uncertain case (can't fetch the
    requirement, missing field, unparseable version) returns False so the gate
    fails open — a backend blip or offline use never bricks the CLI.
    """
    requirements = get_sdk_version_requirements(backend_url)
    if not requirements:
        return (False, "", "")
    minimum = requirements.get("cli_minimum")
    if not minimum:
        return (False, "", "")
    try:
        current = _get_version("dispatch-cli")
    except Exception:
        return (False, "", "")
    try:
        return (Version(current) < Version(minimum), current, minimum)
    except Exception:
        return (False, "", "")


def enforce_minimum_cli_version(backend_url: str) -> None:
    """Hard-stop when the running CLI is below the backend's minimum version.

    Called from the backend-request chokepoints (``get_auth_headers`` and the
    MCP client), so any backend operation refuses to run on a CLI the backend
    no longer supports — instead of letting it through to fail with a confusing
    downstream error.

    - Bypassed when ``--force`` appears in argv (intentionally undocumented).
    - Fails OPEN (see ``_cli_below_minimum``) so offline use isn't bricked.
    - When it does NOT block, the result is cached for ``_MIN_VERSION_CHECK_TTL``
      seconds (avoids re-fetching on every request). The blocking path is never
      cached, so a long-running session (e.g. an MCP server) keeps getting
      stopped until it's restarted on an up-to-date CLI.
    """
    global _last_min_version_ok

    if "--force" in sys.argv:
        return

    now = time.monotonic()
    if (
        _last_min_version_ok is not None
        and now - _last_min_version_ok < _MIN_VERSION_CHECK_TTL
    ):
        return

    below, current, minimum = _cli_below_minimum(backend_url)
    if not below:
        _last_min_version_ok = now
        return

    logger = get_logger()
    logger.error(
        f"Your dispatch CLI (v{current}) is below the minimum version "
        f"(v{minimum}) supported by this backend. Update before continuing:"
    )
    logger.code(
        "uv tool install git+ssh://git@github.com/datadog-labs/"
        "dispatch_agents_cli.git --upgrade",
        "bash",
        "To update, run:",
    )
    logger.info(
        "If a long-running session is using the CLI (e.g. an MCP server in "
        "your editor or Claude), restart it after updating so it loads the "
        "new version."
    )
    raise typer.Exit(1)


def _ensure_cache_dir():
    """Ensure cache directory exists."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_cached_version_info() -> dict | None:
    """Read cached version information from disk.

    Returns:
        dict with 'last_check' and 'latest_version' keys, or None if cache doesn't exist
    """
    if not VERSION_CHECK_CACHE.exists():
        return None

    try:
        with open(VERSION_CHECK_CACHE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # If cache is corrupted, treat as if it doesn't exist
        return None


def _save_version_cache(data: dict):
    """Save version check information to cache.

    Args:
        data: dict with 'last_check' (ISO format) and 'latest_version' keys
    """
    _ensure_cache_dir()
    try:
        with open(VERSION_CHECK_CACHE, "w") as f:
            json.dump(data, f)
    except OSError:
        # If we can't write cache, silently continue (don't block user)
        pass


def _should_check_version() -> bool:
    """Check if we should query the backend for version updates.

    Returns:
        True if more than 24 hours since last check, False otherwise
    """
    cache = _get_cached_version_info()
    if cache is None:
        return True

    try:
        last_check = datetime.fromisoformat(cache["last_check"])
        return datetime.now() - last_check > VERSION_CHECK_INTERVAL
    except (KeyError, ValueError):
        # If cache is invalid, check again
        return True


def _fetch_version_requirements(backend_url: str) -> dict | None:
    """Fetch version requirements from backend.

    Args:
        backend_url: Base URL of the backend API

    Returns:
        dict with version requirements, or None if request fails
    """
    try:
        response = requests.get(
            f"{backend_url}/api/unstable/version",
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        # Silently fail - don't block user if backend is unreachable
        return None


def check_and_notify_cli_update(backend_url: str):
    """Check for CLI updates and notify user if available.

    This function is called once per day (cached). If a newer version is available,
    it displays a friendly notification with upgrade instructions.

    Args:
        backend_url: Base URL of the backend API
    """
    if not sys.stdout.isatty():
        return

    if not _should_check_version():
        return

    try:
        current_version = _get_version("dispatch-cli")
    except Exception:
        # If we can't get the version, silently skip the check
        return

    requirements = get_sdk_version_requirements(backend_url)

    if requirements is None:
        return

    # Save cache with current timestamp
    _save_version_cache(
        {
            "last_check": datetime.now().isoformat(),
            "latest_version": requirements["cli_current"],
        }
    )

    try:
        latest_version = requirements["cli_current"]
        if Version(latest_version) > Version(current_version):
            upgrade_command = "uv tool install git+ssh://git@github.com/datadog-labs/dispatch_agents_cli.git --upgrade"

            # Use raw print to avoid wrapping (logger not initialized yet in callback)
            print(file=sys.stdout)
            print(
                f"\033[33mNew CLI Version Available: v{latest_version}\033[0m (current: v{current_version})",
                file=sys.stdout,
            )
            print("To update, run:", file=sys.stdout)
            print(f"  {upgrade_command}", file=sys.stdout)
            print(file=sys.stdout)
    except (KeyError, ValueError, TypeError):
        # If version comparison fails, silently continue
        pass


def get_sdk_version_requirements(backend_url: str) -> dict | None:
    """Fetch version requirements from backend.

    Args:
        backend_url: Base URL of the backend API

    Returns:
        dict with version requirements for CLI and SDK, or None if request fails
        Format: {
            "cli_current": "0.1.5",
            "cli_minimum": "0.1.3",
            "sdk_current": "0.1.14",
            "sdk_minimum": "0.1.10"
        }
    """
    version_data = _fetch_version_requirements(backend_url)
    if version_data is None:
        return None

    try:
        requirements = version_data["requirements"]
        return {
            "cli_current": requirements["cli_current"],
            "cli_minimum": requirements["cli_minimum"],
            "sdk_current": requirements["sdk_current"],
            "sdk_minimum": requirements["sdk_minimum"],
        }
    except KeyError:
        return None


def validate_sdk_version(
    detected_version: str, backend_url: str
) -> tuple[str, str | None]:
    """Validate SDK version against backend requirements.

    Args:
        detected_version: SDK version detected in the agent
        backend_url: Base URL of the backend API

    Returns:
        tuple of (status, message) where status is one of:
            - "valid": SDK version is acceptable
            - "outdated": SDK version is below current but above minimum (warning)
            - "blocked": SDK version is below minimum (deploy should be blocked)
            - "error": Could not validate (allow deploy but warn)
    """
    requirements = get_sdk_version_requirements(backend_url)

    if requirements is None:
        return (
            "error",
            "Could not fetch SDK version requirements from backend. Proceeding anyway.",
        )

    try:
        detected = Version(detected_version)
        minimum = Version(requirements["sdk_minimum"])

        if detected < minimum:
            update_cmd = "uv add dispatch-agents --upgrade"
            return (
                "blocked",
                f"SDK version {detected_version} is below minimum required version {requirements['sdk_minimum']}.\n\n"
                f"To update, run:\n{update_cmd}",
            )
        else:
            return ("valid", None)

    except (ValueError, TypeError):
        return (
            "error",
            f"Could not parse SDK version '{detected_version}'. Proceeding anyway.",
        )


def get_cli_suggested_sdk_version() -> str | None:
    """Get the SDK version that ships with this CLI.

    This represents the "suggested" SDK version for agent projects,
    since it's the version the CLI was built and tested against.

    Returns:
        SDK version string, or None if detection fails
    """
    try:
        return _get_version("dispatch_agents")
    except PackageNotFoundError:
        return None


def check_sdk_version_suggestion(
    detected_version: str | None,
) -> tuple[str, str | None]:
    """Check if agent's SDK version matches CLI's suggested version.

    This provides a local check without calling the backend. Use this
    for quick validation during init/dev commands.

    Args:
        detected_version: SDK version detected in the agent project, or None

    Returns:
        tuple of (status, message) where status is one of:
            - "current": SDK version matches CLI's suggested version
            - "outdated": SDK version is older than CLI's suggested version
            - "newer": SDK version is newer than CLI's suggested version (ok)
            - "not_installed": SDK not found in agent project
            - "error": Could not determine versions
    """
    suggested = get_cli_suggested_sdk_version()

    if suggested is None:
        return ("error", "Could not determine CLI's suggested SDK version.")

    if detected_version is None:
        update_cmd = "uv add dispatch-agents"
        return (
            "not_installed",
            f"SDK not installed. To add it, run:\n{update_cmd}",
        )

    try:
        detected = Version(detected_version)
        suggested_ver = Version(suggested)

        if detected < suggested_ver:
            update_cmd = "uv add dispatch-agents --upgrade"
            return (
                "outdated",
                f"SDK version {detected_version} is older than CLI's suggested version {suggested}.\n\n"
                f"To update, run:\n{update_cmd}",
            )
        elif detected > suggested_ver:
            # Agent has a newer SDK than CLI ships with - that's fine
            return ("newer", None)
        else:
            return ("current", None)

    except (ValueError, TypeError):
        return (
            "error",
            f"Could not parse SDK version '{detected_version}'.",
        )
