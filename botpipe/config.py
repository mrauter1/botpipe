"""Canonical project configuration shared by the SDK and command line.

Configuration is resolved from one source. ``botpipe.toml`` is the canonical
project file; ``[tool.botpipe]`` in ``pyproject.toml`` is the fallback.
``BOTPIPE_CONFIG`` or an explicit ``path=`` selects a different source.
Sources are never recursively merged.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

import tomllib
from urllib.parse import urlsplit

from .limits import RunLimits

CONFIG_FILENAMES = ("botpipe.toml", "botpipe.json", "botpipe.yaml", "botpipe.yml")
CONFIG_ENV_VAR = "BOTPIPE_CONFIG"


class ConfigurationError(ValueError):
    """Raised when Botpipe configuration is missing or malformed."""


_SECRET_KEYS = {
    "api_key",
    "password",
    "token",
    "authorization",
    "auth_token",
    "access_token",
    "refresh_token",
    "client_secret",
    "private_key",
}


def validate_non_secret_settings(value: Any, *, path: str = "settings") -> None:
    """Reject credentials from configuration that can enter durable records.

    Credentials belong in the environment, a referenced credential source, or
    an injected live adapter. This validator is deliberately limited to
    configuration/settings; application input and provider response data use
    their own contracts.
    """

    if isinstance(value, Mapping):
        for key, item in value.items():
            label = str(key)
            normalized = "".join(
                character.lower() if character.isalnum() else "_"
                for character in label
            ).strip("_")
            if normalized in _SECRET_KEYS or any(
                normalized.endswith(suffix)
                for suffix in (
                    "_api_key",
                    "_password",
                    "_token",
                    "_authorization",
                    "_private_key",
                    "_client_secret",
                )
            ):
                raise ConfigurationError(
                    f"{path}.{label} appears to contain a credential; use an "
                    "environment credential, credential-source reference, or "
                    "injected live adapter instead"
                )
            validate_non_secret_settings(item, path=f"{path}.{label}")
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            validate_non_secret_settings(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and "://" in value:
        try:
            parsed = urlsplit(value)
        except ValueError:
            return
        if parsed.username is not None or parsed.password is not None:
            raise ConfigurationError(
                f"{path} contains URL user information; use an environment "
                "credential, credential-source reference, or injected live adapter instead"
            )


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    """The resolved, non-secret settings for one provider profile."""

    name: str
    profile: str | None = None
    model: str | None = None
    effort: str | None = None
    generate_allow_commands: tuple[tuple[str, ...], ...] = ()
    # None means the operation default (the workspace); () explicitly disables
    # local discovery.
    query_read_roots: tuple[Path, ...] | None = None
    options: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", _freeze_mapping(self.options))

    def provider_config(self) -> dict[str, Any]:
        """Return adapter settings in the mutable form accepted by runtimes."""

        return _thaw_mapping(self.options)

    def provider_defaults(self) -> dict[str, Any]:
        """Return common operation defaults separately from adapter options."""

        values: dict[str, Any] = {}
        values["generate_allow_commands"] = [
            list(command) for command in self.generate_allow_commands
        ]
        if self.query_read_roots is not None:
            values["query_read_roots"] = [str(path) for path in self.query_read_roots]
        if self.model is not None:
            values["model"] = self.model
        if self.effort is not None:
            values["effort"] = self.effort
        if self.profile is not None:
            values["profile"] = self.profile
        return values


@dataclass(frozen=True, slots=True)
class ClientConfig:
    """An immutable, fully resolved application configuration."""

    workspace: Path
    state_dir: Path | None = None
    default_provider: str | None = None
    default_profile: str | None = None
    selection: ProviderSelection | None = None
    policy: Mapping[str, Any] | None = None
    max_operations: int = 1000
    timeout: float = 3600.0
    source: Path | None = None

    def __post_init__(self) -> None:
        if self.policy is not None:
            object.__setattr__(self, "policy", _freeze_mapping(self.policy))

    def require_provider(self) -> ProviderSelection:
        if self.selection is None:
            raise ConfigurationError(
                "no default provider is configured; set default_provider in "
                "botpipe.toml, pass --provider, or construct an explicit provider"
            )
        return self.selection

    def client_kwargs(self) -> dict[str, Any]:
        """Return runtime arguments without inventing a provider default."""

        values: dict[str, Any] = {
            "workspace": self.workspace,
            "state_dir": self.state_dir,
            "policy": _thaw_mapping(self.policy),
            "max_operations": self.max_operations,
            "timeout": self.timeout,
            "provider": None,
            "provider_config": {},
            "provider_defaults": {},
        }
        if self.selection is not None:
            values["provider"] = self.selection.name
            values["provider_config"] = self.selection.provider_config()
            values["provider_defaults"] = self.selection.provider_defaults()
        return values


def discover_config(workspace: str | Path = ".") -> Path | None:
    """Choose one config source using the documented precedence."""

    root = Path(workspace).expanduser().resolve()
    environment = os.environ.get(CONFIG_ENV_VAR)
    if environment:
        path = Path(environment).expanduser()
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            raise ConfigurationError(f"{CONFIG_ENV_VAR} does not exist: {path}")
        return path.resolve()

    found = [root / name for name in CONFIG_FILENAMES if (root / name).is_file()]
    if len(found) > 1:
        names = ", ".join(path.name for path in found)
        raise ConfigurationError(f"multiple Botpipe config files found: {names}")
    if found:
        return found[0]

    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    payload = _read_toml(pyproject)
    tool = payload.get("tool", {})
    if isinstance(tool, Mapping) and isinstance(tool.get("botpipe"), Mapping):
        return pyproject
    return None


def load_config(
    workspace: str | Path = ".",
    *,
    path: str | Path | None = None,
    provider: str | None = None,
    profile: str | None = None,
    state_dir: str | Path | None = None,
    policy: Mapping[str, Any] | None = None,
    provider_config: Mapping[str, Any] | None = None,
    model: str | None = None,
    effort: str | None = None,
    generate_allow_commands: Sequence[Sequence[str]] | None = None,
    query_read_roots: Sequence[str | Path] | None = None,
    max_operations: int | None = None,
    timeout: float | None = None,
) -> ClientConfig:
    """Load one source and apply explicit application or CLI overrides.

    Collection and mapping overrides replace the configured value. They are
    never recursively merged.
    """

    root = Path(workspace).expanduser().resolve()
    source = _explicit_source(path, root) if path is not None else discover_config(root)
    payload = _load_source(source) if source is not None else {}
    allowed = {
        "default_provider",
        "default_profile",
        "state_dir",
        "policy",
        "providers",
        "max_operations",
        "timeout",
    }
    _reject_unknown(payload, allowed, "configuration")

    file_provider = _optional_name(payload.get("default_provider"), "default_provider")
    file_profile = _optional_name(payload.get("default_profile"), "default_profile")
    selected_name = _optional_name(provider, "provider") if provider is not None else file_provider
    selected_profile = (
        _optional_name(profile, "profile")
        if profile is not None
        else file_profile if selected_name == file_provider else None
    )
    if selected_name is None and selected_profile is not None:
        raise ConfigurationError("default_profile requires default_provider")

    providers = _mapping(payload.get("providers"), "providers")
    selection = None
    if selected_name is not None:
        selection = _selection(
            root,
            selected_name,
            selected_profile,
            providers,
            provider_config=provider_config,
            model=model,
            effort=effort,
            generate_allow_commands=generate_allow_commands,
            query_read_roots=query_read_roots,
        )
    elif any(
        value is not None
        for value in (
            provider_config,
            model,
            effort,
            generate_allow_commands,
            query_read_roots,
        )
    ):
        raise ConfigurationError("provider settings require a configured provider")

    resolved_policy = (
        _mapping(policy, "policy")
        if policy is not None
        else _mapping(payload.get("policy"), "policy")
    )
    # Model and effort use the same runtime Policy fields as direct SDK calls.
    if selection is not None:
        resolved_policy = dict(resolved_policy)
        if selection.model is not None and (model is not None or "model" not in resolved_policy):
            resolved_policy["model"] = selection.model
        if selection.effort is not None and (effort is not None or "effort" not in resolved_policy):
            resolved_policy["effort"] = selection.effort
        validate_non_secret_settings(selection.options, path="provider options")
    validate_non_secret_settings(resolved_policy, path="policy")
    resolved_state = _resolve_path(
        root, state_dir if state_dir is not None else payload.get("state_dir"), "state_dir"
    )
    try:
        limits = RunLimits(
            max_operations if max_operations is not None else payload.get("max_operations", 1000),
            timeout if timeout is not None else payload.get("timeout", 3600.0),
        )
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc

    return ClientConfig(
        workspace=root,
        state_dir=resolved_state,
        default_provider=selected_name,
        default_profile=selected_profile,
        selection=selection,
        policy=resolved_policy or None,
        max_operations=limits.max_operations,
        timeout=limits.timeout,
        source=source,
    )


def _selection(
    root: Path,
    name: str,
    profile: str | None,
    providers: Mapping[str, Any],
    **overrides: Any,
) -> ProviderSelection:
    data = _mapping(providers.get(name), f"providers.{name}")
    allowed = {
        "model",
        "effort",
        "generate_allow_commands",
        "query_read_roots",
        "options",
        "profiles",
    }
    _reject_unknown(data, allowed, f"providers.{name}")
    profiles = _mapping(data.pop("profiles", None), f"providers.{name}.profiles")
    if profile is not None:
        if profile not in profiles:
            raise ConfigurationError(
                f"profile {profile!r} is not defined for provider {name!r}"
            )
        profile_data = _mapping(profiles[profile], f"providers.{name}.profiles.{profile}")
        _reject_unknown(profile_data, allowed - {"profiles"}, f"providers.{name}.profiles.{profile}")
        data.update(profile_data)

    options = _mapping(data.get("options"), f"providers.{name}.options")
    if overrides["provider_config"] is not None:
        options = _mapping(overrides["provider_config"], "provider_config")
    selected_model = _optional_name(
        overrides["model"] if overrides["model"] is not None else data.get("model"), "model"
    )
    selected_effort = _optional_name(
        overrides["effort"] if overrides["effort"] is not None else data.get("effort"), "effort"
    )
    commands = _commands(
        overrides["generate_allow_commands"]
        if overrides["generate_allow_commands"] is not None
        else data.get("generate_allow_commands", ()),
        "generate_allow_commands",
    )
    roots_value = (
        overrides["query_read_roots"]
        if overrides["query_read_roots"] is not None
        else data.get("query_read_roots")
    )
    roots = None if roots_value is None else _read_roots(root, roots_value)
    return ProviderSelection(
        name=name,
        profile=profile,
        model=selected_model,
        effort=selected_effort,
        generate_allow_commands=commands,
        query_read_roots=roots,
        options=options,
    )


def _explicit_source(path: str | Path, root: Path) -> Path:
    source = Path(path).expanduser()
    if not source.is_absolute():
        source = root / source
    if not source.is_file():
        raise ConfigurationError(f"configuration file does not exist: {source}")
    return source.resolve()


def _load_source(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"could not parse {path}: {exc}") from exc
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (ImportError, OSError, ValueError) as exc:
            raise ConfigurationError(f"could not parse {path}: {exc}") from exc
    else:
        payload = _read_toml(path)
        if path.name == "pyproject.toml":
            tool = payload.get("tool", {})
            payload = tool.get("botpipe", {}) if isinstance(tool, Mapping) else {}
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ConfigurationError(f"{path}: configuration must be a mapping")
    return dict(payload)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"could not parse {path}: {exc}") from exc
    return payload


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{name} must be a mapping")
    return dict(value)


def _optional_name(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{name} must be a non-empty string")
    return value.strip()


def _commands(value: Any, name: str) -> tuple[tuple[str, ...], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigurationError(f"{name} must be an array of argv arrays")
    result: list[tuple[str, ...]] = []
    for command in value:
        if isinstance(command, (str, bytes)) or not isinstance(command, Sequence):
            raise ConfigurationError(f"{name} must contain argv arrays")
        argv = tuple(command)
        if not argv or any(not isinstance(item, str) or not item for item in argv):
            raise ConfigurationError(f"{name} commands must contain non-empty strings")
        result.append(argv)
    return tuple(result)


def _read_roots(root: Path, value: Any) -> tuple[Path, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigurationError("query_read_roots must be an array of paths")
    roots: list[Path] = []
    for item in value:
        path = _resolve_path(root, item, "query_read_roots")
        assert path is not None
        roots.append(path)
    return tuple(roots)


def _resolve_path(root: Path, value: Any, name: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, (str, os.PathLike)):
        raise ConfigurationError(f"{name} must contain paths")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigurationError(f"unknown {name} keys: {', '.join(unknown)}")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_thaw(item) for item in value]
    return value


def _thaw_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return {} if value is None else {str(key): _thaw(item) for key, item in value.items()}


__all__ = [
    "CONFIG_ENV_VAR",
    "CONFIG_FILENAMES",
    "ClientConfig",
    "ConfigurationError",
    "ProviderSelection",
    "discover_config",
    "load_config",
    "validate_non_secret_settings",
]
