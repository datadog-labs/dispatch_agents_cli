"""Authentication management for dispatch CLI."""

import os
import subprocess
import sys
from urllib.parse import urlparse

import questionary

from dispatch_cli.logger import get_logger
from dispatch_cli.utils import DISPATCH_API_BASE, DISPATCH_DEPLOY_URL

from .http_client import get_api_headers


def _get_keychain_identifiers(backend_url: str) -> tuple[str, str]:
    """Get keychain service and account names scoped to backend URL.

    Args:
        backend_url: Backend URL to scope the keychain entry to (required).

    Returns:
        Tuple of (service_name, account_name) for keychain operations.

    Example:
        >>> _get_keychain_identifiers("https://dispatchagents.ai")
        ('dispatch-cli', 'dispatchagents-ai')
        >>> _get_keychain_identifiers("https://dispatchagents.work")
        ('dispatch-cli', 'dispatchagents-work')
        >>> _get_keychain_identifiers("http://localhost:8000")
        ('dispatch-cli', 'localhost-8000')
    """
    # Parse URL to extract host and port
    parsed = urlparse(backend_url)

    # Build normalized identifier from netloc (host:port)
    # netloc already includes port if present (e.g., "localhost:8000")
    netloc = parsed.netloc or parsed.path.split("/")[0]

    # Replace dots and colons with hyphens for keychain safety
    # e.g., "dispatchagents.ai" -> "dispatchagents-ai"
    # e.g., "localhost:8000" -> "localhost-8000"
    normalized = netloc.replace(".", "-").replace(":", "-")

    service_name = "dispatch-cli"
    account_name = normalized

    return service_name, account_name


def get_api_key() -> str:
    """Get API key from environment variable or keychain."""
    logger = get_logger()

    # Check environment variable first (takes precedence)
    api_key = os.getenv("DISPATCH_API_KEY")
    if api_key:
        logger.debug("Using API key from DISPATCH_API_KEY environment variable")
        return api_key

    # Try to get from keychain
    try:
        api_key = get_api_key_from_keychain(DISPATCH_API_BASE)
        if api_key:
            logger.debug(f"Found API key in keychain (length={len(api_key)})")
            if validate_api_key(api_key, DISPATCH_DEPLOY_URL):
                logger.debug("API key validation passed")
                return api_key
            else:
                logger.debug("API key validation failed, will prompt for new key")
        else:
            logger.debug("No API key found in keychain")
    except Exception as e:
        logger.debug(f"Error getting API key from keychain: {e}")

    # If no key found, prompt user to log in
    return prompt_for_api_key()


