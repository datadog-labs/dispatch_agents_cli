"""Tests for the hard minimum-CLI-version gate (enforce_minimum_cli_version)."""

from unittest.mock import patch

import pytest
import typer

from dispatch_cli import version_check
from dispatch_cli.version_check import enforce_minimum_cli_version


@pytest.fixture(autouse=True)
def _reset_gate_cache():
    """The gate caches its last passing check in a module global; reset it so
    each case starts fresh (otherwise the TTL short-circuit hides behavior)."""
    version_check._last_min_version_ok = None
    yield
    version_check._last_min_version_ok = None


def _requirements(cli_minimum: str) -> dict:
    return {
        "cli_current": cli_minimum,
        "cli_minimum": cli_minimum,
        "sdk_current": "0.0.0",
        "sdk_minimum": "0.0.0",
    }


@pytest.mark.unit
class TestEnforceMinimumCliVersion:
    def test_blocks_when_below_minimum(self):
        with (
            patch.object(version_check.sys, "argv", ["dispatch", "agent", "deploy"]),
            patch.object(
                version_check,
                "get_sdk_version_requirements",
                return_value=_requirements("0.10.0"),
            ),
            patch.object(version_check, "_get_version", return_value="0.9.0"),
        ):
            with pytest.raises(typer.Exit) as exc:
                enforce_minimum_cli_version("https://backend")
        assert exc.value.exit_code == 1

    def test_allows_when_at_or_above_minimum(self):
        with (
            patch.object(version_check.sys, "argv", ["dispatch", "agent", "deploy"]),
            patch.object(
                version_check,
                "get_sdk_version_requirements",
                return_value=_requirements("0.10.0"),
            ),
            patch.object(version_check, "_get_version", return_value="0.10.0"),
        ):
            # Should not raise.
            enforce_minimum_cli_version("https://backend")

    def test_force_in_argv_bypasses_gate(self):
        # Even though the CLI is below minimum, --force skips the gate.
        with (
            patch.object(
                version_check.sys, "argv", ["dispatch", "agent", "deploy", "--force"]
            ),
            patch.object(
                version_check,
                "get_sdk_version_requirements",
                return_value=_requirements("0.10.0"),
            ),
            patch.object(version_check, "_get_version", return_value="0.9.0"),
        ):
            enforce_minimum_cli_version("https://backend")

    def test_fails_open_when_requirements_unavailable(self):
        # Backend unreachable / offline -> never block.
        with (
            patch.object(version_check.sys, "argv", ["dispatch", "agent", "deploy"]),
            patch.object(
                version_check, "get_sdk_version_requirements", return_value=None
            ),
            patch.object(version_check, "_get_version", return_value="0.9.0"),
        ):
            enforce_minimum_cli_version("https://backend")

    def test_passing_check_is_cached_within_ttl(self):
        # First call fetches; a second call within the TTL must not re-fetch.
        with (
            patch.object(version_check.sys, "argv", ["dispatch", "agent", "deploy"]),
            patch.object(
                version_check,
                "get_sdk_version_requirements",
                return_value=_requirements("0.10.0"),
            ) as get_req,
            patch.object(version_check, "_get_version", return_value="0.10.0"),
        ):
            enforce_minimum_cli_version("https://backend")
            enforce_minimum_cli_version("https://backend")
        assert get_req.call_count == 1
