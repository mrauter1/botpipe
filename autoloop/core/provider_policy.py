"""Provider policy core models and validation helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import WorkflowExecutionError


PolicyValidationMode = Literal["fail", "warn", "ignore"]


class _PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _dedupe_strings(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError("policy entries must be strings")
        item = value.strip()
        if not item:
            raise ValueError("policy entries must be non-empty strings")
        if "\x00" in item:
            raise ValueError("policy entries must not contain NUL bytes")
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


def _dedupe_domains(values: Iterable[str]) -> tuple[str, ...]:
    normalized = _dedupe_strings(values)
    for value in normalized:
        if "://" in value:
            raise ValueError(f"domain entries must not include a URL scheme: {value!r}")
    return normalized


def _merge_string_tuples(*values: Iterable[str]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in values:
        for item in group:
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return tuple(merged)


def _safe_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _redact_secret_mapping(values: Mapping[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in values.items():
        upper_key = key.upper()
        if any(marker in upper_key for marker in ("TOKEN", "SECRET", "KEY")):
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted


def _normalize_policy_string(value: str) -> str:
    normalized = os.path.normpath(value.strip())
    return "." if normalized == "" else normalized


def _resolved_policy_path(path_value: str, workspace_root: Path) -> tuple[Path, bool]:
    raw = Path(_normalize_policy_string(path_value))
    workspace_root_resolved = workspace_root.resolve(strict=False)
    candidate = raw if raw.is_absolute() else workspace_root / raw
    resolved = candidate.resolve(strict=False)
    escaped_workspace = not raw.is_absolute() and not resolved.is_relative_to(workspace_root_resolved)
    return resolved, escaped_workspace


def _domain_allowed(domain: str, allowed_domains: Sequence[str]) -> bool:
    candidate = domain.casefold()
    for allowed in allowed_domains:
        pattern = allowed.casefold()
        if candidate == pattern:
            return True
        if pattern.startswith("*."):
            suffix = pattern[1:]
            if candidate.endswith(suffix) and candidate != suffix[1:]:
                return True
    return False


class ModelPolicy(_PolicyModel):
    default: str | None = None
    provider: str | None = None
    base_url: str | None = None
    effort: Literal["minimal", "low", "medium", "high", "xhigh"] | None = None
    verbosity: Literal["low", "medium", "high"] | None = None
    reasoning_summary: Literal["auto", "concise", "detailed", "none"] | None = None
    overrides: dict[str, str] = Field(default_factory=dict)

    @field_validator("overrides")
    @classmethod
    def _validate_overrides(cls, value: dict[str, str]) -> dict[str, str]:
        return {str(key): str(item) for key, item in value.items()}


class PermissionPolicy(_PolicyModel):
    mode: Literal[
        "ask",
        "auto_edit",
        "full_auto_sandboxed",
        "full_auto_unsandboxed",
        "deny_all",
    ] = "ask"
    allow_dangerous_bypass: bool = False
    disable_dangerous_bypass: bool = True
    allow: tuple[str, ...] = ()
    ask: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()

    @field_validator("allow", "ask", "deny", mode="before")
    @classmethod
    def _normalize_rules(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_strings(value)

    @model_validator(mode="after")
    def _validate_dangerous_bypass(self) -> "PermissionPolicy":
        if self.mode == "full_auto_unsandboxed" and not self.allow_dangerous_bypass:
            raise ValueError(
                "permissions.mode='full_auto_unsandboxed' requires allow_dangerous_bypass=True"
            )
        return self


class WorkspaceFilesystemPolicy(_PolicyModel):
    allow_read: tuple[str, ...] = (".",)
    allow_write: tuple[str, ...] = (".",)
    deny_read: tuple[str, ...] = ()
    deny_write: tuple[str, ...] = ()

    @field_validator("allow_read", "allow_write", "deny_read", "deny_write", mode="before")
    @classmethod
    def _normalize_paths(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_strings(value)


class WorkspaceNetworkPolicy(_PolicyModel):
    enabled: bool = True
    mode: Literal["none", "limited", "full"] = "full"
    allow_domains: tuple[str, ...] = ()
    deny_domains: tuple[str, ...] = ()
    allow_local_binding: bool = False

    @field_validator("allow_domains", "deny_domains", mode="before")
    @classmethod
    def _normalize_domains(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_domains(value)

    @model_validator(mode="after")
    def _normalize_mode(self) -> "WorkspaceNetworkPolicy":
        if self.mode == "none" and self.enabled:
            return self.model_copy(update={"enabled": False})
        if not self.enabled and self.mode != "none":
            return self.model_copy(update={"mode": "none"})
        return self


class WorkspacePolicy(_PolicyModel):
    root: str = "."
    filesystem: WorkspaceFilesystemPolicy = Field(default_factory=WorkspaceFilesystemPolicy)
    network: WorkspaceNetworkPolicy = Field(default_factory=WorkspaceNetworkPolicy)

    @field_validator("root")
    @classmethod
    def _validate_root(cls, value: str) -> str:
        return _dedupe_strings((value,))[0]


class SandboxPolicy(_PolicyModel):
    enabled: bool = True
    required: bool = True
    mode: Literal["read_only", "workspace_write", "danger_full_access"] = "workspace_write"
    workspace: WorkspacePolicy = Field(default_factory=WorkspacePolicy)


class EnvPolicy(_PolicyModel):
    inherit: Literal["all", "core", "none"] = "core"
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ("*TOKEN*", "*SECRET*", "*KEY*")
    set: dict[str, str] = Field(default_factory=dict)

    @field_validator("allow", "deny", mode="before")
    @classmethod
    def _normalize_patterns(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_strings(value)

    @field_validator("set")
    @classmethod
    def _validate_set(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("env.set keys must be non-empty strings")
            if not isinstance(item, str):
                raise ValueError(f"env.set[{key!r}] must be a string")
            normalized[key] = item
        return normalized


class ToolPolicy(_PolicyModel):
    allow: tuple[str, ...] = ()
    ask: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()

    @field_validator("allow", "ask", "deny", mode="before")
    @classmethod
    def _normalize_rules(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_strings(value)


class InstructionPolicy(_PolicyModel):
    files: tuple[str, ...] = ()
    inline: str | None = None
    output_style: str | None = None

    @field_validator("files", mode="before")
    @classmethod
    def _normalize_files(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_strings(value)


class TelemetryPolicy(_PolicyModel):
    enabled: bool = False
    exporter: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("headers")
    @classmethod
    def _validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        return {str(key): str(item) for key, item in value.items()}


class ProviderPolicy(_PolicyModel):
    model: ModelPolicy = Field(default_factory=ModelPolicy)
    permissions: PermissionPolicy = Field(default_factory=PermissionPolicy)
    sandbox: SandboxPolicy = Field(default_factory=SandboxPolicy)
    env: EnvPolicy = Field(default_factory=EnvPolicy)
    tools: ToolPolicy = Field(default_factory=ToolPolicy)
    instructions: InstructionPolicy = Field(default_factory=InstructionPolicy)
    telemetry: TelemetryPolicy = Field(default_factory=TelemetryPolicy)
    codex: dict[str, Any] = Field(default_factory=dict)
    claude: dict[str, Any] = Field(default_factory=dict)

    @field_validator("codex", "claude")
    @classmethod
    def _validate_provider_extras(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("provider extras must be mappings")
        return deepcopy(value)

    @model_validator(mode="after")
    def _validate_cross_field_constraints(self) -> "ProviderPolicy":
        if self.sandbox.mode == "danger_full_access" and not self.permissions.allow_dangerous_bypass:
            raise ValueError(
                "sandbox.mode='danger_full_access' requires permissions.allow_dangerous_bypass=True"
            )
        if self.permissions.mode == "full_auto_sandboxed":
            if not self.sandbox.enabled:
                raise ValueError("permissions.mode='full_auto_sandboxed' requires sandbox.enabled=True")
            if not self.sandbox.required:
                raise ValueError("permissions.mode='full_auto_sandboxed' requires sandbox.required=True")
            if self.sandbox.mode == "danger_full_access":
                raise ValueError(
                    "permissions.mode='full_auto_sandboxed' is incompatible with sandbox.mode='danger_full_access'"
                )
        if self.permissions.mode == "full_auto_unsandboxed" and self.sandbox.mode != "danger_full_access":
            raise ValueError(
                "permissions.mode='full_auto_unsandboxed' requires sandbox.mode='danger_full_access'"
            )
        return self

    def with_overrides(self, **kwargs: Any) -> "ProviderPolicy":
        return merge_provider_policies(self, ProviderPolicyOverride(**kwargs))

    def allow_workspace_write(self, *paths: str) -> "ProviderPolicy":
        filesystem = self.sandbox.workspace.filesystem
        updated_filesystem = filesystem.model_copy(
            update={"allow_write": _merge_string_tuples(filesystem.allow_write, _dedupe_strings(paths))}
        )
        return self._with_filesystem(updated_filesystem)

    def deny_workspace_read(self, *paths: str) -> "ProviderPolicy":
        filesystem = self.sandbox.workspace.filesystem
        updated_filesystem = filesystem.model_copy(
            update={"deny_read": _merge_string_tuples(filesystem.deny_read, _dedupe_strings(paths))}
        )
        return self._with_filesystem(updated_filesystem)

    def with_network_domains(self, *domains: str) -> "ProviderPolicy":
        network = self.sandbox.workspace.network
        updated_network = network.model_copy(
            update={
                "enabled": True,
                "mode": "limited" if domains else network.mode,
                "allow_domains": _dedupe_domains(domains),
            }
        )
        return self._with_network(updated_network)

    def with_model_effort(self, effort: str) -> "ProviderPolicy":
        updated_model = self.model.model_copy(update={"effort": effort})
        return self.model_copy(update={"model": updated_model})

    def _with_filesystem(self, filesystem: WorkspaceFilesystemPolicy) -> "ProviderPolicy":
        workspace = self.sandbox.workspace.model_copy(update={"filesystem": filesystem})
        sandbox = self.sandbox.model_copy(update={"workspace": workspace})
        return self.model_copy(update={"sandbox": sandbox})

    def _with_network(self, network: WorkspaceNetworkPolicy) -> "ProviderPolicy":
        workspace = self.sandbox.workspace.model_copy(update={"network": network})
        sandbox = self.sandbox.model_copy(update={"workspace": workspace})
        return self.model_copy(update={"sandbox": sandbox})


class ProviderPolicyOverride(_PolicyModel):
    model: ModelPolicy | None = None
    permissions: PermissionPolicy | None = None
    sandbox: SandboxPolicy | None = None
    env: EnvPolicy | None = None
    tools: ToolPolicy | None = None
    instructions: InstructionPolicy | None = None
    telemetry: TelemetryPolicy | None = None
    codex: dict[str, Any] | None = None
    claude: dict[str, Any] | None = None


ResolvedProviderPolicy = ProviderPolicy


class StrictPermissionPolicy(_PolicyModel):
    allow_dangerous_bypass: bool | None = False
    disable_dangerous_bypass: bool | None = True
    required_deny: tuple[str, ...] = ()
    forbidden_allow: tuple[str, ...] = ()

    @field_validator("required_deny", "forbidden_allow", mode="before")
    @classmethod
    def _normalize_rules(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_strings(value)


class StrictWorkspaceFilesystemPolicy(_PolicyModel):
    allowed_read_roots: tuple[str, ...] | None = (".",)
    allowed_write_roots: tuple[str, ...] | None = (".",)
    required_deny_read: tuple[str, ...] = ("./.env", "./secrets/**")
    required_deny_write: tuple[str, ...] = ("/etc", "/usr/local/bin")
    allow_symlink_escape: bool = False

    @field_validator("allowed_read_roots", "allowed_write_roots", mode="before")
    @classmethod
    def _normalize_allowed_roots(cls, value: Any) -> tuple[str, ...] | None:
        if value is None:
            return None
        return _dedupe_strings(value)

    @field_validator("required_deny_read", "required_deny_write", mode="before")
    @classmethod
    def _normalize_required_deny(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_strings(value)


class StrictWorkspaceNetworkPolicy(_PolicyModel):
    allowed_modes: tuple[Literal["none", "limited", "full"], ...] = ("none", "limited", "full")
    allowed_domains: tuple[str, ...] | None = None
    required_deny_domains: tuple[str, ...] = ()
    allow_local_binding: bool | None = False

    @field_validator("allowed_modes", mode="before")
    @classmethod
    def _normalize_allowed_modes(cls, value: Any) -> tuple[Literal["none", "limited", "full"], ...]:
        if value is None:
            return ("none", "limited", "full")
        return tuple(value)

    @field_validator("allowed_domains", "required_deny_domains", mode="before")
    @classmethod
    def _normalize_allowed_domains(cls, value: Any) -> tuple[str, ...] | None:
        if value is None:
            return None
        return _dedupe_domains(value)


class StrictWorkspacePolicy(_PolicyModel):
    filesystem: StrictWorkspaceFilesystemPolicy = Field(default_factory=StrictWorkspaceFilesystemPolicy)
    network: StrictWorkspaceNetworkPolicy = Field(default_factory=StrictWorkspaceNetworkPolicy)


class StrictSandboxPolicy(_PolicyModel):
    required: bool | None = True
    allowed_modes: tuple[Literal["read_only", "workspace_write", "danger_full_access"], ...] = (
        "read_only",
        "workspace_write",
    )
    workspace: StrictWorkspacePolicy = Field(default_factory=StrictWorkspacePolicy)

    @field_validator("allowed_modes", mode="before")
    @classmethod
    def _normalize_modes(
        cls, value: Any
    ) -> tuple[Literal["read_only", "workspace_write", "danger_full_access"], ...]:
        if value is None:
            return ("read_only", "workspace_write")
        return tuple(value)


class StrictEnvPolicy(_PolicyModel):
    required_deny: tuple[str, ...] = ("*TOKEN*", "*SECRET*", "*KEY*")
    allowed_set_keys: tuple[str, ...] | None = None

    @field_validator("required_deny", "allowed_set_keys", mode="before")
    @classmethod
    def _normalize_patterns(cls, value: Any) -> tuple[str, ...] | None:
        if value is None:
            return None
        return _dedupe_strings(value)


class StrictProviderPolicy(_PolicyModel):
    permissions: StrictPermissionPolicy = Field(default_factory=StrictPermissionPolicy)
    sandbox: StrictSandboxPolicy = Field(default_factory=StrictSandboxPolicy)
    env: StrictEnvPolicy = Field(default_factory=StrictEnvPolicy)


class ProviderPolicyValidationConfig(_PolicyModel):
    unsupported: PolicyValidationMode = "fail"
    lossy_mapping: PolicyValidationMode = "warn"
    unsafe_expansion: PolicyValidationMode = "fail"


class ProviderPolicyViolation(_PolicyModel):
    field_path: str
    requested_value: Any | None = None
    constraint: str | None = None
    message: str | None = None

    def render(self) -> str:
        if self.message:
            return self.message
        if self.constraint is not None:
            return (
                f"{self.field_path}={self.requested_value!r} violates {self.constraint}"
                if self.requested_value is not None
                else f"{self.field_path} violates {self.constraint}"
            )
        return self.field_path


class ProviderPolicyError(WorkflowExecutionError):
    def __init__(self, violations: Sequence[ProviderPolicyViolation], *, step_name: str | None = None) -> None:
        self.step_name = step_name
        self.violations = tuple(violations)
        if self.violations:
            if step_name:
                message = f"Provider policy violation for step {step_name!r}:\n"
            else:
                message = "Provider policy violation:\n"
            message += "\n".join(f"- {violation.render()}" for violation in self.violations)
        else:
            message = "Provider policy violation"
        super().__init__(message)


class EffectiveEnforcementReport(_PolicyModel):
    sandbox_mode: str | None = None
    write_roots: tuple[str, ...] = ()
    read_roots: tuple[str, ...] = ()
    deny_read_enforced: bool | None = None
    deny_write_enforced: bool | None = None
    network_domain_filter_enforced: bool | None = None
    dangerous_bypass_disabled: bool | None = None

    @field_validator("write_roots", "read_roots", mode="before")
    @classmethod
    def _normalize_roots(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_strings(value)


class ProviderPolicyCapabilityReport(_PolicyModel):
    target: Literal["codex", "claude"]
    step_name: str | None = None
    policy_fingerprint: str
    unsupported: tuple[str, ...] = ()
    lossy: tuple[str, ...] = ()
    unsafe_expansions: tuple[str, ...] = ()
    emitted_files: tuple[str, ...] = ()
    emitted_cli_args: tuple[str, ...] = ()
    effective_enforcement: EffectiveEnforcementReport = Field(default_factory=EffectiveEnforcementReport)
    decision: Literal["ok", "warn", "fail"] = "ok"

    @field_validator(
        "unsupported",
        "lossy",
        "unsafe_expansions",
        "emitted_files",
        "emitted_cli_args",
        mode="before",
    )
    @classmethod
    def _normalize_entries(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_strings(value)


class ProviderPolicyEmission(_PolicyModel):
    target: Literal["codex", "claude"]
    config_files: dict[str, Path]
    cli_args: tuple[str, ...] = ()
    env: dict[str, str] = Field(default_factory=dict)
    capability_report: ProviderPolicyCapabilityReport

    @field_validator("config_files")
    @classmethod
    def _validate_config_files(cls, value: dict[str, Path]) -> dict[str, Path]:
        return {str(key): Path(path) for key, path in value.items()}

    @field_validator("cli_args", mode="before")
    @classmethod
    def _normalize_cli_args(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return _dedupe_strings(value)

    @field_validator("env")
    @classmethod
    def _validate_env(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("emission env keys must be non-empty strings")
            if not isinstance(item, str):
                raise ValueError(f"emission env[{key!r}] must be a string")
            normalized[key] = item
        return normalized

    def redacted_env(self) -> dict[str, str]:
        return _redact_secret_mapping(self.env)


SYSTEM_DEFAULT_PROVIDER_POLICY = ProviderPolicy(
    permissions=PermissionPolicy(
        mode="full_auto_sandboxed",
        allow_dangerous_bypass=False,
        disable_dangerous_bypass=True,
        allow=(),
        ask=(),
        deny=(),
    ),
    sandbox=SandboxPolicy(
        enabled=True,
        required=True,
        mode="workspace_write",
        workspace=WorkspacePolicy(
            filesystem=WorkspaceFilesystemPolicy(
                allow_read=(".",),
                allow_write=(".",),
                deny_read=(),
                deny_write=(),
            ),
            network=WorkspaceNetworkPolicy(
                enabled=True,
                mode="full",
                allow_domains=(),
                deny_domains=(),
                allow_local_binding=False,
            ),
        ),
    ),
    env=EnvPolicy(
        inherit="core",
        allow=(),
        deny=("*TOKEN*", "*SECRET*", "*KEY*"),
        set={},
    ),
)


_UNION_PATHS = {
    ("permissions", "deny"),
    ("tools", "deny"),
    ("sandbox", "workspace", "filesystem", "deny_read"),
    ("sandbox", "workspace", "filesystem", "deny_write"),
    ("sandbox", "workspace", "network", "deny_domains"),
    ("env", "deny"),
}


def _policy_dump(layer: ProviderPolicy | ProviderPolicyOverride) -> dict[str, Any]:
    if isinstance(layer, ProviderPolicyOverride):
        return layer.model_dump(mode="python", exclude_none=True, exclude_unset=True, warnings=False)
    return layer.model_dump(mode="python", exclude_none=True, warnings=False)


def _merge_policy_values(base: Any, update: Any, path: tuple[str, ...]) -> Any:
    if path in _UNION_PATHS:
        base_values = tuple(base or ())
        update_values = tuple(update or ())
        return _merge_string_tuples(base_values, update_values)
    if isinstance(base, Mapping) and isinstance(update, Mapping):
        merged: dict[str, Any] = deepcopy(dict(base))
        for key, value in update.items():
            if key in merged:
                merged[key] = _merge_policy_values(merged[key], value, path + (str(key),))
            else:
                merged[key] = deepcopy(value)
        return merged
    return deepcopy(update)


def merge_provider_policies(*layers: ProviderPolicy | ProviderPolicyOverride | None) -> ProviderPolicy:
    merged: dict[str, Any] = ProviderPolicy().model_dump(mode="python", warnings=False)
    for layer in layers:
        if layer is None:
            continue
        payload = _policy_dump(layer)
        merged = _merge_policy_values(merged, payload, ())
    return ProviderPolicy.model_validate(merged)


def _ensure_within_roots(
    *,
    field_path: str,
    entries: Sequence[str],
    allowed_roots: Sequence[str] | None,
    allow_symlink_escape: bool,
    workspace_root: Path,
) -> list[ProviderPolicyViolation]:
    if allowed_roots is None:
        return []
    allowed_resolved = [
        (root, *_resolved_policy_path(root, workspace_root))
        for root in allowed_roots
    ]
    violations: list[ProviderPolicyViolation] = []
    for entry in entries:
        resolved_entry, escaped_workspace = _resolved_policy_path(entry, workspace_root)
        if escaped_workspace and not allow_symlink_escape:
            violations.append(
                ProviderPolicyViolation(
                    field_path=field_path,
                    requested_value=entry,
                    constraint=f"must remain within workspace_root={str(workspace_root)!r} without symlink escape",
                    message=(
                        f"{field_path}={entry!r} escapes workspace_root={str(workspace_root)!r} "
                        "via symlink traversal"
                    ),
                )
            )
            continue
        permitted = False
        for raw_root, resolved_root, root_escaped in allowed_resolved:
            if root_escaped and not allow_symlink_escape:
                continue
            if resolved_entry.is_relative_to(resolved_root):
                permitted = True
                break
        if permitted:
            continue
        violations.append(
            ProviderPolicyViolation(
                field_path=field_path,
                requested_value=entry,
                constraint=f"strict allowed_roots={list(allowed_roots)!r}",
                message=f"{field_path}={entry!r} is outside strict allowed_roots={list(allowed_roots)!r}",
            )
        )
    return violations


def validate_against_strict_policy(
    policy: ProviderPolicy,
    strict: StrictProviderPolicy | None,
    *,
    step_name: str | None = None,
    workspace_root: Path | None = None,
) -> ProviderPolicy:
    resolved_workspace = (workspace_root or Path(".")).resolve(strict=False)
    candidate = ProviderPolicy.model_validate(policy.model_dump(mode="python", warnings=False))
    if strict is None:
        return candidate

    violations: list[ProviderPolicyViolation] = []

    if strict.permissions.allow_dangerous_bypass is False and candidate.permissions.allow_dangerous_bypass:
        violations.append(
            ProviderPolicyViolation(
                field_path="permissions.allow_dangerous_bypass",
                requested_value=candidate.permissions.allow_dangerous_bypass,
                constraint="strict permissions.allow_dangerous_bypass=False",
            )
        )
    if strict.permissions.disable_dangerous_bypass is True and not candidate.permissions.disable_dangerous_bypass:
        violations.append(
            ProviderPolicyViolation(
                field_path="permissions.disable_dangerous_bypass",
                requested_value=candidate.permissions.disable_dangerous_bypass,
                constraint="strict permissions.disable_dangerous_bypass=True",
            )
        )
    forbidden_allow = strict.permissions.forbidden_allow
    for allow_entry in candidate.permissions.allow:
        if allow_entry in forbidden_allow:
            violations.append(
                ProviderPolicyViolation(
                    field_path="permissions.allow",
                    requested_value=allow_entry,
                    constraint=f"strict forbidden_allow={list(forbidden_allow)!r}",
                )
            )

    if strict.sandbox.required and not candidate.sandbox.enabled:
        violations.append(
            ProviderPolicyViolation(
                field_path="sandbox.enabled",
                requested_value=candidate.sandbox.enabled,
                constraint="strict sandbox.required=True",
            )
        )
    if candidate.sandbox.mode not in strict.sandbox.allowed_modes:
        violations.append(
            ProviderPolicyViolation(
                field_path="sandbox.mode",
                requested_value=candidate.sandbox.mode,
                constraint=f"strict sandbox.allowed_modes={list(strict.sandbox.allowed_modes)!r}",
                message=(
                    f"sandbox.mode={candidate.sandbox.mode!r} exceeds strict "
                    f"sandbox.allowed_modes={list(strict.sandbox.allowed_modes)!r}"
                ),
            )
        )
    if candidate.permissions.mode == "full_auto_unsandboxed":
        if candidate.sandbox.mode != "danger_full_access":
            violations.append(
                ProviderPolicyViolation(
                    field_path="sandbox.mode",
                    requested_value=candidate.sandbox.mode,
                    constraint="permissions.mode='full_auto_unsandboxed' requires sandbox.mode='danger_full_access'",
                )
            )
        if strict.permissions.allow_dangerous_bypass is False:
            violations.append(
                ProviderPolicyViolation(
                    field_path="permissions.mode",
                    requested_value=candidate.permissions.mode,
                    constraint="strict policy forbids unsandboxed full auto",
                )
            )
        if "danger_full_access" not in strict.sandbox.allowed_modes:
            violations.append(
                ProviderPolicyViolation(
                    field_path="permissions.mode",
                    requested_value=candidate.permissions.mode,
                    constraint=(
                        "strict sandbox.allowed_modes must include 'danger_full_access' "
                        "for permissions.mode='full_auto_unsandboxed'"
                    ),
                )
            )

    filesystem_strict = strict.sandbox.workspace.filesystem
    violations.extend(
        _ensure_within_roots(
            field_path="sandbox.workspace.filesystem.allow_read",
            entries=candidate.sandbox.workspace.filesystem.allow_read,
            allowed_roots=filesystem_strict.allowed_read_roots,
            allow_symlink_escape=filesystem_strict.allow_symlink_escape,
            workspace_root=resolved_workspace,
        )
    )
    violations.extend(
        _ensure_within_roots(
            field_path="sandbox.workspace.filesystem.allow_write",
            entries=candidate.sandbox.workspace.filesystem.allow_write,
            allowed_roots=filesystem_strict.allowed_write_roots,
            allow_symlink_escape=filesystem_strict.allow_symlink_escape,
            workspace_root=resolved_workspace,
        )
    )

    network_strict = strict.sandbox.workspace.network
    if candidate.sandbox.workspace.network.mode not in network_strict.allowed_modes:
        violations.append(
            ProviderPolicyViolation(
                field_path="sandbox.workspace.network.mode",
                requested_value=candidate.sandbox.workspace.network.mode,
                constraint=f"strict allowed_modes={list(network_strict.allowed_modes)!r}",
            )
        )
    if network_strict.allow_local_binding is False and candidate.sandbox.workspace.network.allow_local_binding:
        violations.append(
            ProviderPolicyViolation(
                field_path="sandbox.workspace.network.allow_local_binding",
                requested_value=candidate.sandbox.workspace.network.allow_local_binding,
                constraint="strict allow_local_binding=False",
            )
        )
    if network_strict.allowed_domains is not None:
        for domain in candidate.sandbox.workspace.network.allow_domains:
            if not _domain_allowed(domain, network_strict.allowed_domains):
                violations.append(
                    ProviderPolicyViolation(
                        field_path="sandbox.workspace.network.allow_domains",
                        requested_value=domain,
                        constraint=f"strict allowed_domains={list(network_strict.allowed_domains)!r}",
                    )
                )

    if strict.env.allowed_set_keys is not None:
        for key in candidate.env.set:
            if key not in strict.env.allowed_set_keys:
                violations.append(
                    ProviderPolicyViolation(
                        field_path=f"env.set.{key}",
                        requested_value="<redacted>",
                        constraint=f"strict allowed_set_keys={list(strict.env.allowed_set_keys)!r}",
                    )
                )

    if violations:
        raise ProviderPolicyError(violations, step_name=step_name)

    permissions = candidate.permissions.model_copy(
        update={
            "deny": _merge_string_tuples(candidate.permissions.deny, strict.permissions.required_deny),
        }
    )
    filesystem = candidate.sandbox.workspace.filesystem.model_copy(
        update={
            "deny_read": _merge_string_tuples(
                candidate.sandbox.workspace.filesystem.deny_read,
                filesystem_strict.required_deny_read,
            ),
            "deny_write": _merge_string_tuples(
                candidate.sandbox.workspace.filesystem.deny_write,
                filesystem_strict.required_deny_write,
            ),
        }
    )
    network = candidate.sandbox.workspace.network.model_copy(
        update={
            "deny_domains": _merge_string_tuples(
                candidate.sandbox.workspace.network.deny_domains,
                network_strict.required_deny_domains,
            ),
        }
    )
    workspace = candidate.sandbox.workspace.model_copy(update={"filesystem": filesystem, "network": network})
    sandbox = candidate.sandbox.model_copy(update={"workspace": workspace})
    env = candidate.env.model_copy(
        update={"deny": _merge_string_tuples(candidate.env.deny, strict.env.required_deny or ())}
    )
    return candidate.model_copy(
        update={
            "permissions": permissions,
            "sandbox": sandbox,
            "env": env,
        }
    )


def policy_fingerprint(policy: ProviderPolicy) -> str:
    payload = policy.model_dump(mode="json", warnings=False)
    encoded = _safe_json(payload).encode("utf-8")
    return sha256(encoded).hexdigest()


__all__ = [
    "SYSTEM_DEFAULT_PROVIDER_POLICY",
    "ProviderPolicy",
    "ProviderPolicyOverride",
    "ResolvedProviderPolicy",
    "StrictProviderPolicy",
    "ModelPolicy",
    "PermissionPolicy",
    "SandboxPolicy",
    "WorkspacePolicy",
    "WorkspaceFilesystemPolicy",
    "WorkspaceNetworkPolicy",
    "EnvPolicy",
    "ToolPolicy",
    "InstructionPolicy",
    "TelemetryPolicy",
    "PolicyValidationMode",
    "ProviderPolicyError",
    "ProviderPolicyViolation",
    "ProviderPolicyCapabilityReport",
    "ProviderPolicyEmission",
    "merge_provider_policies",
    "validate_against_strict_policy",
    "policy_fingerprint",
]
