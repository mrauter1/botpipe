"""Claude-specific provider policy emission."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ...core.errors import ProviderExecutionError
from ...core.provider_policy import (
    EffectiveEnforcementReport,
    ProviderPolicyCapabilityReport,
    ProviderPolicyEmission,
    ProviderPolicyValidationConfig,
    ResolvedProviderPolicy,
    policy_fingerprint,
)
from ._common import (
    provider_policy_capability_decision,
    raise_for_policy_capability_failure,
    redacted_policy_payload,
    write_policy_json,
)


class ClaudeCapabilities(BaseModel):
    """Capability profile for Claude Code policy emission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supports_sandbox_filesystem: bool = True
    supports_sandbox_network_domains: bool = True
    supports_disable_bypass: bool = True


def _extend_unique(values: list[str], additions: list[str] | tuple[str, ...]) -> None:
    seen = set(values)
    for entry in additions:
        if entry in seen:
            continue
        seen.add(entry)
        values.append(entry)


def _claude_permission_path(path: str) -> str:
    if path.startswith(("//", "~/", "./")):
        return path
    if path.startswith("/"):
        return f"//{path.lstrip('/')}"
    return path


def _read_rule(path: str) -> str:
    return f"Read({_claude_permission_path(path)})"


def _edit_rule(path: str) -> str:
    return f"Edit({_claude_permission_path(path)})"


def _webfetch_rule(domain: str) -> str:
    return f"WebFetch(domain:{domain})"


def _resolve_workspace_policy_path(path: str, workspace_root: Path) -> str:
    raw_path = Path(path)
    candidate = raw_path if raw_path.is_absolute() else workspace_root / raw_path
    return str(candidate.resolve(strict=False))


def _filesystem_entries_for_emission(
    entries: tuple[str, ...],
    *,
    workspace_root: Path | None,
) -> tuple[str, ...]:
    if workspace_root is None:
        return entries
    resolved_root = workspace_root.resolve(strict=False)
    return tuple(_resolve_workspace_policy_path(entry, resolved_root) for entry in entries)


CLAUDE_PERMISSION_MODES = {
    "ask": "default",
    "auto_edit": "acceptEdits",
    "full_auto_sandboxed": "auto",
    "deny_all": "dontAsk",
}


@dataclass
class _ClaudeEmissionContext:
    payload: dict[str, Any]
    unsupported: list[str] = field(default_factory=list)
    lossy: list[str] = field(default_factory=list)
    unsafe: list[str] = field(default_factory=list)
    cli_args: list[str] = field(default_factory=list)
    permissions_payload: dict[str, Any] = field(default_factory=dict)
    sandbox_payload: dict[str, Any] = field(default_factory=dict)
    filesystem_payload: dict[str, Any] = field(default_factory=dict)
    network_payload: dict[str, Any] = field(default_factory=dict)
    permission_allow: list[str] = field(default_factory=list)
    permission_ask: list[str] = field(default_factory=list)
    permission_deny: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ClaudeFilesystemState:
    emitted_allow_read: tuple[str, ...]
    emitted_allow_write: tuple[str, ...]
    native_filesystem: bool


@dataclass(frozen=True)
class _ClaudeNetworkState:
    native_network: bool


def _init_claude_emission(policy: ResolvedProviderPolicy) -> _ClaudeEmissionContext:
    payload = deepcopy(policy.claude)
    if not isinstance(payload, dict):
        payload = {}
    permissions_payload = dict(payload.get("permissions", {}))
    sandbox_payload = dict(payload.get("sandbox", {}))
    return _ClaudeEmissionContext(
        payload=payload,
        permissions_payload=permissions_payload,
        sandbox_payload=sandbox_payload,
        filesystem_payload=dict(sandbox_payload.get("filesystem", {})),
        network_payload=dict(sandbox_payload.get("network", {})),
        permission_allow=list(permissions_payload.get("allow", [])),
        permission_ask=list(permissions_payload.get("ask", [])),
        permission_deny=list(permissions_payload.get("deny", [])),
    )