def get_api_key_from_keychain(backend_url: str) -> str | None:
    """Retrieve API key from system keychain.

    Args:
        backend_url: Backend URL to scope the keychain entry to.

    Returns:
        API key if found, None otherwise.
    """
    service_name, account_name = _get_keychain_identifiers(backend_url)
    logger = get_logger()
    logger.debug(
        f"Retrieving API key from keychain: service={service_name}, account={account_name}"
    )

    if sys.platform == "darwin":  # macOS
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    service_name,
                    "-a",
                    account_name,
                    "-w",  # output password only
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None
    elif sys.platform.startswith("linux"):  # Linux
        try:
            # Use secret-tool if available
            result = subprocess.run(
                [
                    "secret-tool",
                    "lookup",
                    "service",
                    service_name,
                    "account",
                    account_name,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
    elif sys.platform == "win32":  # Windows
        try:
            # Use Windows Credential Manager via cmdkey
            result = subprocess.run(
                ["cmdkey", f"/list:{service_name}"],
                capture_output=True,
                text=True,
                check=True,
            )
            # This is a simplified approach - in practice, you might want to use
            # the Windows Credential API through a library like keyring
            return None  # Simplified for now
        except subprocess.CalledProcessError:
            return None

    return None


def store_api_key_in_keychain(api_key: str, backend_url: str) -> bool:
    """Store API key in system keychain.

    Args:
        api_key: API key to store.
        backend_url: Backend URL to scope the keychain entry to.

    Returns:
        True if successful, False otherwise.
    """
    service_name, account_name = _get_keychain_identifiers(backend_url)
    logger = get_logger()
    logger.debug(
        f"Storing API key in keychain: service={service_name}, account={account_name}"
    )

    if sys.platform == "darwin":  # macOS
        try:
            # First, try to delete any existing entry (ignore errors if it doesn't exist)
            delete_result = subprocess.run(
                [
                    "security",
                    "delete-generic-password",
                    "-s",
                    service_name,
                    "-a",
                    account_name,
                ],
                capture_output=True,
            )
            logger.debug(
                f"Keychain delete result: returncode={delete_result.returncode}, "
                f"stderr={delete_result.stderr.decode() if delete_result.stderr else 'none'}"
            )

            # Now add the new entry
            add_cmd = [
                "security",
                "add-generic-password",
                "-s",
                service_name,
                "-a",
                account_name,
                "-w",
                api_key,
            ]
            logger.debug(
                f"Running: security add-generic-password -s {service_name} -a {account_name} -w [REDACTED]"
            )
            result = subprocess.run(
                add_cmd,
                capture_output=True,
            )
            logger.debug(
                f"Keychain add result: returncode={result.returncode}, "
                f"stdout={result.stdout.decode() if result.stdout else 'none'}, "
                f"stderr={result.stderr.decode() if result.stderr else 'none'}"
            )

            if result.returncode != 0:
                logger.debug("Keychain add failed!")
                return False

            # Verify the entry was actually stored
            verify = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    service_name,
                    "-a",
                    account_name,
                ],
                capture_output=True,
            )
            logger.debug(
                f"Keychain verify result: returncode={verify.returncode}, "
                f"stdout={verify.stdout.decode()[:100] if verify.stdout else 'none'}..."
            )

            if verify.returncode != 0:
                logger.debug(
                    "Keychain verification failed! Entry not found after store."
                )
                return False

            logger.debug("Keychain verification passed!")
            return True
        except Exception as e:
            logger.debug(f"Keychain store exception: {e}")
            return False
    elif sys.platform.startswith("linux"):  # Linux
        try:
            # Use secret-tool if available
            subprocess.run(
                [
                    "secret-tool",
                    "store",
                    "--label",
                    f"Dispatch CLI API Key ({account_name})",
                    "service",
                    service_name,
                    "account",
                    account_name,
                ],
                input=api_key,
                text=True,
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    elif sys.platform == "win32":  # Windows
        try:
            # Use Windows Credential Manager via cmdkey
            subprocess.run(
                [
                    "cmdkey",
                    f"/add:{service_name}",
                    f"/user:{account_name}",
                    f"/pass:{api_key}",
                ],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    return False


def prompt_for_api_key() -> str:
    """Prompt user for API key and store it in keychain."""
    logger = get_logger()
    manage_url = f"{DISPATCH_API_BASE}/manage/api-keys"

    logger.warning("Authentication required!")
    logger.info(f"Please create an API key at: [link={manage_url}]{manage_url}[/link]")
    logger.info("")

    while True:
        api_key = questionary.password("Enter your API key:").ask() or ""

        if not api_key.strip():
            logger.error("API key cannot be empty. Please try again.")
            continue

        api_key = api_key.strip()

        # Try to store in keychain
        if store_api_key_in_keychain(api_key, DISPATCH_API_BASE):
            logger.success("API key stored securely in keychain")
        else:
            logger.warning("Could not store API key in keychain")
            logger.info("    You may need to set DISPATCH_API_KEY environment variable")

        return api_key


def handle_auth_error(error_message: str = "") -> str:
    """Handle authentication errors and prompt for new API key."""
    logger = get_logger()
    logger.error(f"Authentication failed: {error_message}")
    logger.info("Your API key may have expired or been revoked.")
    logger.info("")

    # Remove old key from keychain
    try:
        remove_api_key_from_keychain(DISPATCH_API_BASE)
    except Exception:
        pass

    return prompt_for_api_key()


def remove_api_key_from_keychain(backend_url: str) -> bool:
    """Remove API key from system keychain.

    Args:
        backend_url: Backend URL to scope the keychain entry to.

    Returns:
        True if successful, False otherwise.
    """
    service_name, account_name = _get_keychain_identifiers(backend_url)

    if sys.platform == "darwin":  # macOS
        try:
            subprocess.run(
                [
                    "security",
                    "delete-generic-password",
                    "-s",
                    service_name,
                    "-a",
                    account_name,
                ],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False
    elif sys.platform.startswith("linux"):  # Linux
        try:
            subprocess.run(
                [
                    "secret-tool",
                    "clear",
                    "service",
                    service_name,
                    "account",
                    account_name,
                ],
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    elif sys.platform == "win32":  # Windows
        try:
            subprocess.run(
                ["cmdkey", f"/delete:{service_name}"], check=True, capture_output=True
            )
            return True
        except subprocess.CalledProcessError:
            return False

    return False


def validate_api_key(api_key: str, api_url: str) -> bool:
    """Validate API key by making a test request."""
    import requests

    logger = get_logger()
    url = f"{api_url}/namespaces/list"
    logger.debug(f"Validating API key against: {url}")

    try:
        response = requests.get(
            url,
            headers=get_api_headers(api_key),
            timeout=5,
        )
        logger.debug(f"Validation response: status={response.status_code}")
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"Validation failed with exception: {e}")
        return False
