"""Tests for validate_cli_version, _get_version_requirement, and related helpers."""

from unittest.mock import MagicMock, patch


class TestGetVersionRequirement:
    """Tests for _get_version_requirement()."""

    def setup_method(self):
        from dispatch_cli.version_check import _fetch_version_requirements

        _fetch_version_requirements.cache_clear()

    def test_returns_value_for_existing_key(self):
        from dispatch_cli.version_check import _get_version_requirement

        backend_response = {
            "requirements": {"cli_minimum": "0.6.0", "sdk_minimum": "0.1.10"}
        }
        with patch(
            "dispatch_cli.version_check._fetch_version_requirements",
            return_value=backend_response,
        ):
            assert (
                _get_version_requirement("http://localhost", "cli_minimum") == "0.6.0"
            )

    def test_returns_different_key(self):
        from dispatch_cli.version_check import _get_version_requirement

        backend_response = {
            "requirements": {"cli_minimum": "0.6.0", "sdk_minimum": "0.1.10"}
        }
        with patch(
            "dispatch_cli.version_check._fetch_version_requirements",
            return_value=backend_response,
        ):
            assert (
                _get_version_requirement("http://localhost", "sdk_minimum") == "0.1.10"
            )

    def test_returns_none_when_key_missing(self):
        from dispatch_cli.version_check import _get_version_requirement

        with patch(
            "dispatch_cli.version_check._fetch_version_requirements",
            return_value={"requirements": {}},
        ):
            assert _get_version_requirement("http://localhost", "cli_minimum") is None

    def test_returns_none_when_requirements_key_absent(self):
        from dispatch_cli.version_check import _get_version_requirement

        with patch(
            "dispatch_cli.version_check._fetch_version_requirements", return_value={}
        ):
            assert _get_version_requirement("http://localhost", "cli_minimum") is None

    def test_returns_none_when_backend_unreachable(self):
        from dispatch_cli.version_check import _get_version_requirement

        with patch(
            "dispatch_cli.version_check._fetch_version_requirements", return_value=None
        ):
            assert _get_version_requirement("http://localhost", "cli_minimum") is None


