"""Tests for the CI version policy helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "scripts" / "version_policy.py"
)
MODULE_NAME = "dispatch_cli_ci_version_policy"

spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
assert spec is not None
assert spec.loader is not None
version_policy = importlib.util.module_from_spec(spec)
sys.modules[MODULE_NAME] = version_policy
spec.loader.exec_module(version_policy)


def pyproject(
    *,
    version: str,
    description: str = "Dispatch CLI",
    packages: list[str] | None = None,
    dependency_sources: dict[str, dict[str, str]] | None = None,
    dev_dependencies: list[str] | None = None,
) -> dict[str, object]:
    return {
        "build-system": {
            "requires": ["hatchling"],
            "build-backend": "hatchling.build",
        },
        "project": {
            "name": "dispatch-cli",
            "version": version,
            "description": description,
            "dependencies": ["typer>=0.16.1", "dispatch_agents"],
            "scripts": {"dispatch": "dispatch_cli.main:app"},
        },
        "tool": {
            "hatch": {
                "build": {
                    "targets": {"wheel": {"packages": packages or ["dispatch_cli"]}}
                },
                "metadata": {"allow-direct-references": True},
            },
            "uv": {
                "sources": dependency_sources
                or {
                    "dispatch_agents": {
                        "git": "https://github.com/datadog-labs/dispatch_agents_sdk",
                        "tag": "v0.7.3",
                    }
                }
            },
            "ruff": {"line-length": 88},
        },
        "dependency-groups": {
            "dev": dev_dependencies or ["pytest>=7.0.0", "ruff>=0.8.0"]
        },
    }


def test_extract_shipped_path_prefixes_from_hatch_packages():
    assert version_policy.extract_shipped_path_prefixes(
        pyproject(version="0.5.0", packages=["dispatch_cli", "other_pkg"])
    ) == ("dispatch_cli/", "other_pkg/")


def test_feature_branch_sdk_change_requires_bump_when_version_is_unchanged():
    result = version_policy.evaluate_policy(
        mode="feature-branch",
        changed_files=["dispatch_cli/main.py"],
        current_pyproject=pyproject(version="0.5.0"),
        baseline_pyproject=pyproject(version="0.5.0"),
        baseline_ref="origin/main",
        baseline_version="0.5.0",
    )

    assert result.requires_version_bump is True
    assert result.has_version_bump is False
    assert result.should_release is False
    assert result.failure_reason is not None


def test_feature_branch_sdk_change_passes_with_higher_version():
    result = version_policy.evaluate_policy(
        mode="feature-branch",
        changed_files=["dispatch_cli/main.py"],
        current_pyproject=pyproject(version="0.5.1"),
        baseline_pyproject=pyproject(version="0.5.0"),
        baseline_ref="origin/main",
        baseline_version="0.5.0",
    )

    assert result.requires_version_bump is True
    assert result.has_version_bump is True
    assert result.should_release is False
    assert result.failure_reason is None


def test_feature_branch_docs_only_change_does_not_require_bump():
    result = version_policy.evaluate_policy(
        mode="feature-branch",
        changed_files=["README.md", ".github/workflows/release.yml"],
        current_pyproject=pyproject(version="0.5.0"),
        baseline_pyproject=pyproject(version="0.5.0"),
        baseline_ref="origin/main",
        baseline_version="0.5.0",
    )

    assert result.requires_version_bump is False
    assert result.has_version_bump is False
    assert result.should_release is False
    assert result.failure_reason is None


def test_feature_branch_docs_only_change_can_be_behind_main_version():
    result = version_policy.evaluate_policy(
        mode="feature-branch",
        changed_files=["README.md"],
        current_pyproject=pyproject(version="0.5.0"),
        baseline_pyproject=pyproject(version="0.5.1"),
        baseline_ref="origin/main",
        baseline_version="0.5.1",
    )

    assert result.requires_version_bump is False
    assert result.failure_reason is None


def test_relevant_pyproject_change_requires_bump():
    result = version_policy.evaluate_policy(
        mode="feature-branch",
        changed_files=["pyproject.toml"],
        current_pyproject=pyproject(version="0.5.0", description="Updated CLI"),
        baseline_pyproject=pyproject(version="0.5.0"),
        baseline_ref="origin/main",
        baseline_version="0.5.0",
    )

    assert result.relevant_pyproject_changed is True
    assert result.requires_version_bump is True
    assert result.failure_reason is not None


def test_dev_tooling_pyproject_change_does_not_require_bump():
    result = version_policy.evaluate_policy(
        mode="feature-branch",
        changed_files=["pyproject.toml"],
        current_pyproject=pyproject(
            version="0.5.0",
            dev_dependencies=["pytest>=7.0.0", "ruff>=0.9.0"],
        ),
        baseline_pyproject=pyproject(version="0.5.0"),
        baseline_ref="origin/main",
        baseline_version="0.5.0",
    )

    assert result.relevant_pyproject_changed is False
    assert result.requires_version_bump is False
    assert result.failure_reason is None


def test_release_change_requires_bump_when_version_is_unchanged():
    result = version_policy.evaluate_policy(
        mode="release",
        changed_files=["dispatch_cli/main.py"],
        current_pyproject=pyproject(version="0.5.0"),
        baseline_pyproject=pyproject(version="0.4.9"),
        baseline_ref="v0.5.0",
        baseline_version="0.5.0",
    )

    assert result.requires_version_bump is True
    assert result.has_version_bump is False
    assert result.should_release is False
    assert result.failure_reason is not None


def test_release_change_passes_with_higher_version():
    result = version_policy.evaluate_policy(
        mode="release",
        changed_files=["dispatch_cli/main.py"],
        current_pyproject=pyproject(version="0.5.1"),
        baseline_pyproject=pyproject(version="0.5.0"),
        baseline_ref="v0.5.0",
        baseline_version="0.5.0",
    )

    assert result.requires_version_bump is True
    assert result.has_version_bump is True
    assert result.should_release is True
    assert result.failure_reason is None


def test_release_docs_only_change_does_not_require_release():
    result = version_policy.evaluate_policy(
        mode="release",
        changed_files=["README.md"],
        current_pyproject=pyproject(version="0.5.0"),
        baseline_pyproject=pyproject(version="0.5.0"),
        baseline_ref="v0.5.0",
        baseline_version="0.5.0",
    )

    assert result.requires_version_bump is False
    assert result.should_release is False
    assert result.failure_reason is None


def test_release_lower_than_latest_tag_fails():
    result = version_policy.evaluate_policy(
        mode="release",
        changed_files=["README.md"],
        current_pyproject=pyproject(version="0.4.9"),
        baseline_pyproject=pyproject(version="0.5.0"),
        baseline_ref="v0.5.0",
        baseline_version="0.5.0",
    )

    assert result.failure_reason == (
        "Current version v0.4.9 is behind latest release v0.5.0."
    )


def test_unknown_top_level_path_requires_bump():
    result = version_policy.evaluate_policy(
        mode="feature-branch",
        changed_files=["new-surface/config.json"],
        current_pyproject=pyproject(version="0.5.0"),
        baseline_pyproject=pyproject(version="0.5.0"),
        baseline_ref="origin/main",
        baseline_version="0.5.0",
    )

    assert result.unknown_paths == ("new-surface/config.json",)
    assert result.requires_version_bump is True
    assert result.failure_reason is not None


def test_release_without_prior_tag_triggers_initial_release():
    result = version_policy.evaluate_policy(
        mode="release",
        changed_files=["dispatch_cli/main.py"],
        current_pyproject=pyproject(version="0.1.0"),
        baseline_pyproject=None,
        baseline_ref="initial repository state",
        baseline_version=None,
    )

    assert result.requires_version_bump is True
    assert result.has_version_bump is True
    assert result.should_release is True
    assert result.failure_reason is None
