"""Dispatch CLI main entry point."""

from importlib.metadata import version as _version

import questionary
import typer

from .commands.agent import agent_app
from .commands.llm import llm_app
from .commands.mcp import mcp_app
from .commands.registry import registry_app
from .commands.router import router_app
from .commands.secrets import secrets_app
from .commands.skills import skills_app
from .utils import DISPATCH_API_BASE
from .version_check import check_and_notify_cli_update

app = typer.Typer(no_args_is_help=True)
app.add_typer(agent_app)
app.add_typer(llm_app)
app.add_typer(mcp_app)
app.add_typer(registry_app)
app.add_typer(router_app)
app.add_typer(secrets_app)
app.add_typer(skills_app)

__version__ = _version("dispatch-cli")


@app.callback()
def main_callback(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output (show debug messages)",
    ),
):
    """Run before every command to check for CLI updates.

    This checks for updates once per day (cached) and notifies users
    if a newer version is available.
    """
    # Initialize global logger with verbosity setting
    from .logger import set_logger

    set_logger(verbose=verbose)

    # Check for CLI updates
    check_and_notify_cli_update(DISPATCH_API_BASE)


@app.command()
def version():
    """Show dispatch CLI version and optionally check for updates."""
    from .logger import get_logger
    from .version_check import get_sdk_version_requirements

    logger = get_logger()
    current = __version__
    logger.info(f"Dispatch CLI Version: {current}")

    # Force a version check
    version_data = get_sdk_version_requirements(DISPATCH_API_BASE)
    if version_data:
        from packaging.version import Version

        try:
            latest = version_data["cli_current"]
            current_ver = Version(current)
            latest_ver = Version(latest)

            if latest_ver > current_ver:
                logger.warning(f"A newer version is available: {latest}")
                logger.info("Run 'dispatch update-cli' to see the update command")
            elif latest_ver == current_ver:
                logger.success("You are on the latest version!")
            else:
                logger.debug(f"You are running a pre-release version ({current})")
        except (KeyError, ValueError):
            logger.warning("Could not check for updates")
    else:
        logger.warning("Could not check for updates (backend unreachable)")


@app.command()
def login(
    api_key: str = typer.Option(
        None, "--api-key", help="API key to store (if not provided, will prompt)"
    ),
):
    """Store your API key securely in the system keychain."""
    from .auth import store_api_key_in_keychain, validate_api_key
    from .logger import get_logger

    logger = get_logger()

    # If no API key provided, prompt for it
    if not api_key:
        logger.info("Please enter your Dispatch API key.")
        logger.info(
            f"You can create one at: [link={DISPATCH_API_BASE}/manage/api-keys]{DISPATCH_API_BASE}/manage/api-keys[/link]\n"
        )
        api_key = questionary.password("API Key:").ask()
        if not api_key:
            logger.error("API key cannot be empty")
            raise typer.Exit(1)

    api_key = api_key.strip()

    if not api_key:
        logger.error("API key cannot be empty")
        raise typer.Exit(1)

    # Validate the API key
    with logger.status_context("Validating API key..."):
        if not validate_api_key(api_key, DISPATCH_API_BASE):
            logger.error("Invalid API key")
            logger.info("Please check your API key and try again.")
            raise typer.Exit(1)

    # Store in keychain
    if store_api_key_in_keychain(api_key, DISPATCH_API_BASE):
        logger.success("API key stored securely in system keychain")
        logger.info(
            "You can now use dispatch commands without setting DISPATCH_API_KEY"
        )
    else:
        logger.warning("Could not store API key in keychain")
        logger.info(
            "You may need to set the DISPATCH_API_KEY environment variable instead:"
        )
        logger.code(f"export DISPATCH_API_KEY={api_key}", language="bash")
        raise typer.Exit(1)


@app.command()
def update_cli():
    """Show the command to update the CLI to the latest version."""
    from .logger import get_logger

    logger = get_logger()
    current = __version__
    logger.info(f"Current CLI version: {current}\n")

    logger.code(
        "uv tool install git+ssh://git@github.com/datadog-labs/dispatch_agents_cli.git --upgrade",
        language="bash",
        title="To install the latest stable version:",
    )


if __name__ == "__main__":
    app()
