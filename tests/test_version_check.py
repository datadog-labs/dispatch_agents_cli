"""Tests for CLI version check functions."""

from unittest.mock import MagicMock, patch


class TestFetchLatestCliVersionFromGitHub:
    """Tests for _fetch_latest_cli_version_from_github()."""

    def test_strips_v_prefix_from_tag_name(self):
        """tag_name 'v0.5.0' should return '0.5.0'."""
        from dispatch_cli.version_check import _fetch_latest_cli_version_from_github

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"tag_name": "v0.5.0"}

        with patch(
            "dispatch_cli.version_check.requests.get", return_value=mock_response
        ):
            result = _fetch_latest_cli_version_from_github()

        assert result == "0.5.0"

    def test_returns_none_on_network_error(self):
        """Network failure should return None silently."""
        import requests as req

        from dispatch_cli.version_check import _fetch_latest_cli_version_from_github

        with patch(
            "dispatch_cli.version_check.requests.get",
            side_effect=req.RequestException("timeout"),
        ):
            result = _fetch_latest_cli_version_from_github()

        assert result is None

    def test_returns_none_on_non_200_response(self):
        """Non-200 HTTP response should return None silently."""
        import requests as req

        from dispatch_cli.version_check import _fetch_latest_cli_version_from_github

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req.HTTPError("403")

        with patch(
            "dispatch_cli.version_check.requests.get", return_value=mock_response
        ):
            result = _fetch_latest_cli_version_from_github()

        assert result is None

    def test_returns_none_when_tag_name_missing(self):
        """Missing tag_name key should return None silently."""
        from dispatch_cli.version_check import _fetch_latest_cli_version_from_github

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {}  # no tag_name

        with patch(
            "dispatch_cli.version_check.requests.get", return_value=mock_response
        ):
            result = _fetch_latest_cli_version_from_github()

        assert result is None


class TestCheckAndNotifyCliUpdate:
    """Tests for check_and_notify_cli_update()."""

    def test_skips_github_call_when_cache_is_recent(self):
        """Should not call GitHub API if cache is recent."""
        from dispatch_cli.version_check import check_and_notify_cli_update

        with (
            patch(
                "dispatch_cli.version_check._should_check_version", return_value=False
            ),
            patch("dispatch_cli.version_check.requests.get") as mock_get,
        ):
            check_and_notify_cli_update()

        mock_get.assert_not_called()

    def test_no_notification_when_github_unreachable(self):
        """Should fail silently when GitHub is unreachable."""
        import requests as req

        from dispatch_cli.version_check import check_and_notify_cli_update

        with (
            patch(
                "dispatch_cli.version_check._should_check_version", return_value=True
            ),
            patch("dispatch_cli.version_check._get_version", return_value="0.5.0"),
            patch(
                "dispatch_cli.version_check.requests.get",
                side_effect=req.RequestException("timeout"),
            ),
            patch("sys.stdout") as mock_stdout,
        ):
            check_and_notify_cli_update()

        # Should not have printed anything
        mock_stdout.write.assert_not_called()

    def test_prints_notification_when_update_available(self, capsys):
        """Should print update notification when newer version is available."""
        from dispatch_cli.version_check import check_and_notify_cli_update

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"tag_name": "v99.0.0"}

        with (
            patch(
                "dispatch_cli.version_check._should_check_version", return_value=True
            ),
            patch("dispatch_cli.version_check._get_version", return_value="0.5.0"),
            patch(
                "dispatch_cli.version_check.requests.get", return_value=mock_response
            ),
            patch("dispatch_cli.version_check._save_version_cache"),
        ):
            check_and_notify_cli_update()

        captured = capsys.readouterr()
        assert "99.0.0" in captured.out
        assert "@v99.0.0" in captured.out
