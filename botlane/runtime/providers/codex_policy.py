"""Codex-specific provider policy emission."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from ...core.errors import ProviderExecutionError
from ...core.provider_policy import (
    EffectiveEnforcementReport,
    ProviderPolicyCapabilityReport,
    ProviderPolicyEmission,
    ProviderPolicyValidationConfig,
    ResolvedProviderPolicy,
    policy_fingerprint,
)


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


def _toml_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, Path):
        return _toml_literal(str(value))
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        items = ", ".join(f"{key} = {_toml_literal(item)}" for key, item in value.items())
        return "{ " + items + " }"
    raise TypeError(f"unsupported TOML value: {type(value)!r}")


def _codex_config_cli_args(payload: dict[str, Any]) -> tuple[str, ...]:
    args: list[str] = []
    for key, value in _flatten_config_payload(payload):
        args.append(f"--config={key}={_toml_literal(value)}")
    return tuple(args)


def _flatten_config_payload(payload: dict[str, Any], *, prefix: tuple[str, ...] = ()) -> tuple[tuple[str, Any], ...]:
    entries: list[tuple[str, Any]] = []
    for key, value in payload.items():
        path = (*prefix, str(key))
        if isinstance(value, dict):
            entries.extend(_flatten_config_payload(value, prefix=path))
        else:
            entries.append((".".join(path), value))
    return tuple(entries)


CODEX_PERMISSION_MODES = {
    "ask": "on-request",
    "full_auto_sandboxed": "never",
    "full_auto_unsandboxed": "never",
}

CODEX_SANDBOX_MODES = {
    "read_only": "read-only",
    "workspace_write": "workspace-write",
    "danger_full_access": "danger-full-access",
}


@dataclass
class _CodexEmissionContext:
    payload: dict[str, Any]
    unsupported: list[str] = field(default_factory=list)
    lossy: list[str] = field(default_factory=list)
    unsafe: list[str] = field(default_factory=list)


def _init_codex_emission(policy: ResolvedProviderPolicy) -> _CodexEmissionContext:
    payload = deepcopy(policy.codex)
    if not isinstance(payload, dict):
        payload = {}
    return _CodexEmissionContext(payload=payload)


def _emit_codex_model(ctx: _CodexEmissionContext, policy: ResolvedProviderPolicy) -> None:
    if policy.model.default is not None:
        ctx.payload["model"] = policy.model.default
    if policy.model.effort is not None:
        ctx.payload["model_reasoning_effort"] = policy.model.effort
    if policy.model.provider is not None:
        ctx.unsupported.append("model.provider is not supported by Codex policy emission")
    if policy.model.base_url is not None:
        ctx.unsupported.append("model.base_url is not supported by Codex policy emission")
    if policy.model.verbosity is not None:
        ctx.unsupported.append("model.verbosity is not supported by Codex policy emission")
    if policy.model.reasoning_summary is not None:
        ctx.unsupported.append("model.reasoning_summary is not supported by Codex policy emission")
    if policy.model.overrides:
        ctx.unsupported.append("model.overrides are not supported by Codex policy emission")


def _emit_codex_permission_mode(ctx: _CodexEmissionContext, policy: ResolvedProviderPolicy) -> str:
    permission_mode = policy.permissions.mode
    translated = CODEX_PERMISSION_MODES.get(permission_mode)
    if translated is None:
        ctx.unsupported.append(f"permissions.mode={permission_mode!r} is not supported by Codex policy emission")
        return permission_mode
    if permission_mode == "full_auto_unsandboxed" and not policy.permissions.allow_dangerous_bypass:
        raise ProviderExecutionError(
            "provider policy for 'codex' cannot emit full_auto_unsandboxed without allow_dangerous_bypass=True"
        )
    ctx.payload["approval_policy"] = translated
    return permission_mode


def _resolve_codex_sandbox_mode(
    ctx: _CodexEmissionContext,
    policy: ResolvedProviderPolicy,
    *,
    permission_mode: str,
) -> str | None:
    if not policy.sandbox.enabled:
        if policy.sandbox.required:
            raise ProviderExecutionError(
                "provider policy for 'codex' cannot emit sandbox.enabled=False when sandbox.required=True"
            )
        if permission_mode == "full_auto_unsandboxed":
            return CODEX_SANDBOX_MODES["danger_full_access"]
        ctx.unsupported.append("sandbox.enabled=False is not supported by Codex policy emission")
        return None

    translated = CODEX_SANDBOX_MODES.get(policy.sandbox.mode)
    if translated is None:
        ctx.unsupported.append(f"sandbox.mode={policy.sandbox.mode!r} is not supported by Codex policy emission")
        return None
    if policy.sandbox.mode == "danger_full_access" and not policy.permissions.allow_dangerous_bypass:
        raise ProviderExecutionError(
            "provider policy for 'codex' cannot emit danger_full_access without allow_dangerous_bypass=True"
        )
    if policy.sandbox.mode == "read_only" and policy.sandbox.workspace.filesystem.allow_write:
        ctx.lossy.append("sandbox.mode='read_only' ignores filesystem.allow_write in Codex")
    return translated


def _emit_codex_filesystem(
    ctx: _CodexEmissionContext,
    policy: ResolvedProviderPolicy,
    *,
    sandbox_mode: str | None,
) -> None:
    filesystem = policy.sandbox.workspace.filesystem
    if sandbox_mode == CODEX_SANDBOX_MODES["workspace_write"]:
        workspace_payload = dict(ctx.payload.get("sandbox_workspace_write", {}))
        workspace_payload["writable_roots"] = list(filesystem.allow_write)
        workspace_payload["network_access"] = bool(policy.sandbox.workspace.network.enabled)
        ctx.payload["sandbox_workspace_write"] = workspace_payload
    if filesystem.deny_read:
        ctx.unsupported.append("sandbox.workspace.filesystem.deny_read is not enforced by Codex")
    if filesystem.deny_write:
        ctx.unsupported.append("sandbox.workspace.filesystem.deny_write is not enforced by Codex")
    if filesystem.allow_read not in {(".",), ()}:
        ctx.unsafe.append("sandbox.workspace.filesystem.allow_read cannot be narrowed by Codex")


def _emit_codex_network(
    ctx: _CodexEmissionContext,
    policy: ResolvedProviderPolicy,
    *,
    sandbox_mode: str | None,
) -> None:
    network = policy.sandbox.workspace.network
    if network.allow_domains or network.deny_domains:
        ctx.unsupported.append("sandbox.workspace.network domain allow/deny filters are not enforced by Codex")
    if network.mode == "limited":
        ctx.unsafe.append("sandbox.workspace.network.mode='limited' expands to unrestricted network access in Codex")
    elif sandbox_mode == CODEX_SANDBOX_MODES["workspace_write"] and network.mode in {"none", "full"}:
        workspace_payload = dict(ctx.payload.get("sandbox_workspace_write", {}))
        workspace_payload["network_access"] = network.mode == "full"
        ctx.payload["sandbox_workspace_write"] = workspace_payload
    if network.allow_local_binding:
        ctx.unsupported.append("sandbox.workspace.network.allow_local_binding is not enforced by Codex")


def _emit_codex_unsupported_sections(ctx: _CodexEmissionContext, policy: ResolvedProviderPolicy) -> None:
    if policy.permissions.allow or policy.permissions.ask or policy.permissions.deny:
        ctx.unsupported.append("permission allow/ask/deny rules are not supported by Codex policy emission")
    if policy.tools.allow or policy.tools.ask or policy.tools.deny:
        ctx.unsupported.append("tool allow/ask/deny rules are not supported by Codex policy emission")
    if policy.instructions.files or policy.instructions.inline or policy.instructions.output_style:
        ctx.unsupported.append("instruction policy fields are not supported by Codex policy emission")
    if policy.telemetry.enabled or policy.telemetry.exporter or policy.telemetry.headers:
        ctx.unsupported.append("telemetry policy fields are not supported by Codex policy emission")


class CodexPolicyEmitter:
    """Emit Codex config and capability artifacts for one resolved policy."""

    def emit(
        self,
        policy: ResolvedProviderPolicy,
        *,
        run_dir: Path,
        step_key: str,
        validation: ProviderPolicyValidationConfig,
        step_name: str | None = None,
    ) -> ProviderPolicyEmission:
        policy_root = run_dir / "provider_policy" / step_key / "codex"
        policy_root.mkdir(parents=True, exist_ok=True)
        effective_policy_path = policy_root / "effective_policy.json"
        capability_report_path = policy_root / "capability_report.json"

        config_payload, unsupported, lossy, unsafe = self._build_config_payload(policy)
        cli_args = _codex_config_cli_args(config_payload)

        fingerprint = policy_fingerprint(policy)
        report = ProviderPolicyCapabilityReport(
            target="codex",
            step_name=step_name,
            policy_fingerprint=fingerprint,
            unsupported=tuple(unsupported),
            lossy=tuple(lossy),
            unsafe_expansions=tuple(unsafe),
            emitted_files=(str(effective_policy_path), str(capability_report_path)),
            emitted_cli_args=cli_args,
            effective_enforcement=EffectiveEnforcementReport(
                sandbox_mode=str(config_payload.get("sandbox_mode")) if config_payload.get("sandbox_mode") else None,
                write_roots=tuple(config_payload.get("sandbox_workspace_write", {}).get("writable_roots", ())),
                # Codex does not expose a read-root enforcement surface, so capability
                # reports must not echo requested allow_read roots as enforced state.
                read_roots=(),
                deny_read_enforced=False if policy.sandbox.workspace.filesystem.deny_read else None,
                deny_write_enforced=False if policy.sandbox.workspace.filesystem.deny_write else None,
                network_domain_filter_enforced=False
                if policy.sandbox.workspace.network.allow_domains or policy.sandbox.workspace.network.deny_domains
                else None,
                dangerous_bypass_disabled=False if policy.permissions.allow_dangerous_bypass else True,
            ),
            decision=_capability_decision(
                validation,
                unsupported=tuple(unsupported),
                lossy=tuple(lossy),
                unsafe=tuple(unsafe),
            ),
        )

        effective_payload = {
            "target": "codex",
            "step_name": step_name,
            "step_key": step_key,
            "policy_fingerprint": fingerprint,
            "policy": _redacted_policy_payload(policy),
            "codex_config": config_payload,
        }
        _json_dump(effective_policy_path, effective_payload)
        _json_dump(capability_report_path, report.model_dump(mode="json"))

        emission = ProviderPolicyEmission(
            target="codex",
            config_files={
                "effective_policy": effective_policy_path,
                "capability_report": capability_report_path,
            },
            cli_args=cli_args,
            env={},
            capability_report=report,
        )
        _raise_for_capability_failure(emission)
        return emission

    def _build_config_payload(
        self,
        policy: ResolvedProviderPolicy,
    ) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
        ctx = _init_codex_emission(policy)
        _emit_codex_model(ctx, policy)
        permission_mode = _emit_codex_permission_mode(ctx, policy)
        sandbox_mode = _resolve_codex_sandbox_mode(ctx, policy, permission_mode=permission_mode)
        if sandbox_mode is not None:
            ctx.payload["sandbox_mode"] = sandbox_mode
        _emit_codex_filesystem(ctx, policy, sandbox_mode=sandbox_mode)
        _emit_codex_network(ctx, policy, sandbox_mode=sandbox_mode)
        ctx.payload["shell_environment_policy"] = self._shell_environment_policy(policy, unsupported=ctx.unsupported)
        _emit_codex_unsupported_sections(ctx, policy)
        return ctx.payload, ctx.unsupported, ctx.lossy, ctx.unsafe

    def _shell_environment_policy(
        self,
        policy: ResolvedProviderPolicy,
        *,
        unsupported: list[str],
    ) -> dict[str, Any]:
        env_payload: dict[str, Any] = {
            "inherit": policy.env.inherit,
            "ignore_default_excludes": False,
        }
        if policy.env.deny:
            env_payload["exclude"] = list(policy.env.deny)
        if policy.env.set:
            env_payload["set"] = dict(policy.env.set)
        if policy.env.allow:
            unsupported.append("env.allow is not supported by Codex shell_environment_policy")
        return env_payload


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
        f"provider policy capability validation failed for target 'codex' on step {report.step_name!r}: {details}"
    )
