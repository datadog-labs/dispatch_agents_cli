"""Shared utility functions for dispatch CLI."""

import ast
import copy
import os
import re
from collections.abc import Callable
from typing import Any

import requests
import tomlkit
import typer
import yaml
from dispatch_agents._internal.constants import DEFAULT_SYSTEM_PACKAGES
from dispatch_agents.models import DispatchConfig, ResourceConfig, VolumeConfig
from pydantic import ValidationError
from tomlkit.items import Item

from dispatch_cli.logger import get_logger

# URL constants for different contexts
LOCAL_ROUTER_PORT = int(os.getenv("LOCAL_ROUTER_PORT", "4000"))
LOCAL_ROUTER_URL = "http://localhost"
DISPATCH_API_BASE = os.getenv("DISPATCH_DEPLOY_URL", "https://dispatchagents.ai")
DISPATCH_DEPLOY_URL = DISPATCH_API_BASE + "/api/unstable"

DISPATCH_DIR = ".dispatch"
DISPATCH_YAML = "dispatch.yaml"
DISPATCH_LISTENER_MODULE = "__dispatch_listener__"
DISPATCH_LISTENER_FILE = f"{DISPATCH_LISTENER_MODULE}.py"

# LLM provider API keys managed by the Dispatch LLM gateway.
# When present in dispatch.yaml secrets, these serve as fallback credentials
# if the namespace has no platform-level LLM provider configured.
LLM_PROVIDER_KEY_NAMES = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "COHERE_API_KEY",
    "MISTRAL_API_KEY",
}
AGENT_DIR = "."

# The platform builds every agent on a single, backend-controlled
# base image. The Python version here is the runtime the agent's
# pyproject.toml `requires-python` must be compatible with.
#
# Keep in sync with backend/build_templates/build_config.json
# (default_python_version). If you bump Python here, bump there too.
DEFAULT_PYTHON_VERSION = "3.13"

# The base image the platform currently supports. `dispatch agent deploy`
# blocks any other value unless --force; omitting the field uses this default.
DEFAULT_BASE_IMAGE = "python:3.13-slim"

DISPATCH_REQUIREMENTS = [
    "grpcio",
    "protobuf",
    "pydantic",
    "tomlkit",
    "pyyaml",
    "aiohttp",
    "asyncio",
]
# Legacy constant for backwards compatibility - prefer get_sdk_dependency() function
SDK_DEPENDENCY = os.getenv("SDK_DEPENDENCY", "dispatch-agents")


def get_sdk_dependency() -> str:
    """Get the SDK dependency string for agent projects.

    Defaults to the published PyPI package so `dispatch agent init` does not
    send users through a GitHub install flow. An explicit `SDK_DEPENDENCY`
    environment override still wins for local development and testing.

    Returns:
        SDK dependency string for use with 'uv add'
    """
    # Check for environment override first
    if os.getenv("SDK_DEPENDENCY"):
        return os.getenv("SDK_DEPENDENCY", SDK_DEPENDENCY)

    return SDK_DEPENDENCY


INTERACTIVE_CONFIG_OPTIONS: dict[str, dict] = {
    "namespace": {
        "text": "Namespace for agent deployment (required - contact your org admin if it doesn't exist)",
        "default_from_context": True,  # Special flag to compute default from context
    },
    "entrypoint": {
        "text": "Entrypoint Python file (with agent handlers)",
        "default": "agent.py",
    },
    "system_packages": {
        "text": "Additional system packages (space-separated)",
        "default": "",
        "value_proc": lambda x: x.split() if isinstance(x, str) else x,
    },
}


def _to_builtin(value):
    if isinstance(value, Item):
        try:
            inner = value.unwrap()
        except AttributeError:
            inner = value.value
        if inner is value:
            return inner
        return _to_builtin(inner)
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_builtin(v) for v in value]
    return value


def read_pyproject(path: str) -> tomlkit.TOMLDocument | None:
    """Load pyproject.toml if present."""
    logger = get_logger()
    pyproject_path = os.path.join(path, "pyproject.toml")
    if not os.path.exists(pyproject_path):
        logger.warning("pyproject.toml not found.")
        raise typer.Exit(1)

    try:
        with open(pyproject_path, "rb") as fh:
            return tomlkit.load(fh)
    except Exception as exc:  # pragma: no cover - surface error to caller
        logger.error(f"Could not parse pyproject.toml: {exc}")
        raise typer.Exit(1)


