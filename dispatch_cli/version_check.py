"""CLI version checking and upgrade notifications.

Checks for CLI updates once per hour (cached) and SDK version on every deploy.
Also provides SDK version suggestion for agent projects based on CLI's bundled SDK.
"""

import json
from datetime import datetime, timedelta
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version
from pathlib import Path

import requests
from packaging.version import Version
from platformdirs import user_cache_dir

# Cache configuration
CACHE_DIR = Path(user_cache_dir("dispatch", "DataDog"))
VERSION_CHECK_CACHE = CACHE_DIR / "version_check.json"
VERSION_CHECK_INTERVAL = timedelta(hours=1)
GITHUB_CLI_REPO = "datadog-labs/dispatch_agents_cli"


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
    """Check if we should query GitHub for version updates.

    Returns:
        True if more than 3 hours since last check, False otherwise
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


@lru_cache(maxsize=1)
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


def _fetch_latest_cli_version_from_github() -> str | None:
    """Fetch the latest CLI version from the GitHub Releases API.

    Returns:
        Latest version string (e.g. "0.5.0"), or None if request fails
    """
    try:
        response = requests.get(
            f"https://api.github.com/repos/{GITHUB_CLI_REPO}/releases/latest",
            timeout=5,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        tag_name = response.json()["tag_name"]
        return tag_name.lstrip("v")
    except (requests.RequestException, KeyError, ValueError):
        return None


def check_and_notify_cli_update():
    """Check for CLI updates and notify user if available.

    Checks GitHub Releases once per 3 hours (cached). If a newer version is
    available, displays a friendly notification with upgrade instructions.
    """
    if not _should_check_version():
        return

    try:
        current_version = _get_version("dispatch-cli")
    except Exception:
        return

    latest_version = _fetch_latest_cli_version_from_github()

    if latest_version is None:
        return

    _save_version_cache(
        {
            "last_check": datetime.now().isoformat(),
            "latest_version": latest_version,
        }
    )

    try:
        if Version(latest_version) > Version(current_version):
            upgrade_command = f"uv tool install git+ssh://git@github.com/datadog-labs/dispatch_agents_cli.git@v{latest_version} --upgrade"

            import sys

            print(file=sys.stdout)
            print(
                f"\033[33mNew CLI Version Available: v{latest_version}\033[0m (current: v{current_version})",
                file=sys.stdout,
            )
            print("To update, run:", file=sys.stdout)
            print(f"  {upgrade_command}", file=sys.stdout)
            print(file=sys.stdout)
    except (ValueError, TypeError):
        pass


def _get_version_requirement(backend_url: str, key: str) -> str | None:
    """Fetch a single version requirement value from the backend.

    Args:
        backend_url: Base URL of the backend API
        key: Key within the requirements dict (e.g. "sdk_minimum", "cli_minimum")

    Returns:
        The version string, or None if the request fails or the key is missing
    """
    version_data = _fetch_version_requirements(backend_url)
    if version_data is None:
        return None
    try:
        return version_data["requirements"][key]
    except KeyError:
        return None


def get_sdk_version_requirements(backend_url: str) -> dict | None:
    """Fetch SDK version requirements from backend.

    Args:
        backend_url: Base URL of the backend API

    Returns:
        dict with SDK version requirements, or None if request fails
        Format: {
            "sdk_minimum": "0.1.10"
        }
    """
    minimum = _get_version_requirement(backend_url, "sdk_minimum")
    return {"sdk_minimum": minimum} if minimum is not None else None


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
            suggested = get_cli_suggested_sdk_version()
            update_cmd = (
                f"uv add git+ssh://git@github.com/datadog-labs/dispatch_agents_sdk.git@v{suggested}"
                if suggested
                else "uv add git+ssh://git@github.com/datadog-labs/dispatch_agents_sdk.git"
            )
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


def validate_cli_version(backend_url: str) -> tuple[str, str | None]:
    """Validate the installed CLI version against backend requirements.

    Args:
        backend_url: Base URL of the backend API

    Returns:
        tuple of (status, message) where status is one of:
            - "valid": CLI version is acceptable
            - "blocked": CLI version is below minimum (deploy should be blocked)
            - "error": Could not validate (allow deploy but warn)
    """
    try:
        current_version = _get_version("dispatch-cli")
    except PackageNotFoundError:
        return ("error", "Could not determine CLI version. Proceeding anyway.")

    cli_minimum = _get_version_requirement(backend_url, "cli_minimum")
    if cli_minimum is None:
        return (
            "error",
            "Could not fetch CLI version requirements from backend. Proceeding anyway.",
        )

    try:
        if Version(current_version) < Version(cli_minimum):
            latest = _fetch_latest_cli_version_from_github()
            update_cmd = (
                f"uv tool install git+ssh://git@github.com/datadog-labs/dispatch_agents_cli.git@v{latest} --upgrade"
                if latest
                else "uv tool install git+ssh://git@github.com/datadog-labs/dispatch_agents_cli.git --upgrade"
            )
            return (
                "blocked",
                f"CLI version {current_version} is below the minimum required version "
                f"{cli_minimum}.\n\nTo update, run:\n{update_cmd}",
            )
    except (ValueError, TypeError):
        return ("error", "Could not parse CLI version. Proceeding anyway.")

    return ("valid", None)


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
        update_cmd = f"uv add git+ssh://git@github.com/datadog-labs/dispatch_agents_sdk.git@v{suggested}"
        return (
            "not_installed",
            f"SDK not installed. To add it, run:\n{update_cmd}",
        )

    try:
        detected = Version(detected_version)
        suggested_ver = Version(suggested)

        if detected < suggested_ver:
            update_cmd = f"uv add git+ssh://git@github.com/datadog-labs/dispatch_agents_sdk.git@v{suggested}"
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
