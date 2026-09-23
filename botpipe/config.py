"""Small, typed configuration layer shared by the CLI and SDK callers."""

from __future__ import annotations

import json
import math
import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .limits import RunLimits

CONFIG_FILENAMES = ("botpipe.toml", ".botpipe.toml", "botpipe.json")


class ConfigError(ValueError):
    """Raised when configuration is malformed or contradictory."""


@dataclass(frozen=True, slots=True)
class ClientConfig:
    workspace: Path
    provider: str = "codex"
    state_dir: Path | None = None
    policy: dict[str, Any] | None = None
    provider_config: dict[str, Any] = field(default_factory=dict)
    max_operations: int = 1000
    timeout: float = 3600.0
    source: Path | None = None

    def client_kwargs(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "provider": self.provider,
            "state_dir": self.state_dir,
            "policy": self.policy,
            "provider_config": dict(self.provider_config),
            "max_operations": self.max_operations,
            "timeout": self.timeout,
        }


def discover_config(workspace: str | Path = ".") -> Path | None:
    root = Path(workspace).expanduser().resolve()
    explicit = os.environ.get("BOTPIPE_CONFIG")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError(f"BOTPIPE_CONFIG does not exist: {path}")
        return path.resolve()
    found = [root / name for name in CONFIG_FILENAMES if (root / name).is_file()]
    if len(found) > 1:
        names = ", ".join(path.name for path in found)
        raise ConfigError(f"multiple Botpipe config files found: {names}")
    if found:
        return found[0]
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"could not read {pyproject}: {exc}") from exc
        if isinstance(payload.get("tool", {}).get("botpipe"), Mapping):
            return pyproject
    return None