def _emit_claude_model(ctx: _ClaudeEmissionContext, policy: ResolvedProviderPolicy) -> None:
    if policy.model.default is not None:
        ctx.payload["model"] = policy.model.default
    if policy.model.effort is not None:
        ctx.payload["effortLevel"] = policy.model.effort
    if policy.model.provider is not None:
        ctx.unsupported.append("model.provider is not supported by Claude policy emission")
    if policy.model.base_url is not None:
        ctx.unsupported.append("model.base_url is not supported by Claude policy emission")
    if policy.model.verbosity is not None:
        ctx.unsupported.append("model.verbosity is not supported by Claude policy emission")
    if policy.model.reasoning_summary is not None:
        ctx.unsupported.append("model.reasoning_summary is not supported by Claude policy emission")
    if policy.model.overrides:
        ctx.unsupported.append("model.overrides are not supported by Claude policy emission")


def _emit_claude_instruction_and_telemetry_notes(
    ctx: _ClaudeEmissionContext,
    policy: ResolvedProviderPolicy,
) -> None:
    if policy.instructions.output_style is not None:
        ctx.payload["outputStyle"] = policy.instructions.output_style
    if policy.instructions.files or policy.instructions.inline:
        ctx.unsupported.append("instruction policy files/inline fields are not supported by Claude policy emission")
    if policy.telemetry.enabled or policy.telemetry.exporter or policy.telemetry.headers:
        ctx.unsupported.append("telemetry policy fields are not supported by Claude policy emission")


def _extend_claude_permission_rules(ctx: _ClaudeEmissionContext, policy: ResolvedProviderPolicy) -> None:
    _extend_unique(ctx.permission_allow, list(policy.permissions.allow))
    _extend_unique(ctx.permission_ask, list(policy.permissions.ask))
    _extend_unique(ctx.permission_deny, list(policy.permissions.deny))
    _extend_unique(ctx.permission_allow, list(policy.tools.allow))
    _extend_unique(ctx.permission_ask, list(policy.tools.ask))
    _extend_unique(ctx.permission_deny, list(policy.tools.deny))


def _emit_claude_permissions(
    ctx: _ClaudeEmissionContext,
    policy: ResolvedProviderPolicy,
    *,
    capabilities: ClaudeCapabilities,
) -> str:
    _extend_claude_permission_rules(ctx, policy)
    permission_mode = policy.permissions.mode
    translated = CLAUDE_PERMISSION_MODES.get(permission_mode)
    if translated is not None:
        ctx.permissions_payload["defaultMode"] = translated
    elif permission_mode == "full_auto_unsandboxed":
        if not policy.permissions.allow_dangerous_bypass:
            raise ProviderExecutionError(
                "provider policy for 'claude' cannot emit full_auto_unsandboxed without allow_dangerous_bypass=True"
            )
        if policy.permissions.disable_dangerous_bypass:
            raise ProviderExecutionError(
                "provider policy for 'claude' cannot emit full_auto_unsandboxed with disable_dangerous_bypass=True"
            )
        ctx.permissions_payload["defaultMode"] = "bypassPermissions"
        ctx.cli_args.append("--dangerously-skip-permissions")
    else:
        ctx.unsupported.append(f"permissions.mode={permission_mode!r} is not supported by Claude policy emission")

    if policy.permissions.disable_dangerous_bypass:
        if capabilities.supports_disable_bypass:
            ctx.permissions_payload["disableBypassPermissionsMode"] = "disable"
        else:
            ctx.lossy.append("permissions.disable_dangerous_bypass could not be enforced natively by Claude capabilities")
    return permission_mode


