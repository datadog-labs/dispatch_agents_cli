#!/usr/bin/env python3
"""Enforce release version policy for CI workflows."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SEMVER_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
SEMVER_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

IGNORED_PATH_PREFIXES = (".github/", "tests/", "tasks/")
IGNORED_PATHS = {
    "README.md",
    "CONTRIBUTING.md",
    "NOTICE",
    "LICENSE",
    "LICENSE-3rdparty.csv",
    "SKILL.md",
    "uv.lock",
}


@dataclass(frozen=True)
class PolicyResult:
    mode: str
    current_version: str
    current_tag: str
    baseline_ref: str
    baseline_version: str | None
    requires_version_bump: bool
    has_version_bump: bool
    should_release: bool
    relevant_pyproject_changed: bool
    unknown_paths: tuple[str, ...]
    failure_reason: str | None


def parse_version(version: str) -> tuple[int, int, int]:
    match = SEMVER_VERSION_RE.fullmatch(version)
    if not match:
        raise ValueError(f"Unsupported version format: {version}")
    return tuple(int(part) for part in match.groups())


def parse_tag(tag: str) -> tuple[int, int, int]:
    match = SEMVER_TAG_RE.fullmatch(tag)
    if not match:
        raise ValueError(f"Unsupported tag format: {tag}")
    return tuple(int(part) for part in match.groups())


def filter_semver_tags(tags: Iterable[str]) -> list[str]:
    valid_tags = [tag for tag in tags if SEMVER_TAG_RE.fullmatch(tag)]
    return sorted(valid_tags, key=parse_tag)


def compare_versions(current_version: str, baseline_version: str) -> int:
    current = parse_version(current_version)
    baseline = parse_version(baseline_version)
    if current > baseline:
        return 1
    if current < baseline:
        return -1
    return 0


def extract_shipped_path_prefixes(pyproject_data: dict[str, Any]) -> tuple[str, ...]:
    packages = (
        pyproject_data.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
        .get("packages", [])
    )
    normalized = []
    for package in packages:
        package_name = str(package).strip().strip("/")
        if package_name:
            normalized.append(f"{package_name}/")
    return tuple(normalized)


def is_relevant_pyproject_change(
    current_pyproject: dict[str, Any], baseline_pyproject: dict[str, Any] | None
) -> bool:
    if baseline_pyproject is None:
        return False

    current_project = dict(current_pyproject.get("project", {}))
    baseline_project = dict(baseline_pyproject.get("project", {}))
    current_project.pop("version", None)
    baseline_project.pop("version", None)

    current_tool = current_pyproject.get("tool", {})
    baseline_tool = baseline_pyproject.get("tool", {})

    relevant_current_tool = {
        "hatch": current_tool.get("hatch", {}),
        "uv": current_tool.get("uv", {}),
    }
    relevant_baseline_tool = {
        "hatch": baseline_tool.get("hatch", {}),
        "uv": baseline_tool.get("uv", {}),
    }

    return (
        current_pyproject.get("build-system", {})
        != baseline_pyproject.get("build-system", {})
        or current_project != baseline_project
        or relevant_current_tool != relevant_baseline_tool
    )


def is_shipped_path(path: str, shipped_path_prefixes: tuple[str, ...]) -> bool:
    return path.startswith(shipped_path_prefixes)


def is_ignored_path(path: str) -> bool:
    if path in IGNORED_PATHS:
        return True
    if path.startswith("LICENSE"):
        return True
    return path.startswith(IGNORED_PATH_PREFIXES)


def requires_version_bump(
    changed_files: Iterable[str],
    relevant_pyproject_changed: bool,
    unknown_paths: Iterable[str],
    shipped_path_prefixes: tuple[str, ...],
) -> bool:
    if relevant_pyproject_changed:
        return True
    return any(
        is_shipped_path(path, shipped_path_prefixes) for path in changed_files
    ) or any(unknown_paths)


def evaluate_policy(
    *,
    mode: str,
    changed_files: Iterable[str],
    current_pyproject: dict[str, Any],
    baseline_pyproject: dict[str, Any] | None,
    baseline_ref: str,
    baseline_version: str | None,
) -> PolicyResult:
    current_version = current_pyproject["project"]["version"]
    current_tag = f"v{current_version}"
    shipped_path_prefixes = extract_shipped_path_prefixes(current_pyproject)
    relevant_change = is_relevant_pyproject_change(
        current_pyproject, baseline_pyproject
    )
    changed_files = list(changed_files)
    unknown_paths = tuple(
        path
        for path in changed_files
        if not is_ignored_path(path)
        and not is_shipped_path(path, shipped_path_prefixes)
        and path != "pyproject.toml"
    )
    bump_required = requires_version_bump(
        changed_files,
        relevant_change,
        unknown_paths,
        shipped_path_prefixes,
    )

    comparison = (
        1
        if baseline_version is None
        else compare_versions(current_version, baseline_version)
    )
    has_bump = comparison > 0
    should_release = mode == "release" and has_bump
    failure_reason: str | None = None

    if mode == "release":
        if baseline_version is not None and comparison < 0:
            failure_reason = f"Current version {current_tag} is behind latest release {baseline_ref}."
        elif baseline_version is not None and bump_required and comparison <= 0:
            failure_reason = (
                "Changes require a semantic version bump, "
                f"but {current_tag} is not greater than {baseline_ref}."
            )
    else:
        if baseline_version is not None and bump_required and comparison <= 0:
            failure_reason = (
                "Changes require a semantic version bump compared with "
                f"{baseline_ref} version v{baseline_version}, "
                f"but current version is {current_tag}."
            )

    return PolicyResult(
        mode=mode,
        current_version=current_version,
        current_tag=current_tag,
        baseline_ref=baseline_ref,
        baseline_version=baseline_version,
        requires_version_bump=bump_required,
        has_version_bump=has_bump,
        should_release=should_release,
        relevant_pyproject_changed=relevant_change,
        unknown_paths=unknown_paths,
        failure_reason=failure_reason,
    )


def run_git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def fetch_default_branch(default_branch: str) -> None:
    subprocess.run(
        ["git", "fetch", "--force", "origin", default_branch],
        check=True,
        capture_output=True,
        text=True,
    )


def fetch_tags() -> None:
    subprocess.run(
        ["git", "fetch", "--force", "--tags", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )


def get_latest_tag() -> str | None:
    tags_output = run_git("tag", "--list", "v*")
    tags = [line.strip() for line in tags_output.splitlines() if line.strip()]
    valid_tags = filter_semver_tags(tags)
    if not valid_tags:
        return None
    return valid_tags[-1]


def get_merge_base(default_branch: str) -> str:
    return run_git("merge-base", "HEAD", f"origin/{default_branch}")


def get_changed_files_since_ref(ref: str) -> list[str]:
    output = run_git(
        "diff",
        "--name-only",
        "--diff-filter=ACDMRTUXB",
        f"{ref}..HEAD",
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def get_changed_files_since_tag(latest_tag: str | None) -> list[str]:
    if latest_tag is None:
        output = run_git("ls-files")
    else:
        output = run_git(
            "diff",
            "--name-only",
            "--diff-filter=ACDMRTUXB",
            f"{latest_tag}...HEAD",
        )
    return [line.strip() for line in output.splitlines() if line.strip()]


def load_pyproject(path: Path) -> dict[str, Any]:
    with path.open("rb") as file_obj:
        return tomllib.load(file_obj)


def load_pyproject_from_ref(ref: str | None, repo_root: Path) -> dict[str, Any] | None:
    if ref is None:
        return None

    result = subprocess.run(
        ["git", "show", f"{ref}:pyproject.toml"],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None
    return tomllib.loads(result.stdout)


def write_github_outputs(result: PolicyResult) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return

    outputs = {
        "current_version": result.current_version,
        "current_tag": result.current_tag,
        "baseline_ref": result.baseline_ref,
        "requires_version_bump": str(result.requires_version_bump).lower(),
        "has_version_bump": str(result.has_version_bump).lower(),
        "relevant_pyproject_changed": str(result.relevant_pyproject_changed).lower(),
        "should_release": str(result.should_release).lower(),
    }

    with Path(output_path).open("a", encoding="utf-8") as file_obj:
        for key, value in outputs.items():
            file_obj.write(f"{key}={value}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("feature-branch", "release"),
        required=True,
        help="Execution mode for workflow messaging.",
    )
    parser.add_argument(
        "--default-branch",
        default="main",
        help="Default branch name used for feature-branch comparisons.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    current_pyproject = load_pyproject(repo_root / "pyproject.toml")

    if args.mode == "feature-branch":
        fetch_default_branch(args.default_branch)
        baseline_ref = get_merge_base(args.default_branch)
        changed_files = get_changed_files_since_ref(baseline_ref)
        baseline_pyproject = load_pyproject_from_ref(baseline_ref, repo_root)
        baseline_version = (
            None
            if baseline_pyproject is None
            else str(baseline_pyproject["project"]["version"])
        )
        baseline_label = f"origin/{args.default_branch}"
    else:
        fetch_tags()
        latest_tag = get_latest_tag()
        changed_files = get_changed_files_since_tag(latest_tag)
        baseline_pyproject = load_pyproject_from_ref(latest_tag, repo_root)
        baseline_ref = latest_tag or "initial repository state"
        baseline_version = latest_tag[1:] if latest_tag is not None else None
        baseline_label = baseline_ref

    result = evaluate_policy(
        mode=args.mode,
        changed_files=changed_files,
        current_pyproject=current_pyproject,
        baseline_pyproject=baseline_pyproject,
        baseline_ref=baseline_label,
        baseline_version=baseline_version,
    )
    write_github_outputs(result)

    print(f"Version policy check ({args.mode})")
    print(f"  baseline: {result.baseline_ref}")
    print(f"  current tag: {result.current_tag}")
    print(f"  requires bump: {str(result.requires_version_bump).lower()}")
    print(f"  should release: {str(result.should_release).lower()}")

    if result.unknown_paths:
        print("  unknown paths conservatively treated as release-relevant:")
        for path in result.unknown_paths:
            print(f"    - {path}")

    if result.failure_reason:
        print(result.failure_reason, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
