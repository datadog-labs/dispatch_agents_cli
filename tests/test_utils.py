"""Unit tests for utility functions."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from dispatch_cli.utils import (
    DISPATCH_LISTENER_FILE,
    SDK_DEPENDENCY,
    get_sdk_dependency,
    prompt_for_missing_config,
    read_project_config,
    validate_dispatch_project,
)
from dispatch_cli.version_check import (
    check_sdk_version_suggestion,
    validate_sdk_version,
)

PUBLIC_SDK_REPO = "datadog-labs/dispatch_agents_sdk"
PUBLIC_CLI_REPO = "datadog-labs/dispatch_agents_cli"
_SDK_BASE_URL = f"git+ssh://git@github.com/{PUBLIC_SDK_REPO}.git"


class TestPublicRepoUrls:
    """Ensure all customer-facing URLs point to the public repos."""

    def test_sdk_dependency_constant_points_to_public_repo(self):
        """SDK_DEPENDENCY must reference the public SDK repo."""
        assert PUBLIC_SDK_REPO in SDK_DEPENDENCY
        assert "DataDog/dispatch_agents" not in SDK_DEPENDENCY

    def test_get_sdk_dependency_with_version_returns_exact_url(self):
        """get_sdk_dependency() must return the exact versioned URL when a version is detected."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SDK_DEPENDENCY", None)
            with patch(
                "dispatch_cli.version_check.get_cli_suggested_sdk_version",
                return_value="1.2.3",
            ):
                result = get_sdk_dependency()
        assert result == f"{_SDK_BASE_URL}@v1.2.3"

    def test_get_sdk_dependency_fallback_returns_unversioned_url(self):
        """Fallback SDK dependency (no version detected) must use the unversioned public URL."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SDK_DEPENDENCY", None)
            with patch(
                "dispatch_cli.version_check.get_cli_suggested_sdk_version",
                return_value=None,
            ):
                result = get_sdk_dependency()
        assert result == _SDK_BASE_URL
        # Fallback must NOT accidentally acquire a version pin.
        assert "@v" not in result

    def test_get_sdk_dependency_env_override_bypasses_version_logic(self):
        """SDK_DEPENDENCY env var must be returned verbatim, bypassing version detection."""
        custom_url = "git+ssh://git@github.com/custom-org/custom-sdk.git"
        with patch.dict(os.environ, {"SDK_DEPENDENCY": custom_url}, clear=False):
            result = get_sdk_dependency()
        assert result == custom_url


class TestValidateSdkVersion:
    """Tests for validate_sdk_version()."""

    def test_above_minimum_is_valid(self):
        """SDK above minimum should return 'valid' with no message."""
        with patch(
            "dispatch_cli.version_check.get_sdk_version_requirements",
            return_value={"sdk_minimum": "0.0.1"},
        ):
            status, message = validate_sdk_version("0.0.2", "http://fake")
        assert status == "valid"
        assert message is None

    def test_exactly_at_minimum_is_valid(self):
        """SDK at exactly the minimum version is acceptable (comparison is strict <)."""
        with patch(
            "dispatch_cli.version_check.get_sdk_version_requirements",
            return_value={"sdk_minimum": "1.0.0"},
        ):
            status, message = validate_sdk_version("1.0.0", "http://fake")
        assert status == "valid"
        assert message is None

    def test_blocked_message_contains_exact_versioned_uv_command(self):
        """Blocked SDK message must embed a complete, copy-pasteable uv add command with @v pin."""
        expected_cmd = f"uv add {_SDK_BASE_URL}@v1.5.0"
        with (
            patch(
                "dispatch_cli.version_check.get_sdk_version_requirements",
                return_value={"sdk_minimum": "1.0.0"},
            ),
            patch(
                "dispatch_cli.version_check.get_cli_suggested_sdk_version",
                return_value="1.5.0",
            ),
        ):
            status, message = validate_sdk_version("0.0.1", "http://fake")
        assert status == "blocked"
        assert expected_cmd in message
        assert "#subdirectory=" not in message

    def test_blocked_message_without_version_uses_unversioned_command(self):
        """Blocked SDK message must fall back to the unversioned uv add command when version is unknown."""
        expected_cmd = f"uv add {_SDK_BASE_URL}"
        with (
            patch(
                "dispatch_cli.version_check.get_sdk_version_requirements",
                return_value={"sdk_minimum": "1.0.0"},
            ),
            patch(
                "dispatch_cli.version_check.get_cli_suggested_sdk_version",
                return_value=None,
            ),
        ):
            status, message = validate_sdk_version("0.0.1", "http://fake")
        assert status == "blocked"
        assert expected_cmd in message
        # The fallback command must not accidentally include a @v pin.
        assert "@v" not in message

    def test_backend_unreachable_returns_error_status(self):
        """When requirements cannot be fetched, status must be 'error', not a crash."""
        with patch(
            "dispatch_cli.version_check.get_sdk_version_requirements",
            return_value=None,
        ):
            status, message = validate_sdk_version("1.0.0", "http://fake")
        assert status == "error"
        assert message is not None

    def test_unparseable_version_string_returns_error_status(self):
        """A garbage version string must return 'error', not raise an exception."""
        with patch(
            "dispatch_cli.version_check.get_sdk_version_requirements",
            return_value={"sdk_minimum": "1.0.0"},
        ):
            status, message = validate_sdk_version("not-a-version", "http://fake")
        assert status == "error"
        assert message is not None


class TestCheckSdkVersionSuggestion:
    """Tests for check_sdk_version_suggestion()."""

    def test_not_installed_message_contains_exact_versioned_uv_command(self):
        """Not-installed message must embed a complete uv add command with @v pin."""
        expected_cmd = f"uv add {_SDK_BASE_URL}@v1.0.0"
        with patch(
            "dispatch_cli.version_check.get_cli_suggested_sdk_version",
            return_value="1.0.0",
        ):
            status, message = check_sdk_version_suggestion(None)
        assert status == "not_installed"
        assert expected_cmd in message
        assert "#subdirectory=" not in message

    def test_outdated_message_contains_exact_versioned_uv_command(self):
        """Outdated message must embed a complete uv add command with @v pin."""
        expected_cmd = f"uv add {_SDK_BASE_URL}@v2.0.0"
        with patch(
            "dispatch_cli.version_check.get_cli_suggested_sdk_version",
            return_value="2.0.0",
        ):
            status, message = check_sdk_version_suggestion("1.0.0")
        assert status == "outdated"
        assert expected_cmd in message
        assert "#subdirectory=" not in message

    def test_current_version_returns_current_status(self):
        """SDK exactly matching the suggested version must return 'current'."""
        with patch(
            "dispatch_cli.version_check.get_cli_suggested_sdk_version",
            return_value="1.0.0",
        ):
            status, message = check_sdk_version_suggestion("1.0.0")
        assert status == "current"
        assert message is None

    def test_newer_sdk_than_suggested_returns_newer_status(self):
        """Agent SDK newer than CLI's suggested version must return 'newer' (not an error)."""
        with patch(
            "dispatch_cli.version_check.get_cli_suggested_sdk_version",
            return_value="1.0.0",
        ):
            status, message = check_sdk_version_suggestion("2.0.0")
        assert status == "newer"
        assert message is None

    def test_cli_suggested_version_unknown_returns_error_status(self):
        """When the CLI cannot determine its own bundled SDK version, return 'error', not a crash."""
        with patch(
            "dispatch_cli.version_check.get_cli_suggested_sdk_version",
            return_value=None,
        ):
            status, message = check_sdk_version_suggestion(None)
        assert status == "error"
        assert message is not None

    def test_unparseable_detected_version_returns_error_status(self):
        """A garbage detected version string must return 'error', not raise."""
        with patch(
            "dispatch_cli.version_check.get_cli_suggested_sdk_version",
            return_value="1.0.0",
        ):
            status, message = check_sdk_version_suggestion("not-a-version")
        assert status == "error"
        assert message is not None


