"""Generic runtime config discovery."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None


CONFIG_FILENAMES = ("autoloop.yaml", "autoloop.config")
DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_PROVIDER_NAME = "codex"
SUPPORTED_PROVIDER_NAMES = frozenset({"codex", "claude"})
DEFAULT_CLAUDE_PERMISSION_STRATEGY = "inherit"
SUPPORTED_CLAUDE_PERMISSION_STRATEGIES = frozenset({"inherit", "allow_core_tools", "bypass"})
DEFAULT_MAX_STEPS = 100
SUPPORTED_GIT_COMMIT_POLICIES = frozenset({"off", "run", "step"})
SUPPORTED_FAILURE_MODES = frozenset({"raise", "ignore"})


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


GitCommitPolicy = Literal["off", "run", "step"]
FailureMode = Literal["raise", "ignore"]


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
class GitTrackingRuntimeConfig:
    enabled: bool = True
    commit_policy: GitCommitPolicy = "step"
    failure_mode: FailureMode = "raise"


@dataclass(frozen=True, slots=True)
class TracingRuntimeConfig:
    enabled: bool = True
    path: str = "trace.jsonl"
    failure_mode: FailureMode = "raise"
    include_state_snapshots: bool = True


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    max_steps: int = DEFAULT_MAX_STEPS
    git_tracking: GitTrackingRuntimeConfig = field(default_factory=GitTrackingRuntimeConfig)
    tracing: TracingRuntimeConfig = field(default_factory=TracingRuntimeConfig)


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
    model: str | None = None
    model_effort: str | None = None
    codex: CodexProviderConfigOverride = field(default_factory=CodexProviderConfigOverride)
    claude: ClaudeProviderConfigOverride = field(default_factory=ClaudeProviderConfigOverride)


@dataclass(frozen=True, slots=True)
class GitTrackingRuntimeConfigOverride:
    enabled: bool | None = None
    commit_policy: GitCommitPolicy | None = None
    failure_mode: FailureMode | None = None


@dataclass(frozen=True, slots=True)
class TracingRuntimeConfigOverride:
    enabled: bool | None = None
    path: str | None = None
    failure_mode: FailureMode | None = None
    include_state_snapshots: bool | None = None


@dataclass(frozen=True, slots=True)
class RuntimeConfigOverride:
    max_steps: int | None = None
    git_tracking: GitTrackingRuntimeConfigOverride = field(default_factory=GitTrackingRuntimeConfigOverride)
    tracing: TracingRuntimeConfigOverride = field(default_factory=TracingRuntimeConfigOverride)


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

    provider_payload = payload.get("provider")
    runtime_payload = payload.get("runtime")
    if provider_payload is None:
        provider_payload = {}
    if runtime_payload is None:
        runtime_payload = {}
    if not isinstance(provider_payload, dict):
        raise ConfigError(f"{source}: provider must be a mapping when provided.")
    if not isinstance(runtime_payload, dict):
        raise ConfigError(f"{source}: runtime must be a mapping when provided.")

    _reject_unknown_keys(source, "provider", provider_payload, {"name", "model", "model_effort", "codex", "claude"})
    _reject_unknown_keys(
        source,
        "runtime",
        runtime_payload,
        {"max_steps", "git_tracking", "tracing"},
    )

    codex_payload = provider_payload.get("codex")
    claude_payload = provider_payload.get("claude")
    git_tracking_payload = runtime_payload.get("git_tracking")
    tracing_payload = runtime_payload.get("tracing")
    if codex_payload is None:
        codex_payload = {}
    if claude_payload is None:
        claude_payload = {}
    if git_tracking_payload is None:
        git_tracking_payload = {}
    if tracing_payload is None:
        tracing_payload = {}
    if not isinstance(codex_payload, dict):
        raise ConfigError(f"{source}: provider.codex must be a mapping when provided.")
    if not isinstance(claude_payload, dict):
        raise ConfigError(f"{source}: provider.claude must be a mapping when provided.")
    if not isinstance(git_tracking_payload, dict):
        raise ConfigError(f"{source}: runtime.git_tracking must be a mapping when provided.")
    if not isinstance(tracing_payload, dict):
        raise ConfigError(f"{source}: runtime.tracing must be a mapping when provided.")

    _reject_unknown_keys(source, "runtime.git_tracking", git_tracking_payload, {"enabled", "commit_policy", "failure_mode"})
    _reject_unknown_keys(
        source,
        "runtime.tracing",
        tracing_payload,
        {"enabled", "path", "failure_mode", "include_state_snapshots"},
    )

    provider = ProviderConfigOverride(
        name=_parse_provider_name(provider_payload.get("name"), "provider.name", source),
        model=_optional_string(provider_payload.get("model"), "provider.model", source),
        model_effort=_optional_string(provider_payload.get("model_effort"), "provider.model_effort", source),
        codex=CodexProviderConfigOverride(
            model=_optional_string(codex_payload.get("model"), "provider.codex.model", source),
            model_effort=_optional_string(codex_payload.get("model_effort"), "provider.codex.model_effort", source),
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
        git_tracking=GitTrackingRuntimeConfigOverride(
            enabled=_optional_bool(git_tracking_payload.get("enabled"), "runtime.git_tracking.enabled", source),
            commit_policy=_optional_git_commit_policy(
                git_tracking_payload.get("commit_policy"),
                "runtime.git_tracking.commit_policy",
                source,
            ),
            failure_mode=_optional_failure_mode(
                git_tracking_payload.get("failure_mode"),
                "runtime.git_tracking.failure_mode",
                source,
            ),
        ),
        tracing=TracingRuntimeConfigOverride(
            enabled=_optional_bool(tracing_payload.get("enabled"), "runtime.tracing.enabled", source),
            path=_optional_string(tracing_payload.get("path"), "runtime.tracing.path", source),
            failure_mode=_optional_failure_mode(
                tracing_payload.get("failure_mode"),
                "runtime.tracing.failure_mode",
                source,
            ),
            include_state_snapshots=_optional_bool(
                tracing_payload.get("include_state_snapshots"),
                "runtime.tracing.include_state_snapshots",
                source,
            ),
        ),
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
    for layer in layers:
        if layer.name is not None:
            name = layer.name

    cli_provider = _optional_cli_provider_name(getattr(args, "provider", None))
    if cli_provider is not None:
        name = cli_provider

    codex_model = DEFAULT_CODEX_MODEL
    codex_effort: str | None = None
    claude_model: str | None = None
    claude_effort: str | None = None
    claude_permission = DEFAULT_CLAUDE_PERMISSION_STRATEGY

    for layer in layers:
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

        codex_model, codex_effort, claude_model, claude_effort = _apply_generic_provider_overrides(
            provider_name=name,
            model=layer.model,
            model_effort=layer.model_effort,
            codex_model=codex_model,
            codex_effort=codex_effort,
            claude_model=claude_model,
            claude_effort=claude_effort,
        )

    cli_model = getattr(args, "model", None)
    cli_model_effort = getattr(args, "model_effort", None)
    codex_model, codex_effort, claude_model, claude_effort = _apply_generic_provider_overrides(
        provider_name=name,
        model=cli_model.strip() if isinstance(cli_model, str) and cli_model.strip() else None,
        model_effort=cli_model_effort.strip()
        if isinstance(cli_model_effort, str) and cli_model_effort.strip()
        else None,
        codex_model=codex_model,
        codex_effort=codex_effort,
        claude_model=claude_model,
        claude_effort=claude_effort,
    )

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
    git_tracking_enabled = True
    git_tracking_commit_policy: GitCommitPolicy = "step"
    git_tracking_failure_mode: FailureMode = "raise"
    tracing_enabled = True
    tracing_path = "trace.jsonl"
    tracing_failure_mode: FailureMode = "raise"
    tracing_include_state_snapshots = True

    for layer in layers:
        if layer.max_steps is not None:
            max_steps = layer.max_steps
        if layer.git_tracking.enabled is not None:
            git_tracking_enabled = layer.git_tracking.enabled
        if layer.git_tracking.commit_policy is not None:
            git_tracking_commit_policy = layer.git_tracking.commit_policy
        if layer.git_tracking.failure_mode is not None:
            git_tracking_failure_mode = layer.git_tracking.failure_mode
        if layer.tracing.enabled is not None:
            tracing_enabled = layer.tracing.enabled
        if layer.tracing.path is not None:
            tracing_path = layer.tracing.path
        if layer.tracing.failure_mode is not None:
            tracing_failure_mode = layer.tracing.failure_mode
        if layer.tracing.include_state_snapshots is not None:
            tracing_include_state_snapshots = layer.tracing.include_state_snapshots

    if git_tracking_commit_policy == "off":
        git_tracking_enabled = False

    cli_max_steps = getattr(args, "max_steps", None)
    if cli_max_steps is not None:
        if isinstance(cli_max_steps, bool) or not isinstance(cli_max_steps, int) or cli_max_steps <= 0:
            raise ConfigError("CLI runtime max_steps must be a positive integer when provided.")
        max_steps = cli_max_steps

    cli_no_git = _optional_cli_bool(getattr(args, "no_git", None), "no_git")
    if cli_no_git:
        git_tracking_enabled = False
    cli_git_commit_policy = _optional_cli_git_commit_policy(getattr(args, "git_commit_policy", None))
    if cli_git_commit_policy is not None:
        git_tracking_commit_policy = cli_git_commit_policy
        git_tracking_enabled = cli_git_commit_policy != "off"

    cli_no_trace = _optional_cli_bool(getattr(args, "no_trace", None), "no_trace")
    if cli_no_trace:
        tracing_enabled = False

    if git_tracking_commit_policy == "off":
        git_tracking_enabled = False

    return RuntimeConfig(
        max_steps=max_steps,
        git_tracking=GitTrackingRuntimeConfig(
            enabled=git_tracking_enabled,
            commit_policy=git_tracking_commit_policy,
            failure_mode=git_tracking_failure_mode,
        ),
        tracing=TracingRuntimeConfig(
            enabled=tracing_enabled,
            path=tracing_path,
            failure_mode=tracing_failure_mode,
            include_state_snapshots=tracing_include_state_snapshots,
        ),
    )


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


def _optional_bool(raw_value: object, label: str, source: Path) -> bool | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, bool):
        raise ConfigError(f"{source}: {label} must be a boolean when provided.")
    return raw_value


def _parse_provider_name(raw_value: object, label: str, source: Path) -> str | None:
    value = _optional_string(raw_value, label, source)
    if value is None:
        return None
    if value not in SUPPORTED_PROVIDER_NAMES:
        raise ConfigError(f"{source}: {label} must be one of: {', '.join(sorted(SUPPORTED_PROVIDER_NAMES))}.")
    return value


def _optional_cli_provider_name(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ConfigError("CLI provider must be a non-empty string when provided.")
    value = raw_value.strip()
    if value not in SUPPORTED_PROVIDER_NAMES:
        raise ConfigError(f"CLI provider must be one of: {', '.join(sorted(SUPPORTED_PROVIDER_NAMES))}.")
    return value


def _optional_cli_bool(raw_value: object, label: str) -> bool:
    if raw_value is None:
        return False
    if not isinstance(raw_value, bool):
        raise ConfigError(f"CLI {label} must be a boolean flag when provided.")
    return raw_value


def _optional_cli_git_commit_policy(raw_value: object) -> GitCommitPolicy | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ConfigError("CLI git_commit_policy must be a non-empty string when provided.")
    value = raw_value.strip()
    if value not in SUPPORTED_GIT_COMMIT_POLICIES:
        raise ConfigError(
            f"CLI git_commit_policy must be one of: {', '.join(sorted(SUPPORTED_GIT_COMMIT_POLICIES))}."
        )
    return cast(GitCommitPolicy, value)


def _apply_generic_provider_overrides(
    *,
    provider_name: str,
    model: str | None,
    model_effort: str | None,
    codex_model: str,
    codex_effort: str | None,
    claude_model: str | None,
    claude_effort: str | None,
) -> tuple[str, str | None, str | None, str | None]:
    if provider_name == "codex":
        if model is not None:
            codex_model = model
        if model_effort is not None:
            codex_effort = model_effort
        return codex_model, codex_effort, claude_model, claude_effort
    if provider_name == "claude":
        if model is not None:
            claude_model = model
        if model_effort is not None:
            claude_effort = model_effort
        return codex_model, codex_effort, claude_model, claude_effort
    raise ConfigError(f"provider.name must be one of: {', '.join(sorted(SUPPORTED_PROVIDER_NAMES))}.")


def _optional_permission_strategy(raw_value: object, label: str, source: Path) -> str | None:
    value = _optional_string(raw_value, label, source)
    if value is None:
        return None
    if value not in SUPPORTED_CLAUDE_PERMISSION_STRATEGIES:
        raise ConfigError(
            f"{source}: {label} must be one of: {', '.join(sorted(SUPPORTED_CLAUDE_PERMISSION_STRATEGIES))}."
        )
    return value


def _optional_git_commit_policy(raw_value: object, label: str, source: Path) -> GitCommitPolicy | None:
    value = _optional_string(raw_value, label, source)
    if value is None:
        return None
    if value not in SUPPORTED_GIT_COMMIT_POLICIES:
        raise ConfigError(f"{source}: {label} must be one of: {', '.join(sorted(SUPPORTED_GIT_COMMIT_POLICIES))}.")
    return cast(GitCommitPolicy, value)


def _optional_failure_mode(raw_value: object, label: str, source: Path) -> FailureMode | None:
    value = _optional_string(raw_value, label, source)
    if value is None:
        return None
    if value not in SUPPORTED_FAILURE_MODES:
        raise ConfigError(f"{source}: {label} must be one of: {', '.join(sorted(SUPPORTED_FAILURE_MODES))}.")
    return cast(FailureMode, value)
