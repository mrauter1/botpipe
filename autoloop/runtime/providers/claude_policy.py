"""Claude-specific provider policy emission."""

from __future__ import annotations

from copy import deepcopy
import json
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


class ClaudeCapabilities(BaseModel):
    """Capability profile for Claude Code policy emission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supports_sandbox_filesystem: bool = True
    supports_sandbox_network_domains: bool = True
    supports_disable_bypass: bool = True


def _redact_secret_mapping(values: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in values.items():
        upper_key = key.upper()
        if any(marker in upper_key for marker in ("TOKEN", "SECRET", "KEY")):
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted


def _json_dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
        runtime_home = run_dir / "provider_policy" / "claude_runtime"
        runtime_home.mkdir(parents=True, exist_ok=True)

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
        _json_dump(settings_path, settings_payload)

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
            decision=_capability_decision(
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
            "policy": _redacted_policy_payload(policy),
            "claude_settings": settings_payload,
            "capabilities": self._capabilities.model_dump(mode="json"),
        }
        _json_dump(effective_policy_path, effective_payload)
        _json_dump(capability_report_path, report.model_dump(mode="json"))

        emission = ProviderPolicyEmission(
            target="claude",
            config_files={
                "settings": settings_path,
                "effective_policy": effective_policy_path,
                "capability_report": capability_report_path,
            },
            cli_args=tuple(cli_args),
            env=_claude_runtime_env(runtime_home, workspace_root=workspace_root),
            capability_report=report,
        )
        _raise_for_capability_failure(emission)
        return emission

    def _build_settings_payload(
        self,
        policy: ResolvedProviderPolicy,
        *,
        workspace_root: Path | None,
    ) -> tuple[dict[str, Any], list[str], list[str], list[str], list[str], EffectiveEnforcementReport]:
        unsupported: list[str] = []
        lossy: list[str] = []
        unsafe: list[str] = []

        payload = deepcopy(policy.claude)
        if not isinstance(payload, dict):
            payload = {}

        if policy.model.default is not None:
            payload["model"] = policy.model.default
        if policy.model.effort is not None:
            payload["effortLevel"] = policy.model.effort
        if policy.model.provider is not None:
            unsupported.append("model.provider is not supported by Claude policy emission")
        if policy.model.base_url is not None:
            unsupported.append("model.base_url is not supported by Claude policy emission")
        if policy.model.verbosity is not None:
            unsupported.append("model.verbosity is not supported by Claude policy emission")
        if policy.model.reasoning_summary is not None:
            unsupported.append("model.reasoning_summary is not supported by Claude policy emission")
        if policy.model.overrides:
            unsupported.append("model.overrides are not supported by Claude policy emission")

        if policy.instructions.output_style is not None:
            payload["outputStyle"] = policy.instructions.output_style
        if policy.instructions.files or policy.instructions.inline:
            unsupported.append("instruction policy files/inline fields are not supported by Claude policy emission")
        if policy.telemetry.enabled or policy.telemetry.exporter or policy.telemetry.headers:
            unsupported.append("telemetry policy fields are not supported by Claude policy emission")

        permissions_payload = dict(payload.get("permissions", {}))
        sandbox_payload = dict(payload.get("sandbox", {}))
        filesystem_payload = dict(sandbox_payload.get("filesystem", {}))
        network_payload = dict(sandbox_payload.get("network", {}))
        cli_args: list[str] = []

        permission_allow = list(permissions_payload.get("allow", []))
        permission_ask = list(permissions_payload.get("ask", []))
        permission_deny = list(permissions_payload.get("deny", []))

        _extend_unique(permission_allow, list(policy.permissions.allow))
        _extend_unique(permission_ask, list(policy.permissions.ask))
        _extend_unique(permission_deny, list(policy.permissions.deny))
        _extend_unique(permission_allow, list(policy.tools.allow))
        _extend_unique(permission_ask, list(policy.tools.ask))
        _extend_unique(permission_deny, list(policy.tools.deny))

        permission_mode = policy.permissions.mode
        if permission_mode == "ask":
            permissions_payload["defaultMode"] = "default"
        elif permission_mode == "auto_edit":
            permissions_payload["defaultMode"] = "acceptEdits"
        elif permission_mode == "full_auto_sandboxed":
            permissions_payload["defaultMode"] = "auto"
        elif permission_mode == "full_auto_unsandboxed":
            if not policy.permissions.allow_dangerous_bypass:
                raise ProviderExecutionError(
                    "provider policy for 'claude' cannot emit full_auto_unsandboxed without allow_dangerous_bypass=True"
                )
            if policy.permissions.disable_dangerous_bypass:
                raise ProviderExecutionError(
                    "provider policy for 'claude' cannot emit full_auto_unsandboxed with disable_dangerous_bypass=True"
                )
            permissions_payload["defaultMode"] = "bypassPermissions"
            cli_args.append("--dangerously-skip-permissions")
        elif permission_mode == "deny_all":
            permissions_payload["defaultMode"] = "dontAsk"
        else:
            unsupported.append(f"permissions.mode={permission_mode!r} is not supported by Claude policy emission")

        if policy.permissions.disable_dangerous_bypass:
            if self._capabilities.supports_disable_bypass:
                permissions_payload["disableBypassPermissionsMode"] = "disable"
            else:
                lossy.append(
                    "permissions.disable_dangerous_bypass could not be enforced natively by Claude capabilities"
                )

        if not policy.sandbox.enabled:
            if policy.sandbox.required:
                raise ProviderExecutionError(
                    "provider policy for 'claude' cannot emit sandbox.enabled=False when sandbox.required=True"
                )
            sandbox_payload["enabled"] = False
        elif policy.sandbox.mode == "read_only":
            sandbox_payload["enabled"] = True
            sandbox_payload["failIfUnavailable"] = policy.sandbox.required
            sandbox_payload["autoAllowBashIfSandboxed"] = permission_mode == "full_auto_sandboxed"
            if policy.sandbox.workspace.filesystem.allow_write:
                lossy.append("sandbox.mode='read_only' ignores filesystem.allow_write in Claude")
        elif policy.sandbox.mode == "workspace_write":
            sandbox_payload["enabled"] = True
            sandbox_payload["failIfUnavailable"] = policy.sandbox.required
            sandbox_payload["autoAllowBashIfSandboxed"] = permission_mode == "full_auto_sandboxed"
        elif policy.sandbox.mode == "danger_full_access":
            if not policy.permissions.allow_dangerous_bypass:
                raise ProviderExecutionError(
                    "provider policy for 'claude' cannot emit danger_full_access without allow_dangerous_bypass=True"
                )
            sandbox_payload["enabled"] = False
            sandbox_payload["allowUnsandboxedCommands"] = True
        else:
            unsupported.append(f"sandbox.mode={policy.sandbox.mode!r} is not supported by Claude policy emission")

        if policy.permissions.disable_dangerous_bypass and permission_mode != "full_auto_unsandboxed":
            sandbox_payload["allowUnsandboxedCommands"] = False

        filesystem = policy.sandbox.workspace.filesystem
        emitted_allow_read = _filesystem_entries_for_emission(filesystem.allow_read, workspace_root=workspace_root)
        emitted_allow_write = _filesystem_entries_for_emission(filesystem.allow_write, workspace_root=workspace_root)
        emitted_deny_read = _filesystem_entries_for_emission(filesystem.deny_read, workspace_root=workspace_root)
        emitted_deny_write = _filesystem_entries_for_emission(filesystem.deny_write, workspace_root=workspace_root)
        native_filesystem = self._capabilities.supports_sandbox_filesystem and bool(sandbox_payload.get("enabled"))
        if native_filesystem:
            filesystem_payload["allowRead"] = list(emitted_allow_read)
            if policy.sandbox.mode != "read_only":
                filesystem_payload["allowWrite"] = list(emitted_allow_write)
            if emitted_deny_read:
                filesystem_payload["denyRead"] = list(emitted_deny_read)
            if emitted_deny_write:
                filesystem_payload["denyWrite"] = list(emitted_deny_write)
        else:
            if bool(sandbox_payload.get("enabled")) and not self._capabilities.supports_sandbox_filesystem:
                lossy.append("sandbox.filesystem native enforcement unavailable; emitted Read/Edit permission rules only")
            _extend_unique(permission_allow, [_read_rule(path) for path in emitted_allow_read])
            if policy.sandbox.mode != "read_only":
                _extend_unique(permission_allow, [_edit_rule(path) for path in emitted_allow_write])

        _extend_unique(permission_deny, [_read_rule(path) for path in emitted_deny_read])
        _extend_unique(permission_deny, [_edit_rule(path) for path in emitted_deny_write])

        network = policy.sandbox.workspace.network
        if policy.sandbox.workspace.network.allow_local_binding:
            network_payload["allowLocalBinding"] = True
        native_network = self._capabilities.supports_sandbox_network_domains and bool(sandbox_payload.get("enabled"))
        if native_network:
            if network.mode in {"none", "limited"}:
                network_payload["allowedDomains"] = list(network.allow_domains)
            elif network.allow_domains:
                network_payload["allowedDomains"] = list(network.allow_domains)
            if network.deny_domains:
                network_payload["deniedDomains"] = list(network.deny_domains)
        else:
            if network.mode == "none":
                lossy.append("sandbox.network.mode='none' could not be enforced natively by Claude capabilities")
            elif network.allow_domains or network.deny_domains:
                lossy.append("sandbox.network domain enforcement unavailable; emitted WebFetch permission rules only")
        _extend_unique(permission_allow, [_webfetch_rule(domain) for domain in network.allow_domains])
        _extend_unique(permission_deny, [_webfetch_rule(domain) for domain in network.deny_domains])

        if filesystem_payload:
            sandbox_payload["filesystem"] = filesystem_payload
        if network_payload:
            sandbox_payload["network"] = network_payload
        if sandbox_payload:
            payload["sandbox"] = sandbox_payload

        if permission_allow:
            permissions_payload["allow"] = permission_allow
        if permission_ask:
            permissions_payload["ask"] = permission_ask
        if permission_deny:
            permissions_payload["deny"] = permission_deny
        payload["permissions"] = permissions_payload

        if policy.env.set:
            payload["env"] = dict(policy.env.set)

        effective = EffectiveEnforcementReport(
            sandbox_mode=policy.sandbox.mode if policy.sandbox.enabled else None,
            write_roots=tuple(emitted_allow_write) if native_filesystem and policy.sandbox.mode != "read_only" else (),
            read_roots=tuple(emitted_allow_read) if native_filesystem else (),
            deny_read_enforced=True if native_filesystem and filesystem.deny_read else (False if filesystem.deny_read else None),
            deny_write_enforced=True
            if native_filesystem and filesystem.deny_write
            else (False if filesystem.deny_write else None),
            network_domain_filter_enforced=True
            if native_network and (network.allow_domains or network.deny_domains)
            else (False if (network.allow_domains or network.deny_domains) else None),
            dangerous_bypass_disabled=True
            if policy.permissions.disable_dangerous_bypass and self._capabilities.supports_disable_bypass
            else (False if policy.permissions.disable_dangerous_bypass else None),
        )
        return payload, cli_args, unsupported, lossy, unsafe, effective


def _claude_runtime_env(runtime_home: Path, *, workspace_root: Path | None) -> dict[str, str]:
    env = {
        "CLAUDE_CONFIG_DIR": str(runtime_home),
    }
    if workspace_root is not None:
        env["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"] = "1"
    return env


def _redacted_policy_payload(policy: ResolvedProviderPolicy) -> dict[str, Any]:
    payload = policy.model_dump(mode="json")
    env_payload = payload.get("env")
    if isinstance(env_payload, dict):
        set_payload = env_payload.get("set")
        if isinstance(set_payload, dict):
            env_payload["set"] = _redact_secret_mapping({str(key): str(value) for key, value in set_payload.items()})
    return payload


def _capability_decision(
    validation: ProviderPolicyValidationConfig,
    *,
    unsupported: tuple[str, ...],
    lossy: tuple[str, ...],
    unsafe: tuple[str, ...],
) -> str:
    if unsupported and validation.unsupported == "fail":
        return "fail"
    if lossy and validation.lossy_mapping == "fail":
        return "fail"
    if unsafe and validation.unsafe_expansion == "fail":
        return "fail"
    if unsupported and validation.unsupported == "warn":
        return "warn"
    if lossy and validation.lossy_mapping == "warn":
        return "warn"
    if unsafe and validation.unsafe_expansion == "warn":
        return "warn"
    return "ok"


def _raise_for_capability_failure(emission: ProviderPolicyEmission) -> None:
    report = emission.capability_report
    if report.decision != "fail":
        return
    sections: list[str] = []
    if report.unsupported:
        sections.append("unsupported: " + "; ".join(report.unsupported))
    if report.lossy:
        sections.append("lossy: " + "; ".join(report.lossy))
    if report.unsafe_expansions:
        sections.append("unsafe: " + "; ".join(report.unsafe_expansions))
    details = " | ".join(sections) if sections else "capability validation failed"
    raise ProviderExecutionError(
        f"provider policy capability validation failed for target 'claude' on step {report.step_name!r}: {details}"
    )