class TestDetectProjectConfig:
    def test_reads_tool_dispatch_config(self):
        """Should read [tool.dispatch] section from pyproject.toml."""
        pyproject_content = """
[tool.dispatch]
base_image = "python:3.11-slim"
port = 3000
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            pyproject_path = os.path.join(tmpdir, "pyproject.toml")
            with open(pyproject_path, "w") as f:
                f.write(pyproject_content)

            config = read_project_config(tmpdir)

        # Only keys present in pyproject.toml and in DEFAULT_CONFIG are returned
        # "port" is not in DEFAULT_CONFIG so it's filtered out (shown in warning)
        assert config == {"base_image": "python:3.11-slim"}


class TestEntrypointConfig:
    def test_discovers_agent_py(self):
        """Should discover agent.py if it exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_path = os.path.join(tmpdir, "agent.py")
            with open(agent_path, "w") as f:
                f.write(
                    "from dispatch_agents import on\n\n@on(topic='test')\nasync def trigger(message: dispatch_agents.Message): pass"
                )

            config = {"entrypoint": None}
            with patch(
                "typer.prompt",
                side_effect=["test-namespace", "agent.py", "python:3.11-slim", ""],
            ):
                # prompt_for_missing_config returns only the updated config (not a tuple)
                # Order: namespace, entrypoint, base_image, system_packages
                config = prompt_for_missing_config(config, path=tmpdir)
                entrypoint = config["entrypoint"]

        assert entrypoint == "agent.py"