def _emit_claude_sandbox(
    ctx: _ClaudeEmissionContext,
    policy: ResolvedProviderPolicy,
    *,
    permission_mode: str,
) -> bool:
    if not policy.sandbox.enabled:
        if policy.sandbox.required:
            raise ProviderExecutionError(
                "provider policy for 'claude' cannot emit sandbox.enabled=False when sandbox.required=True"
            )
        ctx.sandbox_payload["enabled"] = False
    elif policy.sandbox.mode in {"read_only", "workspace_write"}:
        ctx.sandbox_payload["enabled"] = True
        ctx.sandbox_payload["failIfUnavailable"] = policy.sandbox.required
        ctx.sandbox_payload["autoAllowBashIfSandboxed"] = permission_mode == "full_auto_sandboxed"
        if policy.sandbox.mode == "read_only" and policy.sandbox.workspace.filesystem.allow_write:
            ctx.lossy.append("sandbox.mode='read_only' ignores filesystem.allow_write in Claude")
    elif policy.sandbox.mode == "danger_full_access":
        if not policy.permissions.allow_dangerous_bypass:
            raise ProviderExecutionError(
                "provider policy for 'claude' cannot emit danger_full_access without allow_dangerous_bypass=True"
            )
        ctx.sandbox_payload["enabled"] = False
        ctx.sandbox_payload["allowUnsandboxedCommands"] = True
    else:
        ctx.unsupported.append(f"sandbox.mode={policy.sandbox.mode!r} is not supported by Claude policy emission")

    if policy.permissions.disable_dangerous_bypass and permission_mode != "full_auto_unsandboxed":
        ctx.sandbox_payload["allowUnsandboxedCommands"] = False
    return bool(ctx.sandbox_payload.get("enabled"))


def _emit_claude_filesystem(
    ctx: _ClaudeEmissionContext,
    policy: ResolvedProviderPolicy,
    *,
    workspace_root: Path | None,
    capabilities: ClaudeCapabilities,
    sandbox_enabled: bool,
) -> _ClaudeFilesystemState:
    filesystem = policy.sandbox.workspace.filesystem
    emitted_allow_read = _filesystem_entries_for_emission(filesystem.allow_read, workspace_root=workspace_root)
    emitted_allow_write = _filesystem_entries_for_emission(filesystem.allow_write, workspace_root=workspace_root)
    emitted_deny_read = _filesystem_entries_for_emission(filesystem.deny_read, workspace_root=workspace_root)
    emitted_deny_write = _filesystem_entries_for_emission(filesystem.deny_write, workspace_root=workspace_root)
    native_filesystem = capabilities.supports_sandbox_filesystem and sandbox_enabled
    if native_filesystem:
        ctx.filesystem_payload["allowRead"] = list(emitted_allow_read)
        if policy.sandbox.mode != "read_only":
            ctx.filesystem_payload["allowWrite"] = list(emitted_allow_write)
        if emitted_deny_read:
            ctx.filesystem_payload["denyRead"] = list(emitted_deny_read)
        if emitted_deny_write:
            ctx.filesystem_payload["denyWrite"] = list(emitted_deny_write)
    else:
        if sandbox_enabled and not capabilities.supports_sandbox_filesystem:
            ctx.lossy.append("sandbox.filesystem native enforcement unavailable; emitted Read/Edit permission rules only")
        _extend_unique(ctx.permission_allow, [_read_rule(path) for path in emitted_allow_read])
        if policy.sandbox.mode != "read_only":
            _extend_unique(ctx.permission_allow, [_edit_rule(path) for path in emitted_allow_write])

    _extend_unique(ctx.permission_deny, [_read_rule(path) for path in emitted_deny_read])
    _extend_unique(ctx.permission_deny, [_edit_rule(path) for path in emitted_deny_write])
    return _ClaudeFilesystemState(
        emitted_allow_read=emitted_allow_read,
        emitted_allow_write=emitted_allow_write,
        native_filesystem=native_filesystem,
    )


