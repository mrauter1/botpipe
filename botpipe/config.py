"""Small, typed configuration layer shared by the CLI and SDK callers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import tomllib

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

    file_provider, file_provider_config = _provider_values(
        payload.get("provider"), payload.get("provider_config")
    )
    resolved_provider = provider or file_provider or "codex"
    resolved_provider_config = _merge(file_provider_config, provider_config)
    resolved_policy = _mapping(payload.get("policy"), "policy")
    if policy is not None:
        resolved_policy = _merge(resolved_policy, policy)

    raw_state_dir = state_dir if state_dir is not None else payload.get("state_dir")
    resolved_state_dir = None
    if raw_state_dir is not None:
        resolved_state_dir = Path(str(raw_state_dir)).expanduser()
        if not resolved_state_dir.is_absolute():
            resolved_state_dir = root / resolved_state_dir
        resolved_state_dir = resolved_state_dir.resolve()

    resolved_max = int(
        max_operations
        if max_operations is not None
        else payload.get("max_operations", 1000)
    )
    resolved_timeout = float(
        timeout if timeout is not None else payload.get("timeout", 3600)
    )
    if resolved_max <= 0:
        raise ConfigError("max_operations must be greater than zero")
    if resolved_timeout <= 0:
        raise ConfigError("timeout must be greater than zero")
    return ClientConfig(
        workspace=root,
        provider=resolved_provider,
        state_dir=resolved_state_dir,
        policy=resolved_policy or None,
        provider_config=resolved_provider_config,
        max_operations=resolved_max,
        timeout=resolved_timeout,
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