class TestValidateCliVersion:
    """Tests for validate_cli_version()."""

    def setup_method(self):
        from dispatch_cli.version_check import _fetch_version_requirements

        _fetch_version_requirements.cache_clear()

    def _mock_minimum(self, version: str | None):
        return patch(
            "dispatch_cli.version_check._get_version_requirement", return_value=version
        )

    def test_valid_when_version_above_minimum(self):
        from dispatch_cli.version_check import validate_cli_version

        with (
            patch("dispatch_cli.version_check._get_version", return_value="0.7.0"),
            self._mock_minimum("0.6.0"),
        ):
            status, message = validate_cli_version("http://localhost")

        assert status == "valid"
        assert message is None

    def test_valid_when_version_equals_minimum(self):
        from dispatch_cli.version_check import validate_cli_version

        with (
            patch("dispatch_cli.version_check._get_version", return_value="0.6.0"),
            self._mock_minimum("0.6.0"),
        ):
            status, message = validate_cli_version("http://localhost")

        assert status == "valid"
        assert message is None

    def test_blocked_when_version_below_minimum(self):
        from dispatch_cli.version_check import validate_cli_version

        with (
            patch("dispatch_cli.version_check._get_version", return_value="0.5.0"),
            self._mock_minimum("0.6.0"),
        ):
            status, message = validate_cli_version("http://localhost")

        assert status == "blocked"
        assert message is not None
        assert "0.5.0" in message
        assert "0.6.0" in message

    def test_blocked_message_contains_update_command(self):
        """The blocked message must include the upgrade command after 'To update, run:'."""
        from dispatch_cli.version_check import validate_cli_version

        with (
            patch("dispatch_cli.version_check._get_version", return_value="0.1.0"),
            self._mock_minimum("0.6.0"),
            patch(
                "dispatch_cli.version_check._fetch_latest_cli_version_from_github",
                return_value=None,
            ),
        ):
            _, message = validate_cli_version("http://localhost")

        assert message is not None
        assert "To update, run:\n" in message
        assert "dispatch_agents_cli" in message
        assert "uv tool install" in message

    def test_blocked_message_includes_version_tag_when_latest_available(self):
        """When GitHub returns a latest version, the update command must include @v<version>."""
        from dispatch_cli.version_check import validate_cli_version

        with (
            patch("dispatch_cli.version_check._get_version", return_value="0.5.0"),
            self._mock_minimum("0.6.0"),
            patch(
                "dispatch_cli.version_check._fetch_latest_cli_version_from_github",
                return_value="0.6.0",
            ),
        ):
            _, message = validate_cli_version("http://localhost")

        assert message is not None
        assert "@v0.6.0" in message

    def test_blocked_message_falls_back_to_untagged_when_latest_unavailable(self):
        """When GitHub returns None, the update command must not include a version tag."""
        from dispatch_cli.version_check import validate_cli_version

        with (
            patch("dispatch_cli.version_check._get_version", return_value="0.5.0"),
            self._mock_minimum("0.6.0"),
            patch(
                "dispatch_cli.version_check._fetch_latest_cli_version_from_github",
                return_value=None,
            ),
        ):
            _, message = validate_cli_version("http://localhost")

        assert message is not None
        assert "@v" not in message
        assert "dispatch_agents_cli.git --upgrade" in message

    def test_error_when_cli_package_not_found(self):
        from importlib.metadata import PackageNotFoundError

        from dispatch_cli.version_check import validate_cli_version

        with patch(
            "dispatch_cli.version_check._get_version",
            side_effect=PackageNotFoundError("dispatch-cli"),
        ):
            status, message = validate_cli_version("http://localhost")

        assert status == "error"
        assert message is not None

    def test_error_when_backend_unreachable(self):
        from dispatch_cli.version_check import validate_cli_version

        with (
            patch("dispatch_cli.version_check._get_version", return_value="0.5.0"),
            self._mock_minimum(None),
        ):
            status, message = validate_cli_version("http://localhost")

        assert status == "error"
        assert message is not None

    def test_error_when_current_version_unparseable(self):
        from dispatch_cli.version_check import validate_cli_version

        with (
            patch(
                "dispatch_cli.version_check._get_version", return_value="not-a-version"
            ),
            self._mock_minimum("0.6.0"),
        ):
            status, message = validate_cli_version("http://localhost")

        assert status == "error"
        assert message is not None

    def test_error_when_minimum_version_unparseable(self):
        from dispatch_cli.version_check import validate_cli_version

        with (
            patch("dispatch_cli.version_check._get_version", return_value="0.5.0"),
            self._mock_minimum("not-a-version"),
        ):
            status, message = validate_cli_version("http://localhost")

        assert status == "error"
        assert message is not None


class TestFetchVersionRequirementsCache:
    """Tests for the lru_cache on _fetch_version_requirements()."""

    def setup_method(self):
        from dispatch_cli.version_check import _fetch_version_requirements

        _fetch_version_requirements.cache_clear()

    def test_second_call_does_not_hit_network(self):
        """Two calls with the same URL should only make one HTTP request."""

        from dispatch_cli.version_check import _fetch_version_requirements

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"requirements": {"cli_minimum": "0.6.0"}}

        with patch(
            "dispatch_cli.version_check.requests.get", return_value=mock_response
        ) as mock_get:
            _fetch_version_requirements("http://localhost")
            _fetch_version_requirements("http://localhost")

        mock_get.assert_called_once()

    def test_different_urls_make_separate_requests(self):
        """Different backend URLs are cached independently."""
        from dispatch_cli.version_check import _fetch_version_requirements

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"requirements": {}}

        with patch(
            "dispatch_cli.version_check.requests.get", return_value=mock_response
        ) as mock_get:
            _fetch_version_requirements("http://host-a")
            _fetch_version_requirements("http://host-b")

        assert mock_get.call_count == 2