def load_config(
    workspace: str | Path = ".",
    *,
    path: str | Path | None = None,
    provider: str | None = None,
    state_dir: str | Path | None = None,
    policy: Mapping[str, Any] | None = None,
    provider_config: Mapping[str, Any] | None = None,
    max_operations: int | None = None,
    timeout: float | None = None,
) -> ClientConfig:
    """Resolve file configuration and explicit overrides into client arguments."""

    root = Path(workspace).expanduser().resolve()
    source = (
        Path(path).expanduser().resolve() if path is not None else discover_config(root)
    )
    payload: dict[str, Any] = {}
    if source is not None:
        if not source.is_file():
            raise ConfigError(f"configuration file does not exist: {source}")
        payload = _load_mapping(source)
    allowed = {
        "default_provider",
        "codex",
        "codex_path",
        "provider",
        "provider_config",
        "policy",
        "state_dir",
        "max_operations",
        "timeout",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ConfigError(f"unknown configuration keys: {', '.join(unknown)}")

    if "default_provider" in payload and payload["default_provider"] != "codex":
        raise ConfigError("default_provider must be 'codex' in Botpipe 2.0")
    file_provider, legacy_config = _provider_values(
        payload.get("provider"), payload.get("provider_config")
    )
    resolved_provider = (
        provider or payload.get("default_provider") or file_provider or "codex"
    )
    if resolved_provider != "codex":
        raise ConfigError("Botpipe 2.0 supports only the codex provider")
    file_provider_config = _merge(
        legacy_config, _mapping(payload.get("codex"), "codex")
    )
    if "codex_path" in payload:
        file_provider_config.setdefault("path", payload["codex_path"])
    resolved_provider_config = _merge(file_provider_config, provider_config)
    validate_codex_config(resolved_provider_config)
    executable = resolved_provider_config.get("path")
    if executable and ("/" in executable or "\\" in executable):
        executable_path = Path(executable).expanduser()
        if not executable_path.is_absolute():
            executable_path = (
                source.parent if source is not None else root
            ) / executable_path
        resolved_provider_config["path"] = str(executable_path.resolve())
    resolved_policy = _mapping(payload.get("policy"), "policy")
    if policy is not None:
        resolved_policy = _merge(resolved_policy, policy)
    from .policy import Policy

    try:
        resolved_policy = Policy.from_dict(resolved_policy).to_dict()
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc

    raw_state_dir = state_dir if state_dir is not None else payload.get("state_dir")
    resolved_state_dir = None
    if raw_state_dir is not None:
        resolved_state_dir = Path(str(raw_state_dir)).expanduser()
        if not resolved_state_dir.is_absolute():
            resolved_state_dir = root / resolved_state_dir
        resolved_state_dir = resolved_state_dir.resolve()

    try:
        limits = RunLimits(
            max_operations
            if max_operations is not None
            else payload.get("max_operations", 1000),
            timeout if timeout is not None else payload.get("timeout", 3600),
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    return ClientConfig(
        workspace=root,
        provider=resolved_provider,
        state_dir=resolved_state_dir,
        policy=resolved_policy or None,
        provider_config=resolved_provider_config,
        max_operations=limits.max_operations,
        timeout=limits.timeout,
        source=source,
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    try:
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover - optional convenience
                raise ConfigError(
                    "YAML config requires PyYAML; use TOML or JSON instead"
                ) from exc
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
            if path.name == "pyproject.toml":
                payload = payload.get("tool", {}).get("botpipe", {})
    except ConfigError:
        raise
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"could not parse {path}: {exc}") from exc
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ConfigError(f"{path}: configuration must be a mapping")
    return dict(payload)


def _provider_values(provider: Any, separate: Any) -> tuple[str | None, dict[str, Any]]:
    provider_config = _mapping(separate, "provider_config")
    if provider is None:
        return None, provider_config
    if isinstance(provider, str):
        return provider, provider_config
    if isinstance(provider, Mapping):
        data = dict(provider)
        name = data.pop("name", None)
        if name is not None and not isinstance(name, str):
            raise ConfigError("provider.name must be a string")
        return name, _merge(data, provider_config)
    raise ConfigError("provider must be a name or mapping")


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"{name} must be a mapping")
    return dict(value)


def _merge(
    base: Mapping[str, Any] | None, override: Mapping[str, Any] | None
) -> dict[str, Any]:
    result = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result


__all__ = [
    "CONFIG_FILENAMES",
    "ClientConfig",
    "ConfigError",
    "discover_config",
    "load_config",
]


_CODEX_FIELDS = frozenset(
    {
        "path",
        "model",
        "effort",
        "sandbox",
        "network",
        "interrupt_grace_seconds",
        "instructions",
        "tools",
        "timeout",
        "output_retries",
        "name",
        "settings",
    }
)
_SECRET_KEY = re.compile(
    r"(?:^|[_.-])(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret|credentials?|authorization|bearer|token)(?:$|[_.-])",
    re.IGNORECASE,
)


def validate_non_secret_settings(value: Any, path: str = "configuration") -> None:
    """Reject secret-bearing keys before durable configuration is written."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ConfigError(f"{path} keys must be strings")
            if _SECRET_KEY.search(key):
                raise ConfigError(
                    f"secret-looking setting is not durable configuration: {path}.{key}"
                )
            validate_non_secret_settings(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for item in value:
            validate_non_secret_settings(item, path)
    elif isinstance(value, str) and "://" in value:
        for part in re.findall(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s]+", value):
            try:
                parsed = urlsplit(part)
            except ValueError:
                continue
            if parsed.username is not None or parsed.password is not None:
                raise ConfigError(
                    f"credential-bearing URL is not durable configuration: {path}"
                )


def validate_codex_config(value: Mapping[str, Any]) -> None:
    unknown = value.keys() - _CODEX_FIELDS
    if unknown:
        raise ConfigError(
            f"unknown Codex configuration keys: {', '.join(sorted(unknown))}"
        )
    validate_non_secret_settings(value)
    for name in ("path", "model", "effort", "instructions", "name"):
        if name in value and (
            not isinstance(value[name], str) or not value[name].strip()
        ):
            raise ConfigError(f"codex.{name} must be a nonempty string")
    if "network" in value and type(value["network"]) is not bool:
        raise ConfigError("codex.network must be true or false")
    if "sandbox" in value and value["sandbox"] not in {
        "read-only",
        "workspace-write",
        "full-access",
    }:
        raise ConfigError(
            "codex.sandbox must be read-only, workspace-write or full-access"
        )
    for name in ("timeout", "interrupt_grace_seconds"):
        if name in value:
            number = value[name]
            allow_zero = name == "interrupt_grace_seconds"
            if (
                type(number) not in (int, float)
                or not math.isfinite(number)
                or number < 0
                or (number == 0 and not allow_zero)
            ):
                raise ConfigError(
                    f"codex.{name} must be a finite {'nonnegative' if allow_zero else 'positive'} number"
                )
    if "output_retries" in value and (
        type(value["output_retries"]) is not int or value["output_retries"] < 0
    ):
        raise ConfigError("codex.output_retries must be a nonnegative integer")
    if "tools" in value and (
        not isinstance(value["tools"], (list, tuple))
        or any(not isinstance(tool, str) or not tool for tool in value["tools"])
    ):
        raise ConfigError("codex.tools must be a list of tool names")
    settings = value.get("settings", {})
    if not isinstance(settings, Mapping):
        raise ConfigError("codex.settings must be a mapping")
    try:
        json.dumps(settings, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ConfigError("codex.settings must contain finite JSON values") from exc