def read_project_config(
    path: str, pyproject: tomlkit.TOMLDocument | None = None
) -> dict:
    """Read configuration from pyproject.toml [tool.dispatch] section."""
    config: dict[str, object] = {}
    document = pyproject or read_pyproject(path)
    if not document:
        return config

    dispatch_config = document.get("tool", {}).get("dispatch", {}) or {}
    # Valid keys are owned by the SDK's DispatchConfig model — the single source
    # of truth, so new config fields are accepted without a CLI-side list.
    allowed_keys = set(DispatchConfig.model_fields)
    unsupported = set(dispatch_config.keys()) - allowed_keys
    if unsupported:
        logger = get_logger()
        logger.warning(
            f"Unsupported keys in [tool.dispatch]: {', '.join(sorted(unsupported))}"
        )

    for key in allowed_keys:
        if key in dispatch_config:
            config[key] = _to_builtin(dispatch_config[key])

    return config


def _find_dispatch_yaml(path: str) -> str | None:
    """Return the path to the dispatch config file, or None if not found."""
    hidden = os.path.join(path, ".dispatch.yaml")
    if os.path.exists(hidden):
        raise RuntimeError(
            ".dispatch.yaml is no longer supported; rename it to dispatch.yaml"
        )
    candidate = os.path.join(path, DISPATCH_YAML)
    if os.path.exists(candidate):
        return candidate
    return None


def read_dispatch_yaml(path: str) -> dict:
    """Read configuration overrides from dispatch.yaml."""
    yaml_path = _find_dispatch_yaml(path)
    if yaml_path is None:
        return {}

    filename = os.path.basename(yaml_path)

    with open(yaml_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        raise typer.BadParameter(
            f"{filename} must contain a mapping, found {type(data).__name__}"
        )

    # Validate against the SDK schema (the single source of truth). DispatchConfig
    # has extra="forbid", so unknown keys and invalid values both raise here.
    try:
        DispatchConfig.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()
        )
        raise typer.BadParameter(f"Invalid {filename}: {details}") from exc

    return data