def _emit_claude_network(
    ctx: _ClaudeEmissionContext,
    policy: ResolvedProviderPolicy,
    *,
    capabilities: ClaudeCapabilities,
    sandbox_enabled: bool,
) -> _ClaudeNetworkState:
    network = policy.sandbox.workspace.network
    if network.allow_local_binding:
        ctx.network_payload["allowLocalBinding"] = True
    native_network = capabilities.supports_sandbox_network_domains and sandbox_enabled
    if native_network:
        if network.mode in {"none", "limited"}:
            ctx.network_payload["allowedDomains"] = list(network.allow_domains)
        elif network.allow_domains:
            ctx.network_payload["allowedDomains"] = list(network.allow_domains)
        if network.deny_domains:
            ctx.network_payload["deniedDomains"] = list(network.deny_domains)
    else:
        if network.mode == "none":
            ctx.lossy.append("sandbox.network.mode='none' could not be enforced natively by Claude capabilities")
        elif network.allow_domains or network.deny_domains:
            ctx.lossy.append("sandbox.network domain enforcement unavailable; emitted WebFetch permission rules only")
    _extend_unique(ctx.permission_allow, [_webfetch_rule(domain) for domain in network.allow_domains])
    _extend_unique(ctx.permission_deny, [_webfetch_rule(domain) for domain in network.deny_domains])
    return _ClaudeNetworkState(native_network=native_network)


def _emit_claude_env(ctx: _ClaudeEmissionContext, policy: ResolvedProviderPolicy) -> None:
    if ctx.filesystem_payload:
        ctx.sandbox_payload["filesystem"] = ctx.filesystem_payload
    if ctx.network_payload:
        ctx.sandbox_payload["network"] = ctx.network_payload
    if ctx.sandbox_payload:
        ctx.payload["sandbox"] = ctx.sandbox_payload

    if ctx.permission_allow:
        ctx.permissions_payload["allow"] = ctx.permission_allow
    if ctx.permission_ask:
        ctx.permissions_payload["ask"] = ctx.permission_ask
    if ctx.permission_deny:
        ctx.permissions_payload["deny"] = ctx.permission_deny
    ctx.payload["permissions"] = ctx.permissions_payload

    if policy.env.set:
        ctx.payload["env"] = dict(policy.env.set)


def _claude_effective_report(
    policy: ResolvedProviderPolicy,
    *,
    filesystem_state: _ClaudeFilesystemState,
    network_state: _ClaudeNetworkState,
    capabilities: ClaudeCapabilities,
) -> EffectiveEnforcementReport:
    filesystem = policy.sandbox.workspace.filesystem
    network = policy.sandbox.workspace.network
    return EffectiveEnforcementReport(
        sandbox_mode=policy.sandbox.mode if policy.sandbox.enabled else None,
        write_roots=(
            tuple(filesystem_state.emitted_allow_write)
            if filesystem_state.native_filesystem and policy.sandbox.mode != "read_only"
            else ()
        ),
        read_roots=tuple(filesystem_state.emitted_allow_read) if filesystem_state.native_filesystem else (),
        deny_read_enforced=True
        if filesystem_state.native_filesystem and filesystem.deny_read
        else (False if filesystem.deny_read else None),
        deny_write_enforced=True
        if filesystem_state.native_filesystem and filesystem.deny_write
        else (False if filesystem.deny_write else None),
        network_domain_filter_enforced=True
        if network_state.native_network and (network.allow_domains or network.deny_domains)
        else (False if (network.allow_domains or network.deny_domains) else None),
        dangerous_bypass_disabled=True
        if policy.permissions.disable_dangerous_bypass and capabilities.supports_disable_bypass
        else (False if policy.permissions.disable_dangerous_bypass else None),
    )


