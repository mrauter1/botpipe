"""Generic runtime config discovery."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None


PRIMARY_CONFIG_FILENAMES = ("autoloop.yaml", "autoloop.config")
LEGACY_CONFIG_FILENAMES = ("superloop.yaml", "superloop.config")
CONFIG_FILENAMES = (*PRIMARY_CONFIG_FILENAMES, *LEGACY_CONFIG_FILENAMES)
DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_PROVIDER_NAME = "codex"
SUPPORTED_PROVIDER_NAMES = frozenset({"codex", "claude"})
DEFAULT_CLAUDE_PERMISSION_STRATEGY = "inherit"
SUPPORTED_CLAUDE_PERMISSION_STRATEGIES = frozenset({"inherit", "allow_core_tools", "bypass"})
DEFAULT_MAX_STEPS = 100
DEFAULT_INTENT_MODE = "preserve"
SUPPORTED_INTENT_MODES = frozenset({"append", "preserve", "replace"})


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


@dataclass(frozen=True, slots=True)
class CodexProviderConfig:
    model: str = DEFAULT_CODEX_MODEL
    model_effort: str | None = None


@dataclass(frozen=True, slots=True)
class ClaudeProviderConfig:
    model: str | None = None
    effort: str | None = None
    permission_strategy: str = DEFAULT_CLAUDE_PERMISSION_STRATEGY


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    name: str = DEFAULT_PROVIDER_NAME
    codex: CodexProviderConfig = field(default_factory=CodexProviderConfig)
    claude: ClaudeProviderConfig = field(default_factory=ClaudeProviderConfig)


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    max_steps: int = DEFAULT_MAX_STEPS
    intent_mode: str = DEFAULT_INTENT_MODE


@dataclass(frozen=True, slots=True)
class ResolvedRuntimeConfig:
    provider: ProviderConfig
    runtime: RuntimeConfig


@dataclass(frozen=True, slots=True)
class CodexProviderConfigOverride:
    model: str | None = None
    model_effort: str | None = None


@dataclass(frozen=True, slots=True)
class ClaudeProviderConfigOverride:
    model: str | None = None
    effort: str | None = None
    permission_strategy: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderConfigOverride:
    name: str | None = None
    codex: CodexProviderConfigOverride = field(default_factory=CodexProviderConfigOverride)
    claude: ClaudeProviderConfigOverride = field(default_factory=ClaudeProviderConfigOverride)


@dataclass(frozen=True, slots=True)
class RuntimeConfigOverride:
    max_steps: int | None = None
    intent_mode: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeConfigLayer:
    provider: ProviderConfigOverride = field(default_factory=ProviderConfigOverride)
    runtime: RuntimeConfigOverride = field(default_factory=RuntimeConfigOverride)


def user_config_dir() -> Path:
    xdg_config_home = Path.home() / ".config"
    if "XDG_CONFIG_HOME" in __import__("os").environ:
        xdg_config_home = Path(__import__("os").environ["XDG_CONFIG_HOME"]).expanduser()
    return xdg_config_home / "autoloop"


def discover_config_file(directory: Path) -> Path | None:
    matches = [directory / filename for filename in CONFIG_FILENAMES if (directory / filename).is_file()]
    if len(matches) > 1:
        raise ConfigError(
            f"Found multiple configuration files in {directory}: {', '.join(path.name for path in matches)}. Keep only one."
        )
    return matches[0] if matches else None


def load_runtime_config_file(path: Path) -> object:
    if yaml is None:
        raise ConfigError(f"{path} cannot be loaded without PyYAML installed.")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - parser-specific details
        raise ConfigError(f"{path} could not be parsed as YAML: {exc}") from exc


def parse_runtime_config(payload: object, source: Path) -> RuntimeConfigLayer:
    if payload is None:
        return RuntimeConfigLayer()
    if not isinstance(payload, dict):
        raise ConfigError(f"{source}: configuration must be a YAML mapping.")

    provider_payload = payload.get("provider") or {}
    runtime_payload = payload.get("runtime") or {}
    if not isinstance(provider_payload, dict):
        raise ConfigError(f"{source}: provider must be a mapping when provided.")
    if not isinstance(runtime_payload, dict):
        raise ConfigError(f"{source}: runtime must be a mapping when provided.")

    _reject_unknown_keys(source, "provider", provider_payload, {"name", "model", "model_effort", "codex", "claude"})
    _reject_unknown_keys(
        source,
        "runtime",
        runtime_payload,
        {
            "max_steps",
            "intent_mode",
        },
    )

    codex_payload = provider_payload.get("codex") or {}
    claude_payload = provider_payload.get("claude") or {}
    if not isinstance(codex_payload, dict):
        raise ConfigError(f"{source}: provider.codex must be a mapping when provided.")
    if not isinstance(claude_payload, dict):
        raise ConfigError(f"{source}: provider.claude must be a mapping when provided.")

    provider = ProviderConfigOverride(
        name=_parse_provider_name(provider_payload.get("name"), "provider.name", source),
        codex=CodexProviderConfigOverride(
            model=_optional_string(provider_payload.get("model"), "provider.model", source)
            or _optional_string(codex_payload.get("model"), "provider.codex.model", source),
            model_effort=_optional_string(provider_payload.get("model_effort"), "provider.model_effort", source)
            or _optional_string(codex_payload.get("model_effort"), "provider.codex.model_effort", source),
        ),
        claude=ClaudeProviderConfigOverride(
            model=_optional_string(claude_payload.get("model"), "provider.claude.model", source),
            effort=_optional_string(claude_payload.get("effort"), "provider.claude.effort", source),
            permission_strategy=_optional_permission_strategy(
                claude_payload.get("permission_strategy"),
                "provider.claude.permission_strategy",
                source,
            ),
        ),
    )
    runtime = RuntimeConfigOverride(
        max_steps=_optional_positive_int(runtime_payload.get("max_steps"), "runtime.max_steps", source),
        intent_mode=_optional_intent_mode(runtime_payload.get("intent_mode"), "runtime.intent_mode", source),
    )
    return RuntimeConfigLayer(provider=provider, runtime=runtime)


def resolve_runtime_config(root: Path, args: argparse.Namespace) -> ResolvedRuntimeConfig:
    global_config_path = discover_config_file(user_config_dir())
    local_config_path = discover_config_file(root)

    global_layer = (
        parse_runtime_config(load_runtime_config_file(global_config_path), global_config_path)
        if global_config_path is not None
        else RuntimeConfigLayer()
    )
    local_layer = (
        parse_runtime_config(load_runtime_config_file(local_config_path), local_config_path)
        if local_config_path is not None
        else RuntimeConfigLayer()
    )
    return ResolvedRuntimeConfig(
        provider=_merge_provider_config(global_layer.provider, local_layer.provider, args=args),
        runtime=_merge_runtime_config(global_layer.runtime, local_layer.runtime, args=args),
    )


def _merge_provider_config(
    *layers: ProviderConfigOverride,
    args: argparse.Namespace,
) -> ProviderConfig:
    name = DEFAULT_PROVIDER_NAME
    codex_model = DEFAULT_CODEX_MODEL
    codex_effort: str | None = None
    claude_model: str | None = None
    claude_effort: str | None = None
    claude_permission = DEFAULT_CLAUDE_PERMISSION_STRATEGY

    for layer in layers:
        if layer.name is not None:
            name = layer.name
        if layer.codex.model is not None:
            codex_model = layer.codex.model
        if layer.codex.model_effort is not None:
            codex_effort = layer.codex.model_effort
        if layer.claude.model is not None:
            claude_model = layer.claude.model
        if layer.claude.effort is not None:
            claude_effort = layer.claude.effort
        if layer.claude.permission_strategy is not None:
            claude_permission = layer.claude.permission_strategy

    cli_model = getattr(args, "model", None)
    cli_model_effort = getattr(args, "model_effort", None)
    if isinstance(cli_model, str) and cli_model.strip():
        codex_model = cli_model.strip()
    if isinstance(cli_model_effort, str) and cli_model_effort.strip():
        codex_effort = cli_model_effort.strip()

    return ProviderConfig(
        name=name,
        codex=CodexProviderConfig(model=codex_model, model_effort=codex_effort),
        claude=ClaudeProviderConfig(
            model=claude_model,
            effort=claude_effort,
            permission_strategy=claude_permission,
        ),
    )


def _merge_runtime_config(
    *layers: RuntimeConfigOverride,
    args: argparse.Namespace,
) -> RuntimeConfig:
    max_steps = DEFAULT_MAX_STEPS
    intent_mode = DEFAULT_INTENT_MODE

    for layer in layers:
        if layer.max_steps is not None:
            max_steps = layer.max_steps
        if layer.intent_mode is not None:
            intent_mode = layer.intent_mode

    cli_max_steps = getattr(args, "max_steps", None)
    cli_intent_mode = getattr(args, "intent_mode", None)
    if cli_max_steps is not None:
        if isinstance(cli_max_steps, bool) or not isinstance(cli_max_steps, int) or cli_max_steps <= 0:
            raise ConfigError("CLI runtime max_steps must be a positive integer when provided.")
        max_steps = cli_max_steps
    if cli_intent_mode is not None:
        if not isinstance(cli_intent_mode, str) or cli_intent_mode not in SUPPORTED_INTENT_MODES:
            raise ConfigError(
                f"CLI runtime intent_mode must be one of: {', '.join(sorted(SUPPORTED_INTENT_MODES))}."
            )
        intent_mode = cli_intent_mode

    return RuntimeConfig(max_steps=max_steps, intent_mode=intent_mode)


def _reject_unknown_keys(source: Path, label: str, payload: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(key for key in payload if key not in allowed)
    if unknown:
        raise ConfigError(f"{source}: {label} contains unknown keys: {', '.join(unknown)}.")


def _optional_string(raw_value: object, label: str, source: Path) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ConfigError(f"{source}: {label} must be a non-empty string when provided.")
    return raw_value.strip()


def _optional_positive_int(raw_value: object, label: str, source: Path) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value <= 0:
        raise ConfigError(f"{source}: {label} must be a positive integer when provided.")
    return raw_value


def _parse_provider_name(raw_value: object, label: str, source: Path) -> str | None:
    value = _optional_string(raw_value, label, source)
    if value is None:
        return None
    if value not in SUPPORTED_PROVIDER_NAMES:
        raise ConfigError(f"{source}: {label} must be one of: {', '.join(sorted(SUPPORTED_PROVIDER_NAMES))}.")
    return value


def _optional_permission_strategy(raw_value: object, label: str, source: Path) -> str | None:
    value = _optional_string(raw_value, label, source)
    if value is None:
        return None
    if value not in SUPPORTED_CLAUDE_PERMISSION_STRATEGIES:
        raise ConfigError(
            f"{source}: {label} must be one of: {', '.join(sorted(SUPPORTED_CLAUDE_PERMISSION_STRATEGIES))}."
        )
    return value


def _optional_intent_mode(raw_value: object, label: str, source: Path) -> str | None:
    value = _optional_string(raw_value, label, source)
    if value is None:
        return None
    if value not in SUPPORTED_INTENT_MODES:
        raise ConfigError(f"{source}: {label} must be one of: {', '.join(sorted(SUPPORTED_INTENT_MODES))}.")
    return value
