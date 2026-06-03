"""Tests for `dispatch agent clone`.

Covers the post-download transforms that make a clone usable: flattening
the packager's ``agent/`` wrapper, overlaying the authoritative
dispatch.yaml served alongside the archive, and dropping the empty
``dependencies/`` directory the packager always creates.
"""

import io
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dispatch_cli.main import app


def _make_source_tar_gz() -> bytes:
    """Build a source bundle the way ``create_source_package`` does.

    A ``package/agent/`` tree (with an empty ``dependencies/`` directory)
    added via ``tar.add(package_dir, arcname=".")`` — so members look like
    ``./agent/dispatch.yaml``, exercising the ``./`` + ``agent/`` stripping.
    """
    with tempfile.TemporaryDirectory() as staging:
        agent_dir = Path(staging) / "agent"
        (agent_dir / "pkg").mkdir(parents=True)
        (agent_dir / "dependencies").mkdir()
        (agent_dir / "dispatch.yaml").write_bytes(
            b"agent_name: test987\nvars:\n  stale: true\n"
        )
        (agent_dir / "agent.py").write_bytes(b"print('hi')\n")
        (agent_dir / "pkg" / "mod.py").write_bytes(b"x = 1\n")

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(staging, arcname=".")
        return buf.getvalue()


def _responses(tar_gz: bytes, config_body: bytes | None, config_status: int = 200):
    """Build a requests.get side_effect serving the source then the config."""

    def _side_effect(url: str, *args: object, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url.endswith("/source/config"):
            resp.status_code = config_status
            resp.content = config_body or b""
        else:
            resp.status_code = 200
            resp.content = tar_gz
        return resp

    return _side_effect


@patch("dispatch_cli.commands.agent.get_auth_headers", return_value={})
@patch("dispatch_cli.commands.agent.requests.get")
def test_clone_flattens_overlays_and_drops_empty_deps(
    mock_get: MagicMock, _mock_auth: MagicMock
) -> None:
    fresh_config = b"agent_name: test987\nvars:\n  stale: false\n"
    mock_get.side_effect = _responses(_make_source_tar_gz(), fresh_config)

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "out"
        result = CliRunner().invoke(
            app,
            ["agent", "clone", "test987", "--namespace", "ns", "--path", str(dest)],
        )

        assert result.exit_code == 0, result.output
        # agent/ wrapper is gone — files land at the destination root.
        assert (dest / "agent.py").is_file()
        assert (dest / "pkg" / "mod.py").is_file()
        assert not (dest / "agent").exists()
        # Authoritative dispatch.yaml overlaid over the stale embedded copy.
        assert (dest / "dispatch.yaml").read_bytes() == fresh_config
        # Empty dependencies/ dir removed.
        assert not (dest / "dependencies").exists()


@patch("dispatch_cli.commands.agent.get_auth_headers", return_value={})
@patch("dispatch_cli.commands.agent.requests.get")
def test_clone_keeps_embedded_config_on_204(
    mock_get: MagicMock, _mock_auth: MagicMock
) -> None:
    # 204 => no metadata file alongside the archive; keep the embedded copy.
    mock_get.side_effect = _responses(_make_source_tar_gz(), None, config_status=204)

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "out"
        result = CliRunner().invoke(
            app,
            ["agent", "clone", "test987", "--namespace", "ns", "--path", str(dest)],
        )

        assert result.exit_code == 0, result.output
        assert b"stale: true" in (dest / "dispatch.yaml").read_bytes()