class ClaudePolicyEmitter:
    """Emit Claude Code settings and capability artifacts for one resolved policy."""

    def __init__(self, *, capabilities: ClaudeCapabilities | None = None) -> None:
        self._capabilities = capabilities or ClaudeCapabilities()

    @property
    def capabilities(self) -> ClaudeCapabilities:
        return self._capabilities

    def emit(
        self,
        policy: ResolvedProviderPolicy,
        *,
        run_dir: Path,
        step_key: str,
        validation: ProviderPolicyValidationConfig,
        step_name: str | None = None,
        workspace_root: Path | None = None,
    ) -> ProviderPolicyEmission:
        policy_root = run_dir / "provider_policy" / step_key / "claude"
        policy_root.mkdir(parents=True, exist_ok=True)
        settings_path = policy_root / "settings.json"
        effective_policy_path = policy_root / "effective_policy.json"
        capability_report_path = policy_root / "capability_report.json"

        settings_payload, cli_args, unsupported, lossy, unsafe, effective = self._build_settings_payload(
            policy,
            workspace_root=workspace_root,
        )
        cli_args = [
            "--settings",
            str(settings_path),
            *(["--add-dir", str(workspace_root.resolve(strict=False))] if workspace_root is not None else []),
            *cli_args,
        ]
        write_policy_json(settings_path, settings_payload)

        fingerprint = policy_fingerprint(policy)
        report = ProviderPolicyCapabilityReport(
            target="claude",
            step_name=step_name,
            policy_fingerprint=fingerprint,
            unsupported=tuple(unsupported),
            lossy=tuple(lossy),
            unsafe_expansions=tuple(unsafe),
            emitted_files=(str(settings_path), str(effective_policy_path), str(capability_report_path)),
            emitted_cli_args=tuple(cli_args),
            effective_enforcement=effective,
            decision=provider_policy_capability_decision(
                validation,
                unsupported=tuple(unsupported),
                lossy=tuple(lossy),
                unsafe=tuple(unsafe),
            ),
        )

        effective_payload = {
            "target": "claude",
            "step_name": step_name,
            "step_key": step_key,
            "policy_fingerprint": fingerprint,
            "policy": redacted_policy_payload(policy),
            "claude_settings": settings_payload,
            "capabilities": self._capabilities.model_dump(mode="json"),
        }
        write_policy_json(effective_policy_path, effective_payload)
        write_policy_json(capability_report_path, report.model_dump(mode="json"))

        emission = ProviderPolicyEmission(
            target="claude",
            config_files={
                "settings": settings_path,
                "effective_policy": effective_policy_path,
                "capability_report": capability_report_path,
            },
            cli_args=tuple(cli_args),
            env=_claude_env(workspace_root=workspace_root),
            capability_report=report,
        )
        raise_for_policy_capability_failure(emission)
        return emission

    def _build_settings_payload(
        self,
        policy: ResolvedProviderPolicy,
        *,
        workspace_root: Path | None,
    ) -> tuple[dict[str, Any], list[str], list[str], list[str], list[str], EffectiveEnforcementReport]:
        ctx = _init_claude_emission(policy)
        _emit_claude_model(ctx, policy)
        _emit_claude_instruction_and_telemetry_notes(ctx, policy)
        permission_mode = _emit_claude_permissions(ctx, policy, capabilities=self._capabilities)
        sandbox_enabled = _emit_claude_sandbox(ctx, policy, permission_mode=permission_mode)
        filesystem_state = _emit_claude_filesystem(
            ctx,
            policy,
            workspace_root=workspace_root,
            capabilities=self._capabilities,
            sandbox_enabled=sandbox_enabled,
        )
        network_state = _emit_claude_network(
            ctx,
            policy,
            capabilities=self._capabilities,
            sandbox_enabled=sandbox_enabled,
        )
        _emit_claude_env(ctx, policy)
        effective = _claude_effective_report(
            policy,
            filesystem_state=filesystem_state,
            network_state=network_state,
            capabilities=self._capabilities,
        )
        return ctx.payload, ctx.cli_args, ctx.unsupported, ctx.lossy, ctx.unsafe, effective


def _claude_env(*, workspace_root: Path | None) -> dict[str, str]:
    env: dict[str, str] = {}
    if workspace_root is not None:
        env["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"] = "1"
    return env
