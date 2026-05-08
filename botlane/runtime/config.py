"""Generic runtime config discovery."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from botlane.core.extensions import ExtensionFailurePolicy
from botlane.core.provider_policy import (
    ModelPolicy,
    PermissionPolicy,
    PolicyValidationMode,
    ProviderPolicy,
    ProviderPolicyOverride,
    ProviderPolicyValidationConfig,
    SandboxPolicy,
    StrictProviderPolicy,
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    merge_provider_policies,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None


CONFIG_FILENAMES = ("botlane.yaml", "botlane.config")
LEGACY_CONFIG_FILENAMES = ("autoloop.yaml", "autoloop.config")
DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_PROVIDER_NAME = "codex"
SUPPORTED_PROVIDER_NAMES = frozenset({"codex", "claude"})
DEFAULT_CLAUDE_PERMISSION_STRATEGY = "inherit"
SUPPORTED_CLAUDE_PERMISSION_STRATEGIES = frozenset({"inherit", "allow_core_tools", "bypass"})
DEFAULT_MAX_STEPS = 100
SUPPORTED_GIT_COMMIT_POLICIES = frozenset({"off", "run", "step"})
SUPPORTED_EXTENSION_FAILURE_POLICIES = frozenset({"propagate", "record_and_continue"})
SUPPORTED_REPLAY_MISMATCH_BEHAVIORS = frozenset({"warn", "fail"})
SUPPORTED_RESUME_TOPOLOGY_MISMATCH_BEHAVIORS = frozenset({"warn", "fail"})
_LEGACY_POLICY_EFFORT_ALIASES = {"max": "xhigh"}


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


GitCommitPolicy = Literal["off", "run", "step"]


class _RuntimeConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProviderPolicyValidationConfigOverride(_RuntimeConfigModel):
    unsupported: PolicyValidationMode | None = None
    lossy_mapping: PolicyValidationMode | None = None
    unsafe_expansion: PolicyValidationMode | None = None


class ProviderPolicyRuntimeConfigOverride(_RuntimeConfigModel):
    default: ProviderPolicyOverride | None = None
    strict: StrictProviderPolicy | None = None
    validation: ProviderPolicyValidationConfigOverride | None = None


class ProviderPolicyRuntimeConfig(_RuntimeConfigModel):
    default: ProviderPolicy = Field(default_factory=lambda: SYSTEM_DEFAULT_PROVIDER_POLICY)
    strict: StrictProviderPolicy | None = None
    validation: ProviderPolicyValidationConfig = Field(default_factory=ProviderPolicyValidationConfig)


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
    failure_policy: ExtensionFailurePolicy = "propagate"


@dataclass(frozen=True, slots=True)
class TracingRuntimeConfig:
    enabled: bool = True
    path: str = "trace.jsonl"
    failure_policy: ExtensionFailurePolicy = "propagate"
    include_state_snapshots: bool = True


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    max_steps: int = DEFAULT_MAX_STEPS
    full_auto: bool = False
    replay_mismatch_behavior: Literal["warn", "fail"] = "warn"
    resume_topology_mismatch_behavior: Literal["warn", "fail"] = "warn"
    git_tracking: GitTrackingRuntimeConfig = field(default_factory=GitTrackingRuntimeConfig)
    tracing: TracingRuntimeConfig = field(default_factory=TracingRuntimeConfig)


@dataclass(frozen=True, slots=True)
class ResolvedRuntimeConfig:
    provider: ProviderConfig
    runtime: RuntimeConfig
    provider_policy: ProviderPolicyRuntimeConfig = field(default_factory=ProviderPolicyRuntimeConfig)


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
    failure_policy: ExtensionFailurePolicy | None = None


@dataclass(frozen=True, slots=True)
class TracingRuntimeConfigOverride:
    enabled: bool | None = None
    path: str | None = None
    failure_policy: ExtensionFailurePolicy | None = None
    include_state_snapshots: bool | None = None


@dataclass(frozen=True, slots=True)
class RuntimeConfigOverride:
    max_steps: int | None = None
    full_auto: bool | None = None
    replay_mismatch_behavior: Literal["warn", "fail"] | None = None
    resume_topology_mismatch_behavior: Literal["warn", "fail"] | None = None
    git_tracking: GitTrackingRuntimeConfigOverride = field(default_factory=GitTrackingRuntimeConfigOverride)
    tracing: TracingRuntimeConfigOverride = field(default_factory=TracingRuntimeConfigOverride)


@dataclass(frozen=True, slots=True)
class RuntimeConfigLayer:
    provider: ProviderConfigOverride = field(default_factory=ProviderConfigOverride)
    runtime: RuntimeConfigOverride = field(default_factory=RuntimeConfigOverride)
    provider_policy: ProviderPolicyRuntimeConfigOverride = field(default_factory=ProviderPolicyRuntimeConfigOverride)


def user_config_dir() -> Path:
    xdg_config_home = Path.home() / ".config"
    if "XDG_CONFIG_HOME" in __import__("os").environ:
        xdg_config_home = Path(__import__("os").environ["XDG_CONFIG_HOME"]).expanduser()
    return xdg_config_home / "botlane"


def legacy_user_config_dir() -> Path:
    xdg_config_home = Path.home() / ".config"
    if "XDG_CONFIG_HOME" in __import__("os").environ:
        xdg_config_home = Path(__import__("os").environ["XDG_CONFIG_HOME"]).expanduser()
    return xdg_config_home / "autoloop"


def discover_config_file(directory: Path) -> Path | None:
    preferred_matches = [directory / filename for filename in CONFIG_FILENAMES if (directory / filename).is_file()]
    if len(preferred_matches) > 1:
        raise ConfigError(
            "Found multiple configuration files in "
            f"{directory}: {', '.join(path.name for path in preferred_matches)}. Keep only one."
        )
    if preferred_matches:
        return preferred_matches[0]
    legacy_matches = [directory / filename for filename in LEGACY_CONFIG_FILENAMES if (directory / filename).is_file()]
    if len(legacy_matches) > 1:
        raise ConfigError(
            "Found multiple configuration files in "
            f"{directory}: {', '.join(path.name for path in legacy_matches)}. Keep only one."
        )
    return legacy_matches[0] if legacy_matches else None


def load_runtime_config_file(path: Path) -> object:
    if yaml is None:
        try:
            return _load_narrow_yaml_mapping(path)
        except ConfigError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise ConfigError(f"{path} could not be parsed as YAML: {exc}") from exc
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - parser-specific details
        raise ConfigError(f"{path} could not be parsed as YAML: {exc}") from exc


def _load_narrow_yaml_mapping(path: Path) -> object:
    lines = path.read_text(encoding="utf-8").splitlines()
    root: dict[str, object] = {}
    stack: list[tuple[int, dict[str, object]]] = [(0, root)]

    for line_number, raw_line in enumerate(lines, start=1):
        content = _strip_yaml_comment(raw_line)
        if not content.strip():
            continue
        if "\t" in raw_line:
            raise ConfigError(f"{path}:{line_number}: tabs are not supported in YAML indentation.")
        indent = len(content) - len(content.lstrip(" "))
        if indent % 2 != 0:
            raise ConfigError(f"{path}:{line_number}: indentation must use multiples of 2 spaces.")

        while indent < stack[-1][0]:
            stack.pop()
        if indent != stack[-1][0]:
            if len(stack) == 1:
                raise ConfigError(f"{path}:{line_number}: top-level entries must not be indented.")
            raise ConfigError(
                f"{path}:{line_number}: indentation increase is only allowed after a mapping key with no scalar value."
            )

        stripped = content.strip()
        if stripped.startswith(("-", "?", "[", "{", "|", ">")):
            raise ConfigError(f"{path}:{line_number}: unsupported YAML construct in runtime config.")
        if ":" not in stripped:
            raise ConfigError(f"{path}:{line_number}: expected 'key: value' mapping entry.")

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"{path}:{line_number}: mapping keys must be non-empty.")
        raw_value = raw_value.strip()
        parent = stack[-1][1]

        if raw_value == "":
            next_mapping: dict[str, object] = {}
            parent[key] = next_mapping
            stack.append((indent + 2, next_mapping))
            continue

        parent[key] = _parse_narrow_yaml_scalar(raw_value, path=path, line_number=line_number)

    return root


def _strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def _parse_narrow_yaml_scalar(raw_value: str, *, path: Path, line_number: int) -> object:
    lowered = raw_value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    if raw_value.startswith(("'", '"')):
        if len(raw_value) < 2 or raw_value[-1] != raw_value[0]:
            raise ConfigError(f"{path}:{line_number}: unterminated quoted string.")
        return raw_value[1:-1]
    if raw_value.startswith("["):
        return _parse_narrow_yaml_inline_list(raw_value, path=path, line_number=line_number)
    if raw_value.lstrip("-").isdigit():
        return int(raw_value)
    if any(token in raw_value for token in ("[", "]", "{", "}")):
        raise ConfigError(f"{path}:{line_number}: unsupported YAML construct in runtime config.")
    return raw_value


def _parse_narrow_yaml_inline_list(raw_value: str, *, path: Path, line_number: int) -> list[object]:
    if not raw_value.endswith("]"):
        raise ConfigError(f"{path}:{line_number}: unterminated inline list.")
    inner = raw_value[1:-1].strip()
    if not inner:
        return []

    items: list[str] = []
    token: list[str] = []
    in_single = False
    in_double = False
    for char in inner:
        if char == "'" and not in_double:
            in_single = not in_single
            token.append(char)
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            token.append(char)
            continue
        if char == "," and not in_single and not in_double:
            item = "".join(token).strip()
            if not item:
                raise ConfigError(f"{path}:{line_number}: inline lists must not contain empty items.")
            items.append(item)
            token = []
            continue
        token.append(char)
    if in_single or in_double:
        raise ConfigError(f"{path}:{line_number}: unterminated quoted string in inline list.")
    tail = "".join(token).strip()
    if not tail:
        raise ConfigError(f"{path}:{line_number}: inline lists must not end with an empty item.")
    items.append(tail)
    return [_parse_narrow_yaml_scalar(item, path=path, line_number=line_number) for item in items]


def parse_runtime_config(payload: object, source: Path) -> RuntimeConfigLayer:
    if payload is None:
        return RuntimeConfigLayer()
    if not isinstance(payload, dict):
        raise ConfigError(f"{source}: configuration must be a YAML mapping.")

    _reject_unknown_keys(source, "configuration", payload, {"provider", "runtime", "provider_policy"})

    provider_payload = payload.get("provider")
    runtime_payload = payload.get("runtime")
    provider_policy_payload = payload.get("provider_policy")
    if provider_payload is None:
        provider_payload = {}
    if runtime_payload is None:
        runtime_payload = {}
    if provider_policy_payload is None:
        provider_policy_payload = {}
    if not isinstance(provider_payload, dict):
        raise ConfigError(f"{source}: provider must be a mapping when provided.")
    if not isinstance(runtime_payload, dict):
        raise ConfigError(f"{source}: runtime must be a mapping when provided.")
    if not isinstance(provider_policy_payload, dict):
        raise ConfigError(f"{source}: provider_policy must be a mapping when provided.")

    _reject_unknown_keys(source, "provider", provider_payload, {"name", "model", "model_effort", "codex", "claude"})
    _reject_unknown_keys(
        source,
        "runtime",
        runtime_payload,
        {"max_steps", "full_auto", "replay_mismatch_behavior", "resume_topology_mismatch_behavior", "git_tracking", "tracing"},
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

    _reject_unknown_keys(source, "runtime.git_tracking", git_tracking_payload, {"enabled", "commit_policy", "failure_policy"})
    _reject_unknown_keys(
        source,
        "runtime.tracing",
        tracing_payload,
        {"enabled", "path", "failure_policy", "include_state_snapshots"},
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
        full_auto=_optional_bool(runtime_payload.get("full_auto"), "runtime.full_auto", source),
        replay_mismatch_behavior=_optional_replay_mismatch_behavior(
            runtime_payload.get("replay_mismatch_behavior"),
            "runtime.replay_mismatch_behavior",
            source,
        ),
        resume_topology_mismatch_behavior=_optional_resume_topology_mismatch_behavior(
            runtime_payload.get("resume_topology_mismatch_behavior"),
            "runtime.resume_topology_mismatch_behavior",
            source,
        ),
        git_tracking=GitTrackingRuntimeConfigOverride(
            enabled=_optional_bool(git_tracking_payload.get("enabled"), "runtime.git_tracking.enabled", source),
            commit_policy=_optional_git_commit_policy(
                git_tracking_payload.get("commit_policy"),
                "runtime.git_tracking.commit_policy",
                source,
            ),
            failure_policy=_optional_extension_failure_policy(
                git_tracking_payload.get("failure_policy"),
                "runtime.git_tracking.failure_policy",
                source,
            ),
        ),
        tracing=TracingRuntimeConfigOverride(
            enabled=_optional_bool(tracing_payload.get("enabled"), "runtime.tracing.enabled", source),
            path=_optional_string(tracing_payload.get("path"), "runtime.tracing.path", source),
            failure_policy=_optional_extension_failure_policy(
                tracing_payload.get("failure_policy"),
                "runtime.tracing.failure_policy",
                source,
            ),
            include_state_snapshots=_optional_bool(
                tracing_payload.get("include_state_snapshots"),
                "runtime.tracing.include_state_snapshots",
                source,
            ),
        ),
    )
    provider_policy = _parse_provider_policy_config(provider_policy_payload, source)
    return RuntimeConfigLayer(provider=provider, runtime=runtime, provider_policy=provider_policy)


def parse_policy_runtime_config(payload: object, source: Path) -> RuntimeConfigLayer:
    if payload is None:
        return RuntimeConfigLayer()
    if not isinstance(payload, dict):
        raise ConfigError(f"{source}: policy file must be a YAML mapping.")
    if any(key in payload for key in ("provider", "runtime", "provider_policy")):
        return parse_runtime_config(payload, source)
    return parse_runtime_config({"provider_policy": payload}, source)


def resolve_runtime_config(root: Path, args: argparse.Namespace) -> ResolvedRuntimeConfig:
    global_config_path = discover_config_file(user_config_dir())
    if global_config_path is None:
        global_config_path = discover_config_file(legacy_user_config_dir())
    local_config_path = discover_config_file(root)
    policy_file_path = _optional_cli_path(getattr(args, "policy_file", None), "policy_file")

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
    policy_layer = (
        parse_policy_runtime_config(load_runtime_config_file(policy_file_path), policy_file_path)
        if policy_file_path is not None
        else RuntimeConfigLayer()
    )
    provider = _merge_provider_config(global_layer.provider, local_layer.provider, policy_layer.provider, args=args)
    runtime = _merge_runtime_config(global_layer.runtime, local_layer.runtime, policy_layer.runtime, args=args)
    return ResolvedRuntimeConfig(
        provider=provider,
        runtime=runtime,
        provider_policy=_merge_provider_policy_config(
            global_layer.provider_policy,
            local_layer.provider_policy,
            policy_layer.provider_policy,
            provider_layers=(global_layer.provider, local_layer.provider, policy_layer.provider),
            provider=provider,
            runtime=runtime,
            args=args,
        ),
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
    full_auto = False
    replay_mismatch_behavior: Literal["warn", "fail"] = "warn"
    resume_topology_mismatch_behavior: Literal["warn", "fail"] = "warn"
    git_tracking_enabled = True
    git_tracking_commit_policy: GitCommitPolicy = "step"
    git_tracking_failure_policy: ExtensionFailurePolicy = "propagate"
    tracing_enabled = True
    tracing_path = "trace.jsonl"
    tracing_failure_policy: ExtensionFailurePolicy = "propagate"
    tracing_include_state_snapshots = True

    for layer in layers:
        if layer.max_steps is not None:
            max_steps = layer.max_steps
        if layer.full_auto is not None:
            full_auto = layer.full_auto
        if layer.replay_mismatch_behavior is not None:
            replay_mismatch_behavior = layer.replay_mismatch_behavior
        if layer.resume_topology_mismatch_behavior is not None:
            resume_topology_mismatch_behavior = layer.resume_topology_mismatch_behavior
        if layer.git_tracking.enabled is not None:
            git_tracking_enabled = layer.git_tracking.enabled
        if layer.git_tracking.commit_policy is not None:
            git_tracking_commit_policy = layer.git_tracking.commit_policy
        if layer.git_tracking.failure_policy is not None:
            git_tracking_failure_policy = layer.git_tracking.failure_policy
        if layer.tracing.enabled is not None:
            tracing_enabled = layer.tracing.enabled
        if layer.tracing.path is not None:
            tracing_path = layer.tracing.path
        if layer.tracing.failure_policy is not None:
            tracing_failure_policy = layer.tracing.failure_policy
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
        full_auto=full_auto,
        replay_mismatch_behavior=replay_mismatch_behavior,
        resume_topology_mismatch_behavior=resume_topology_mismatch_behavior,
        git_tracking=GitTrackingRuntimeConfig(
            enabled=git_tracking_enabled,
            commit_policy=git_tracking_commit_policy,
            failure_policy=git_tracking_failure_policy,
        ),
        tracing=TracingRuntimeConfig(
            enabled=tracing_enabled,
            path=tracing_path,
            failure_policy=tracing_failure_policy,
            include_state_snapshots=tracing_include_state_snapshots,
        ),
    )


def _parse_provider_policy_config(
    payload: dict[str, Any],
    source: Path,
) -> ProviderPolicyRuntimeConfigOverride:
    if "default" in payload and payload["default"] is None:
        raise ConfigError(f"{source}: provider_policy.default must be a mapping when provided.")
    if "validation" in payload and payload["validation"] is None:
        raise ConfigError(f"{source}: provider_policy.validation must be a mapping when provided.")
    try:
        return ProviderPolicyRuntimeConfigOverride.model_validate(payload)
    except ValidationError as exc:
        raise _render_model_validation_error(source, "provider_policy", exc) from exc


def _merge_provider_policy_config(
    *layers: ProviderPolicyRuntimeConfigOverride,
    provider_layers: tuple[ProviderConfigOverride, ...],
    provider: ProviderConfig,
    runtime: RuntimeConfig,
    args: argparse.Namespace,
) -> ProviderPolicyRuntimeConfig:
    default_policy = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        *(layer.default for layer in layers if layer.default is not None),
    )

    legacy_model, legacy_effort = _resolve_explicit_legacy_provider_model_overrides(
        *provider_layers,
        provider_name=provider.name,
        args=args,
    )

    if legacy_model is not None and not any(_policy_override_sets_field(layer.default, ("model", "default")) for layer in layers):
        default_policy = merge_provider_policies(
            default_policy,
            ProviderPolicyOverride(model=ModelPolicy(default=legacy_model)),
        )
    if legacy_effort is not None and not any(_policy_override_sets_field(layer.default, ("model", "effort")) for layer in layers):
        default_policy = merge_provider_policies(
            default_policy,
            ProviderPolicyOverride(model=ModelPolicy(effort=_policy_effort_alias(legacy_effort))),
        )
    if runtime.full_auto and not any(
        _policy_override_sets_field(layer.default, ("permissions", "mode")) for layer in layers
    ):
        default_policy = merge_provider_policies(
            default_policy,
            ProviderPolicyOverride(permissions=PermissionPolicy(mode="full_auto_sandboxed")),
        )
    if (
        provider.name == "claude"
        and provider.claude.permission_strategy == "bypass"
        and not _policy_layers_set_any_field(
            layers,
            (
                ("permissions", "mode"),
                ("permissions", "allow_dangerous_bypass"),
                ("permissions", "disable_dangerous_bypass"),
                ("sandbox", "enabled"),
                ("sandbox", "required"),
                ("sandbox", "mode"),
            ),
        )
    ):
        default_policy = merge_provider_policies(
            default_policy,
            ProviderPolicyOverride(
                permissions=PermissionPolicy(
                    mode="full_auto_unsandboxed",
                    allow_dangerous_bypass=True,
                    disable_dangerous_bypass=False,
                ),
                sandbox=SandboxPolicy(
                    enabled=False,
                    required=False,
                    mode="danger_full_access",
                ),
            ),
        )

    strict_payload: dict[str, Any] | None = None
    for layer in layers:
        if "strict" not in layer.model_fields_set:
            continue
        if layer.strict is None:
            strict_payload = None
            continue
        update = layer.strict.model_dump(mode="python", exclude_none=True, exclude_unset=True, warnings=False)
        strict_payload = _deep_merge_dicts(strict_payload or {}, update)
    strict = StrictProviderPolicy.model_validate(strict_payload) if strict_payload is not None else None

    validation_payload = ProviderPolicyValidationConfig().model_dump(mode="python", warnings=False)
    for layer in layers:
        if layer.validation is None:
            continue
        update = layer.validation.model_dump(mode="python", exclude_none=True, exclude_unset=True, warnings=False)
        validation_payload = _deep_merge_dicts(validation_payload, update)

    cli_validation_overrides = {
        "unsupported": _optional_cli_policy_validation_mode(getattr(args, "policy_validation_unsupported", None)),
        "lossy_mapping": _optional_cli_policy_validation_mode(getattr(args, "policy_validation_lossy", None)),
        "unsafe_expansion": _optional_cli_policy_validation_mode(
            getattr(args, "policy_validation_unsafe_expansion", None)
        ),
    }
    validation_payload = _deep_merge_dicts(
        validation_payload,
        {key: value for key, value in cli_validation_overrides.items() if value is not None},
    )
    validation = ProviderPolicyValidationConfig.model_validate(validation_payload)

    return ProviderPolicyRuntimeConfig(
        default=default_policy,
        strict=strict,
        validation=validation,
    )


def _resolve_explicit_legacy_provider_model_overrides(
    *layers: ProviderConfigOverride,
    provider_name: str,
    args: argparse.Namespace,
) -> tuple[str | None, str | None]:
    codex_model: str | None = None
    codex_effort: str | None = None
    claude_model: str | None = None
    claude_effort: str | None = None

    for layer in cast(tuple[ProviderConfigOverride, ...], layers):
        if layer.codex.model is not None:
            codex_model = layer.codex.model
        if layer.codex.model_effort is not None:
            codex_effort = layer.codex.model_effort
        if layer.claude.model is not None:
            claude_model = layer.claude.model
        if layer.claude.effort is not None:
            claude_effort = layer.claude.effort

        codex_model, codex_effort, claude_model, claude_effort = _apply_generic_provider_overrides(
            provider_name=provider_name,
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
        provider_name=provider_name,
        model=cli_model.strip() if isinstance(cli_model, str) and cli_model.strip() else None,
        model_effort=cli_model_effort.strip()
        if isinstance(cli_model_effort, str) and cli_model_effort.strip()
        else None,
        codex_model=codex_model,
        codex_effort=codex_effort,
        claude_model=claude_model,
        claude_effort=claude_effort,
    )

    if provider_name == "codex":
        return codex_model, codex_effort
    return claude_model, claude_effort


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


def _optional_cli_path(raw_value: object, label: str) -> Path | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, Path):
        raise ConfigError(f"CLI {label} must be a filesystem path when provided.")
    return raw_value


def _optional_cli_policy_validation_mode(raw_value: object) -> PolicyValidationMode | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ConfigError("CLI policy validation overrides must be non-empty strings when provided.")
    value = raw_value.strip()
    if value not in {"fail", "warn", "ignore"}:
        raise ConfigError("CLI policy validation overrides must be one of: fail, warn, ignore.")
    return cast(PolicyValidationMode, value)


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


def _policy_effort_alias(value: str) -> str:
    return _LEGACY_POLICY_EFFORT_ALIASES.get(value, value)


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


def _optional_extension_failure_policy(
    raw_value: object,
    label: str,
    source: Path,
) -> ExtensionFailurePolicy | None:
    value = _optional_string(raw_value, label, source)
    if value is None:
        return None
    if value not in SUPPORTED_EXTENSION_FAILURE_POLICIES:
        raise ConfigError(
            f"{source}: {label} must be one of: {', '.join(sorted(SUPPORTED_EXTENSION_FAILURE_POLICIES))}."
        )
    return cast(ExtensionFailurePolicy, value)


def _optional_resume_topology_mismatch_behavior(
    raw_value: object,
    label: str,
    source: Path,
) -> Literal["warn", "fail"] | None:
    value = _optional_string(raw_value, label, source)
    if value is None:
        return None
    if value not in SUPPORTED_RESUME_TOPOLOGY_MISMATCH_BEHAVIORS:
        raise ConfigError(
            f"{source}: {label} must be one of: {', '.join(sorted(SUPPORTED_RESUME_TOPOLOGY_MISMATCH_BEHAVIORS))}."
        )
    return cast(Literal["warn", "fail"], value)


def _optional_replay_mismatch_behavior(
    raw_value: object,
    label: str,
    source: Path,
) -> Literal["warn", "fail"] | None:
    value = _optional_string(raw_value, label, source)
    if value is None:
        return None
    if value not in SUPPORTED_REPLAY_MISMATCH_BEHAVIORS:
        raise ConfigError(
            f"{source}: {label} must be one of: {', '.join(sorted(SUPPORTED_REPLAY_MISMATCH_BEHAVIORS))}."
        )
    return cast(Literal["warn", "fail"], value)


def _policy_override_sets_field(
    policy: ProviderPolicyOverride | None,
    path: tuple[str, ...],
) -> bool:
    current: BaseModel | Any = policy
    for part in path:
        if not isinstance(current, BaseModel) or part not in current.model_fields_set:
            return False
        current = getattr(current, part)
    return True


def _policy_layers_set_any_field(
    layers: tuple[ProviderPolicyRuntimeConfigOverride, ...],
    paths: tuple[tuple[str, ...], ...],
) -> bool:
    for layer in layers:
        for path in paths:
            if _policy_override_sets_field(layer.default, path):
                return True
    return False


def _deep_merge_dicts(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in update.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(existing, value)
        else:
            merged[key] = value
    return merged


def _render_model_validation_error(source: Path, prefix: str, exc: ValidationError) -> ConfigError:
    messages = []
    for error in exc.errors(include_url=False):
        location = _format_validation_location(prefix, tuple(error.get("loc", ())))
        messages.append(f"{source}: {location}: {error['msg']}")
    return ConfigError("\n".join(messages))


def _format_validation_location(prefix: str, location: tuple[Any, ...]) -> str:
    parts = [prefix]
    for item in location:
        if isinstance(item, int):
            parts[-1] = f"{parts[-1]}[{item}]"
        else:
            parts.append(str(item))
    return ".".join(parts)