def save_dispatch_yaml(path: str, config: dict) -> None:
    """Persist configuration values to dispatch.yaml."""
    # Write to whichever file already exists; default to dispatch.yaml for new projects
    yaml_path = _find_dispatch_yaml(path) or os.path.join(path, DISPATCH_YAML)
    payload = _config_for_yaml(config)
    with open(yaml_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(
            payload,
            fh,
            allow_unicode=False,
            sort_keys=False,
            default_flow_style=False,
        )

    logger = get_logger()
    logger.debug(f"Saved configuration to {yaml_path}")


def _config_for_yaml(config: dict) -> dict:
    """Return a serializable subset of config for dispatch.yaml."""
    keys = DispatchConfig.model_fields
    always_include = {
        "namespace",
        "agent_name",
        "entrypoint",
        "base_image",
        "system_packages",
    }

    payload: dict[str, object] = {}
    for key in keys:
        value = config.get(key)
        if key in always_include:
            if value is not None:
                payload[key] = value
            continue

        if value is None:
            continue

        if isinstance(value, list | dict) and not value:
            continue

        payload[key] = value

    return payload


def prompt_for_missing_config(config: dict, assume_yes=False, path: str = ".") -> dict:
    """Prompt user for any missing interactive config options."""
    logger = get_logger()
    updated_config = copy.deepcopy(config)
    logger.info(
        "Configuration will be saved to dispatch.yaml; edit that file to adjust later."
    )

    for option_name, option_def in INTERACTIVE_CONFIG_OPTIONS.items():
        processor: Callable[[Any], Any] = option_def.get("value_proc", lambda x: x)  # type: ignore

        if updated_config.get(option_name) is not None:
            continue

        # Compute context-specific defaults
        default_value = option_def.get("default")
        if option_def.get("default_from_context"):
            if option_name == "namespace":
                # Use parent directory name as default namespace
                # Get the parent of the agent directory
                abs_path = os.path.abspath(path)
                parent_dir = os.path.basename(os.path.dirname(abs_path))
                default_value = parent_dir

        if assume_yes:
            value = default_value
        else:
            # Build prompt kwargs, excluding special keys
            prompt_kwargs = {
                k: v
                for k, v in option_def.items()
                if k not in ("value_proc", "default_from_context")
            }
            if default_value is not None:
                prompt_kwargs["default"] = default_value
            value = typer.prompt(**prompt_kwargs)  # type: ignore
        updated_config[option_name] = processor(value)

    return updated_config


def _coerce_string_list(value: object | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split()
    if isinstance(value, list):
        items = value
    else:
        try:
            items = list(value)  # type: ignore
        except TypeError as exc:  # pragma: no cover - defensive
            raise typer.BadParameter(
                f"Expected list-like value, received {value!r}"
            ) from exc
    return [str(item) for item in items if str(item)]


def _seed_system_packages(value: object | None) -> list[str]:
    """Seed DEFAULT_SYSTEM_PACKAGES for new projects; preserve existing values as-is."""
    if value is None:
        return list(DEFAULT_SYSTEM_PACKAGES)
    return _coerce_string_list(value)


def _coerce_dict(key, value: object | None) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    raise typer.BadParameter(
        f"{key} must be a mapping of name → path, received {type(value).__name__}"
    )


def _validate_env(env: dict[str, Any] | None) -> dict[str, str] | None:
    """Validate that all env values are strings.

    YAML parses unquoted ``false`` as bool, ``123`` as int, etc.
    Env vars must be strings — tell users to wrap values in quotes.
    """
    if not env:
        return None
    if not isinstance(env, dict):
        raise typer.BadParameter(
            f"env must be a mapping of name → value, received {type(env).__name__}"
        )
    non_string = {
        k: (type(v).__name__, v) for k, v in env.items() if not isinstance(v, str)
    }
    if non_string:
        examples = ", ".join(
            f'{k} (got {t}, use: {k}: "{v}")'
            for k, (t, v) in sorted(non_string.items())
        )
        raise typer.BadParameter(f"All env values must be strings. {examples}")
    return env


def _apply_default_values(
    config: dict, pyproject: tomlkit.TOMLDocument | None, project_path: str
) -> dict:
    updated = copy.deepcopy(config)

    # base_image is intentionally not prepopulated. Omitting it uses the
    # platform default; an unsupported value is rejected at deploy time.

    updated["system_packages"] = _seed_system_packages(updated.get("system_packages"))
    updated["local_dependencies"] = _coerce_dict(
        "local_dependencies", updated.get("local_dependencies")
    )
    # Validate env values are strings (YAML parses false/true/123 as non-strings)
    updated["env"] = _validate_env(updated.get("env"))

    # Secrets as list - no coercion needed, YAML gives us the right structure
    if updated.get("secrets") is None:
        updated["secrets"] = []

    # Handle volumes configuration
    updated["volumes"] = _coerce_volumes(updated.get("volumes"))

    # Handle resources configuration
    updated["resources"] = _coerce_resources(updated.get("resources"))

    updated["dependency_strategy"] = str(
        updated.get("dependency_strategy") or "auto"
    ).lower()
    updated["dependency_file"] = updated.get("dependency_file")

    if not updated.get("agent_name"):
        updated["agent_name"] = derive_agent_name(project_path, updated, pyproject)

    return updated


def _coerce_resources(resources: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate and normalize resources configuration.

    Validates the resource configuration using the ResourceConfig Pydantic model
    and ensures CPU/memory form a valid combination.

    Args:
        resources: Resource configuration dict with limits sub-object

    Returns:
        Validated resource dict with K8s-style strings, or None if not specified
    """
    if not resources:
        return None

    if not isinstance(resources, dict):
        raise typer.BadParameter(
            f"resources must be an object with limits, got: {type(resources).__name__}"
        )

    # Validate using Pydantic model (combination validation happens automatically)
    try:
        resource_config = ResourceConfig(**resources)

        # Return only non-None values (keep K8s-style strings)
        if not resource_config.limits:
            return None

        limits_dict: dict[str, str] = {}
        if resource_config.limits.cpu is not None:
            limits_dict["cpu"] = resource_config.limits.cpu
        if resource_config.limits.memory is not None:
            limits_dict["memory"] = resource_config.limits.memory

        return {"limits": limits_dict} if limits_dict else None
    except ValueError as e:
        raise typer.BadParameter(f"resources validation error: {e}")


def _coerce_volumes(volumes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Validate and normalize volumes configuration.

    Validates each volume using the VolumeConfig Pydantic model.

    Args:
        volumes: List of volume configuration dicts

    Returns:
        Validated list of volume dicts
    """
    if not volumes:
        return []

    if not isinstance(volumes, list):
        raise typer.BadParameter(
            f"volumes must be a list of volume configurations, got: {type(volumes).__name__}"
        )

    # Validate each volume using Pydantic model
    validated_volumes: list[dict[str, Any]] = []
    for i, vol in enumerate(volumes):
        if not isinstance(vol, dict):
            raise typer.BadParameter(
                f"volumes[{i}] must be an object with name, mountPath, and mode"
            )

        # Validate required fields
        if "name" not in vol:
            raise typer.BadParameter(f"volumes[{i}] is missing required field 'name'")
        if "mountPath" not in vol:
            raise typer.BadParameter(
                f"volumes[{i}] is missing required field 'mountPath'"
            )
        if "mode" not in vol:
            raise typer.BadParameter(f"volumes[{i}] is missing required field 'mode'")

        # Validate using Pydantic model
        try:
            volume_config = VolumeConfig(**vol)
            validated_volumes.append(
                {
                    "name": volume_config.name,
                    "mountPath": volume_config.mount_path,
                    "mode": volume_config.mode.value,
                }
            )
        except Exception as e:
            raise typer.BadParameter(f"volumes[{i}] validation error: {e}")

    return validated_volumes


def load_dispatch_config(path: str, apply_defaults: bool = True) -> dict:
    """Load dispatch configuration, merging defaults, pyproject, and dispatch.yaml."""
    pyproject = read_pyproject(path)
    config = {**read_project_config(path, pyproject), **read_dispatch_yaml(path)}

    if apply_defaults:
        return _apply_default_values(config, pyproject, path)

    # Minimal normalization for callers that want raw values
    if config.get("system_packages") is not None:
        config["system_packages"] = _coerce_string_list(config["system_packages"])
    if config.get("local_dependencies") is None:
        config["local_dependencies"] = {}
    return config


def configure_dispatch_project(path: str, assume_yes=False) -> dict[str, Any]:
    """Interactive configuration flow used by `dispatch agent init`."""
    pyproject = read_pyproject(path)
    config = {**read_project_config(path, pyproject), **read_dispatch_yaml(path)}

    config = prompt_for_missing_config(config, assume_yes, path)
    config = _apply_default_values(config, pyproject, path)
    save_dispatch_yaml(path, config)
    return config


def has_python_reqs(path: str, warn=True) -> bool:
    """Validate that the path looks like a Python project we can work with."""

    pyproject_exists = os.path.exists(os.path.join(path, "pyproject.toml"))
    #  requirements_exists = os.path.exists(os.path.join(path, "requirements.txt"))

    if not pyproject_exists:  # or requirements_exists):
        if warn:
            logger = get_logger()
            logger.warning(
                "Could not find pyproject.toml or requirements.txt. Assuming no extra python dependencies."
            )
            logger.info("Tip: Use 'uv init --bare' to create pyproject.toml easily.")
        return False
    return True


def _read_dotenv_keys(abs_path: str) -> set[str]:
    """Return variable names defined in the .env file at abs_path.

    Returns an empty set if the file doesn't exist.
    """
    dotenv_path = os.path.join(abs_path, ".env")
    if not os.path.exists(dotenv_path):
        return set()
    keys: set[str] = set()
    with open(dotenv_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                keys.add(line.split("=", 1)[0].strip())
    return keys


def check_dotenv_has_all_secrets(path, config) -> None:
    """Warn if secret defined in dispatch.yaml is not set in .env"""
    logger = get_logger()
    secrets = config.get("secrets") or []
    if not secrets:
        return
    existing_env_vars = _read_dotenv_keys(path)

    for secret in secrets:
        secret_var = secret["name"]
        # LLM keys are injected by the proxy — don't require them in .env
        if secret_var in LLM_PROVIDER_KEY_NAMES:
            continue
        if secret_var not in existing_env_vars:
            logger.warning(
                f"Secret environment variable '{secret_var}' is defined in dispatch.yaml but not set in .env, please set it in order to use it for local testing."
            )


def _add_secrets_to_yaml(path: str, config: dict, secret_names: list[str]) -> None:
    """Append secret entries to the dispatch.yaml file."""
    yaml_path = _find_dispatch_yaml(path) or os.path.join(path, DISPATCH_YAML)
    with open(yaml_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    agent_name = config.get("agent_name", data.get("agent_name", "shared"))
    secrets_list = data.get("secrets") or []
    existing_names = {s["name"] for s in secrets_list}

    for var in secret_names:
        if var not in existing_names:
            secrets_list.append(
                {"name": var, "secret_id": f"{agent_name}/{var.lower()}"}
            )

    data["secrets"] = secrets_list
    with open(yaml_path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)


def get_unsupported_base_image(config: dict) -> str | None:
    """Return the configured base_image if it isn't a currently supported value.

    Omitting the field or setting it to ``DEFAULT_BASE_IMAGE`` is supported;
    any other value is returned so the caller can block. Returns ``None`` when
    the value is supported.
    """
    base_image = config.get("base_image")
    if base_image and base_image != DEFAULT_BASE_IMAGE:
        return str(base_image)
    return None


def check_env_secrets_not_in_config(path: str, config: dict) -> list[str]:
    """Check if .env contains secrets that are not configured in dispatch.yaml.

    This helps catch cases where developers add secrets to .env for local testing
    but forget to add them to dispatch.yaml, meaning they won't be available
    in production.

    LLM provider keys are excluded — those are managed by the LLM gateway.

    Returns:
        List of secret variable names found in .env but not in dispatch.yaml.
        Empty list if all secrets are configured.
    """
    logger = get_logger()
    configured_secrets = {s["name"] for s in (config.get("secrets") or [])}
    env_vars = _read_dotenv_keys(path)

    # LLM keys are managed by the gateway — don't flag them as missing
    missing_secrets = sorted(env_vars - configured_secrets - LLM_PROVIDER_KEY_NAMES)
    skipped_llm_keys = sorted(env_vars & LLM_PROVIDER_KEY_NAMES - configured_secrets)

    if skipped_llm_keys:
        logger.info(
            f"Skipping LLM keys ({', '.join(skipped_llm_keys)}) — "
            "managed by the LLM gateway. Use `dispatch llm setup` to configure."
        )

    if missing_secrets:
        logger.warning(
            f"Found {len(missing_secrets)} secret(s) in .env "
            "not configured in dispatch.yaml:"
        )
        for var in missing_secrets:
            logger.info(f"  - {var}")
        logger.info("")
        logger.info("These secrets will NOT be available in production.")

        # Build the full yaml snippet for all missing secrets
        agent_name = config.get("agent_name", "shared")
        yaml_lines = "secrets:"
        for var in missing_secrets:
            yaml_lines += (
                f'\n  - name: "{var}"\n    secret_id: "{agent_name}/{var.lower()}"'
            )

        # Offer to add them automatically
        if typer.confirm("Add these secrets to dispatch.yaml?", default=True):
            _add_secrets_to_yaml(path, config, missing_secrets)
            logger.success("Added secrets to dispatch.yaml.")
            missing_secrets = []  # no longer missing
        else:
            logger.info("To add them manually, use this format:")
            logger.info("")
            logger.code(yaml_lines, "yaml")

    return missing_secrets


# ---------------------------------------------------------------------------
# Dev-mode warnings: LLM key detection, MCP import scanning, secrets checks
# ---------------------------------------------------------------------------

# Package names in pyproject.toml that indicate direct LLM API usage.
# Normalized to lowercase with hyphens — matched after stripping version/extras.
_LLM_INDICATOR_PACKAGES = frozenset(
    {
        "openai-agents",
        "claude-agent-sdk",
        "anthropic",
        "openai",
        "google-generativeai",
        "langchain",
        "langchain-openai",
        "langchain-anthropic",
        "langchain-google-genai",
    }
)

# Maps a detected package to the router provider name it implies.
# Packages not in this map (e.g. bare "langchain") don't imply a specific provider.
_PACKAGE_TO_PROVIDER: dict[str, str] = {
    "openai": "openai",
    "openai-agents": "openai",
    "langchain-openai": "openai",
    "anthropic": "anthropic",
    "claude-agent-sdk": "anthropic",
    "langchain-anthropic": "anthropic",
    "google-generativeai": "google",
    "langchain-google-genai": "google",
}


def _collect_missing_dotenv_secrets(abs_path: str, config: dict) -> list[str]:
    """Return secret names declared in dispatch.yaml but absent from .env and os.environ."""
    secrets = config.get("secrets") or []
    if not secrets:
        return []

    # Collect names present in the environment (covers CI injection and shell exports)
    existing: set[str] = set(os.environ.keys()) | _read_dotenv_keys(abs_path)

    missing = []
    for s in secrets:
        if not isinstance(s, dict):
            # Bare string entries (e.g. `secrets: ["MY_SECRET"]`) are invalid config;
            # flag them rather than silently skipping so the user sees an actionable warning.
            name = str(s).strip()
            if name and name not in LLM_PROVIDER_KEY_NAMES and name not in existing:
                missing.append(name)
            continue
        name = str(s.get("name") or "")
        if name and name not in LLM_PROVIDER_KEY_NAMES and name not in existing:
            missing.append(name)
    return missing


def collect_mcp_import_files(abs_path: str) -> list[str]:
    """Return relative paths of source files that import get_mcp_servers from contrib."""
    matches: list[str] = []
    for root, dirs, files in os.walk(abs_path):
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d not in ("__pycache__", ".venv", "node_modules")
        ]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            try:
                content = open(fpath, encoding="utf-8", errors="ignore").read()
                tree = ast.parse(content, filename=fpath)
            except (OSError, SyntaxError) as e:
                get_logger().debug(f"Skipping unreadable file {fpath}: {e}")
                continue
            if any(
                isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("dispatch_agents.contrib.")
                and any(alias.name == "get_mcp_servers" for alias in node.names)
                for node in ast.walk(tree)
            ):
                matches.append(os.path.relpath(fpath, abs_path))
    return matches


def _collect_llm_packages(abs_path: str) -> list[str]:
    """Return LLM-indicator package names found in pyproject.toml dependencies."""

    pyproject_path = os.path.join(abs_path, "pyproject.toml")
    if not os.path.exists(pyproject_path):
        return []

    try:
        with open(pyproject_path, "rb") as fh:
            doc = tomlkit.load(fh)

        project = doc.get("project") or {}
        deps_raw: list = list(project.get("dependencies") or [])
        for group in (project.get("optional-dependencies") or {}).values():
            deps_raw.extend(group or [])

        found: list[str] = []
        for dep in deps_raw:
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", str(dep))
            if m:
                normalized = m.group(1).lower().replace("_", "-")
                if normalized in _LLM_INDICATOR_PACKAGES:
                    found.append(normalized)
        return found
    except Exception as e:
        get_logger().debug(f"LLM package detection skipped: {type(e).__name__}: {e}")
        return []


def _check_llm_keys_via_router(router_url: str) -> list[str]:
    """Return provider names that have no key configured in the router.

    Queries the router's LLM config endpoint, which has authoritative visibility
    into keys stored via Keychain, environment variables, or the local UI —
    without loading any key material into the current process.
    """
    resp = requests.get(f"{router_url}/api/unstable/llm-config/local", timeout=3)
    resp.raise_for_status()
    data = resp.json()
    return [
        p["provider"]
        for p in data.get("providers", [])
        if not p.get("configured", False)
    ]


def _make_warning(
    warning_type: str, title: str, description: str, items: list[str]
) -> dict:
    """Build a structured dev-mode warning dict for the local UI."""
    return {
        "type": warning_type,
        "severity": "warning",
        "title": title,
        "description": description,
        "items": items,
    }


def _secret_warnings(abs_path: str, config: dict) -> list[dict]:
    """Return a warning if any dispatch.yaml secrets are missing from the local env."""
    missing = _collect_missing_dotenv_secrets(abs_path, config)
    if not missing:
        return []
    return [
        _make_warning(
            "missing_secret",
            "Missing local secrets",
            f"{len(missing)} secret(s) declared in dispatch.yaml "
            "are not set in your .env file. The agent may crash when "
            "accessing these secrets locally.",
            missing,
        )
    ]


def _mcp_warnings(config: dict) -> list[dict]:
    """Return a warning if the agent declares MCP servers (unavailable in local dev)."""
    mcp_servers = config.get("mcp_servers") or []
    if not mcp_servers:
        return []
    server_names = [
        s.get("server", str(s)) if isinstance(s, dict) else str(s) for s in mcp_servers
    ]
    return [
        _make_warning(
            "mcp_unavailable",
            "MCP servers not available locally",
            "This agent uses MCP servers which are only available when deployed. "
            "MCP tool calls will be skipped in local dev mode.",
            server_names,
        )
    ]


def _llm_key_warnings(abs_path: str, router_url: str | None) -> list[dict]:
    """Return a warning if the agent uses LLM libraries whose provider keys are missing."""
    llm_packages = _collect_llm_packages(abs_path)
    if not llm_packages:
        return []

    try:
        if router_url:
            # Preferred: ask the router, which can see Keychain-stored keys and
            # keys set via the local UI — without leaking secrets into this process.
            unconfigured = _check_llm_keys_via_router(router_url)
        else:
            from dispatch_cli.router.local_llm import get_configured_providers

            configured = get_configured_providers()
            unconfigured = [p for p, ok in configured.items() if not ok]

        # Narrow to providers the detected packages actually imply so we
        # don't flag openai when the agent only depends on anthropic.
        suggested_providers = {
            _PACKAGE_TO_PROVIDER[pkg]
            for pkg in llm_packages
            if pkg in _PACKAGE_TO_PROVIDER
        }
        relevant_unconfigured = (
            [p for p in unconfigured if p in suggested_providers]
            if suggested_providers
            else unconfigured
        )

        if not relevant_unconfigured:
            return []
        return [
            _make_warning(
                "llm_keys_missing",
                "LLM provider keys not fully configured",
                "This agent uses LLM libraries. The following providers "
                "have no API key configured locally — if the agent calls "
                "one of them it will crash. "
                "Run `dispatch llm local <provider>` to configure keys.",
                relevant_unconfigured,
            )
        ]
    except Exception as e:
        # Non-fatal — skip LLM key check if router is unreachable or returns
        # an unexpected shape. Logged at debug so it's discoverable without
        # spamming the console in the common case.
        get_logger().debug(f"LLM key check skipped: {type(e).__name__}: {e}")
        return []


def collect_agent_warnings(
    abs_path: str, config: dict, router_url: str | None = None
) -> list[dict]:
    """Analyze an agent project and return structured warnings for the local UI.

    Called at 'dispatch agent dev' startup and sent to the router so the
    Warnings tab in the local UI is populated immediately on load.
    """
    return [
        *_secret_warnings(abs_path, config),
        *_mcp_warnings(config),
        *_llm_key_warnings(abs_path, router_url),
    ]


def validate_dispatch_project(path: str) -> bool:
    """Validate that dispatch project has been initialized."""
    logger = get_logger()
    if not os.path.isdir(path):
        logger.error(f"{path} is not a directory.")
        return False

    has_python_reqs(path, warn=True)

    dispatch_dir = os.path.join(path, DISPATCH_DIR)
    listener_path = os.path.join(dispatch_dir, DISPATCH_LISTENER_FILE)

    for check_path in [dispatch_dir, listener_path]:
        if not os.path.exists(check_path):
            logger.error(
                f"{os.path.relpath(check_path, path)} not found. "
                "Run 'dispatch agent init' to regenerate project assets."
            )
            return False

    # Check for dispatch config file
    has_visible = os.path.exists(os.path.join(path, DISPATCH_YAML))
    has_hidden = os.path.exists(os.path.join(path, ".dispatch.yaml"))

    if has_hidden:
        logger.error(
            ".dispatch.yaml is no longer supported; rename it to dispatch.yaml"
        )
        return False

    if not has_visible:
        logger.error(
            f"{DISPATCH_YAML} not found. "
            "Run 'dispatch agent init' to regenerate project assets."
        )
        return False

    return True


def derive_agent_name(
    path: str,
    config: dict | None = None,
    pyproject: tomlkit.TOMLDocument | None = None,
) -> str:
    """Derive a stable agent name from config, pyproject, or directory name."""
    if config:
        candidate = config.get("agent_name")
        if candidate:
            return _slugify_name(candidate)

    document = pyproject or read_pyproject(path)
    if document:
        project_section = document.get("project", {})
        candidate = project_section.get("name")
        if candidate:
            return _slugify_name(candidate)

    return _slugify_name(os.path.basename(os.path.abspath(path)))


def _slugify_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", str(value).lower()).strip("-")
    return slug or "dispatch-agent"


def extract_local_deps_from_pyproject(project_path: str) -> dict[str, str | dict]:
    """Extract dependencies to bundle from pyproject.toml [tool.uv.sources].

    This function identifies dependencies that need to be bundled as wheels for remote builds.
    It extracts both local path dependencies and git dependencies from uv's source configuration.

    The mixed return type (str | dict) is intentional because different dependency types
    need different handling:
    - Path dependencies: Return the path string so we can call `uv build` on the directory
    - Git dependencies: Return the full source dict so we can clone the repo and build it

    Args:
        project_path: Path to the project directory containing pyproject.toml

    Returns:
        Dict mapping dependency name to source configuration:
        - For path deps: {"my-lib": "../../libs/my-lib"}
        - For git deps: {"other-lib": {"git": "https://...", "rev": "v1.0", "subdirectory": "pkg"}}

    Example pyproject.toml:
        [tool.uv.sources]
        my-local-lib = { path = "../../libs/my-local-lib" }
        private-repo = { git = "git@github.com/org/repo.git", subdirectory = "sdk", rev = "v1.2.3" }

    Example return value:
        {
            "my-local-lib": "../../libs/my-local-lib",
            "private-repo": {"git": "git@github.com/org/repo.git", "subdirectory": "sdk", "rev": "v1.2.3"}
        }

    Note:
        dispatch-agents and dispatch-cli dependencies are NOT included here - they're
        handled separately by the backend infrastructure to ensure version compatibility.
    """
    pyproject = read_pyproject(project_path)
    if not pyproject:
        return {}

    uv_sources = pyproject.get("tool", {}).get("uv", {}).get("sources", {})
    bundled_deps = {}

    for dep_name, source_config in uv_sources.items():
        if isinstance(source_config, dict):
            # Include path dependencies (local)
            if "path" in source_config:
                bundled_deps[dep_name] = source_config["path"]
            # Include git dependencies (need to be downloaded/built)
            elif "git" in source_config:
                bundled_deps[dep_name] = source_config

    return bundled_deps


def process_local_dependencies(config: dict, project_path: str) -> tuple[str, str, str]:
    """Process local path dependencies and return Docker COPY and RUN commands.

    Note: Only handles path dependencies. Git dependencies are handled differently
    in remote builds (downloaded as wheels).

    Returns:
        tuple: (copy_section, path_fix_section, install_section, filtered_requirements)
    """
    # Merge local_dependencies from config with those auto-detected from pyproject.toml
    config_deps = config.get("local_dependencies") or {}
    pyproject_deps = extract_local_deps_from_pyproject(project_path)

    # Config takes precedence over pyproject
    all_deps = {**pyproject_deps, **config_deps}

    # Filter to only path dependencies (strings), skip git dependencies (dicts)
    local_deps = {k: v for k, v in all_deps.items() if isinstance(v, str)}

    if not local_deps:
        return "", "", ""

    copy_commands: list[str] = []
    path_fix_commands: list[str] = []

    # Extract package names to filter out from shared requirements
    local_package_names = {name.replace("_", "-") for name in local_deps.keys()}
    local_package_names.update(local_deps.keys())

    filtered_requirements = []
    for req in DISPATCH_REQUIREMENTS:
        pkg_name = req.split("@")[0].split()[0].strip().strip('"').replace("_", "-")
        if pkg_name not in local_package_names:
            filtered_requirements.append(req)

    for dep_name, dep_path in local_deps.items():
        if not os.path.isabs(dep_path):
            abs_dep_path = os.path.join(project_path, dep_path)
        else:
            abs_dep_path = dep_path

        if not os.path.exists(abs_dep_path):
            logger = get_logger()
            logger.warning(f"Local dependency path does not exist: {abs_dep_path}")
            continue

        # Place local dependencies in a predictable location inside Docker
        # We'll put them in /deps/{dep_name} and update the pyproject.toml paths accordingly
        if os.path.isabs(dep_path):
            # For absolute paths, still use /deps location for consistency
            docker_path = f"/deps/{dep_name}"
        else:
            # For relative paths, place in /deps/{dep_name}
            docker_path = f"/deps/{dep_name}"

        copy_commands.append(f"COPY --from={dep_name} . {docker_path}")

        # Fix pyproject.toml and uv.lock to use the new Docker paths
        # This replaces the original path with our standardized /deps/{dep_name} location
        # Use sed to replace the path in both files
        # This handles formats like: dispatch-agents = { path = "../../sdk", editable = true }
        path_fix_commands.append(
            f'RUN sed -i \'s|path = "{dep_path}"|path = "{docker_path}"|g\' pyproject.toml'
        )

        # Fix uv.lock - update all possible path references
        # uv.lock can have paths in many different formats, so we need comprehensive replacement
        path_fix_commands.append(f"RUN sed -i 's|{dep_path}|{docker_path}|g' uv.lock")

    copy_section = "\n".join(copy_commands) if copy_commands else ""
    path_fix_section = "\n".join(path_fix_commands) if path_fix_commands else ""
    install_section = (
        ""  # No longer needed - uv sync will install from the copied paths
    )

    return copy_section, path_fix_section, install_section


def detect_dependency_strategy(
    path: str, _config: dict
) -> tuple[str, dict[str, object]]:
    """Auto-detect how to install project dependencies inside the container.

    Only supports pyproject.toml (with uv) or bundled wheels.
    requirements.txt is explicitly not supported.

    Args:
        path: Path to the agent project directory
        _config: Config dict (unused, kept for compatibility)
    """

    def _exists(relative: str) -> bool:
        return os.path.exists(os.path.join(path, relative))

    # Check for unsupported requirements.txt files first
    for candidate in [
        "requirements.txt",
        "requirements-prod.txt",
        "requirements-dev.txt",
    ]:
        if _exists(candidate):
            raise typer.BadParameter(
                f"Found {candidate}, but requirements.txt is no longer supported.\n"
                f"Please migrate to pyproject.toml using:\n"
                f"  uv init --name <your-agent-name>\n"
                f"  uv add $(cat {candidate})\n"
                f"Then remove {candidate}."
            )

    # Bundled strategy (for remote builds where wheels are pre-built)
    if _exists("dependencies"):
        return "bundled", {}

    # Standard pyproject.toml strategy
    if _exists("pyproject.toml"):
        return "pyproject", {}

    raise typer.BadParameter(
        "Could not find pyproject.toml. "
        "Please create one using: uv init --name <your-agent-name>"
    )


def render_dependency_install_step(strategy: str, _details: dict[str, object]) -> str:
    """Render Dockerfile snippet that installs project dependencies.

    Args:
        strategy: The dependency strategy ("pyproject" or "bundled")
        _details: Strategy details dict (unused, kept for compatibility)
    """
    if strategy == "requirements":
        raise ValueError("requirements.txt strategy is no longer supported.")

    if strategy == "pyproject":
        return (
            "RUN --mount=type=cache,target=/root/.cache/uv \\\n"
            "    --mount=type=ssh \\\n"
            "    mkdir -p /root/.ssh && \\\n"
            "    ssh-keyscan github.com >> /root/.ssh/known_hosts && \\\n"
            "    uv sync --frozen"
        )

    if strategy == "bundled":
        return (
            "COPY dependencies/ /app/dependencies/\n"
            "# Install dependencies from PyPI and bundled wheels\n"
            "RUN --mount=type=cache,target=/root/.cache/uv \\\n"
            "    uv pip install --system \\\n"
            "    --find-links /app/dependencies \\\n"
            "    ."
        )

    raise ValueError(f"Unsupported dependency strategy '{strategy}'")