class TestValidateDispatchProject:
    def test_returns_true_when_files_exist(self):
        """Should return True when files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # create the .dispatch directory
            dispatch_dir = os.path.join(tmpdir, ".dispatch")
            os.makedirs(dispatch_dir)
            # create the pyproject.toml file with the entry point
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[tool.dispatch]\nentrypoint = 'agent.py'\n")
            # create the dispatch.yaml file (required by validate_dispatch_project)
            with open(os.path.join(tmpdir, ".dispatch.yaml"), "w") as f:
                f.write("entrypoint: agent.py\nnamespace: test\n")
            # create the Dockerfile file
            Path(os.path.join(dispatch_dir, "Dockerfile")).touch()
            # create the agent.py file
            with open(os.path.join(tmpdir, "agent.py"), "w") as f:
                f.write(
                    "from dispatch_agents import on\n\n@on(topic='test')\nasync def trigger(message: dispatch_agents.Message): pass"
                )
            # create the listener file
            Path(os.path.join(dispatch_dir, DISPATCH_LISTENER_FILE)).touch()

            result = validate_dispatch_project(tmpdir)

        assert result

    def test_returns_false_when_dispatch_dir_missing(self):
        """Should return False when .dispatch directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_dispatch_project(tmpdir)
            assert not result


class TestPromptForMissingConfig:
    def test_prompts_for_all_missing_options(self):
        """Should prompt for all missing config options."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "entrypoint": None,
                "base_image": None,
                "system_packages": None,
            }

            with (
                patch(
                    "typer.prompt",
                    side_effect=[
                        "test-namespace",
                        "agent.py",
                        "python:3.11-slim",
                        ["git", "vim"],
                    ],
                ) as mock_prompt,
                patch("typer.confirm", return_value=True),
            ):
                # prompt_for_missing_config returns only the updated config (not a tuple)
                updated_config = prompt_for_missing_config(config, path=tmpdir)

            assert updated_config["entrypoint"] == "agent.py"
            assert updated_config["namespace"] == "test-namespace"
            assert updated_config["base_image"] == "python:3.11-slim"
            assert updated_config["system_packages"] == ["git", "vim"]
            assert mock_prompt.call_count == 4

    def test_skips_existing_config_options(self):
        """Should not prompt for options already in config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "entrypoint": "main.py",
                "namespace": "test-ns",
                "base_image": None,
            }
            # create main.py with the entrypoint
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write(
                    "from dispatch_agents import on\n\n@on(topic='test')\nasync def handler(message: dispatch_agents.Message): pass"
                )

            with patch(
                "typer.prompt", side_effect=["python:3.11-slim", []]
            ) as mock_prompt:
                # prompt_for_missing_config returns only the updated config (not a tuple)
                updated_config = prompt_for_missing_config(config, path=tmpdir)

            # Should keep existing values
            assert updated_config["entrypoint"] == "main.py"
            assert updated_config["namespace"] == "test-ns"

            # Should prompt for missing ones
            assert updated_config["base_image"] == "python:3.11-slim"
            assert updated_config["system_packages"] == []
            assert mock_prompt.call_count == 2
