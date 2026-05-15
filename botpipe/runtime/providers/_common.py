"""Shared helpers for runtime-side CLI providers."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import os
import re
from pathlib import Path
import subprocess
from typing import Any, Mapping

from ...core.errors import FailureContext, ProviderExecutionError
from ...core.provider_policy import (
    ProviderPolicyEmission,
    ProviderPolicyValidationConfig,
    ResolvedProviderPolicy,
    _redact_secret_mapping,
    policy_fingerprint,
)
from ...core.providers.models import TokenUsage
from ...core.providers.turns import RenderedProviderTurn
from ...core.prompts import ResolvedPrompt
from ...core.stores.protocols import SessionBinding


_SAFE_STEP_KEY_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


def require_prompt_text(prompt: ResolvedPrompt, provider_name: str, step_name: str) -> str:
    """Return resolved prompt text or raise a provider execution error."""

    if prompt.text is None:
        prompt_ref = prompt.path or "<inline prompt>"
        raise ProviderExecutionError(
            f"provider '{provider_name}' cannot run step {step_name!r}: prompt {prompt_ref!r} did not resolve to text."
        )
    return prompt.text


def format_subprocess_streams(stdout: str, stderr: str) -> str:
    """Render stdout/stderr for error and debug surfaces."""

    sections: list[str] = []
    if stdout:
        sections.append(f"stdout:\n{stdout}")
    if stderr:
        sections.append(f"stderr:\n{stderr}")
    if not sections:
        return "[empty stdout/stderr]"
    return "\n\n".join(sections)


def ensure_session_provider_match(provider_name: str, binding: SessionBinding | None) -> None:
    """Reject attempts to resume a session across provider backends."""

    if binding is None:
        return
    seen_provider = binding.metadata.get("provider")
    if isinstance(seen_provider, str) and seen_provider != provider_name:
        raise ProviderExecutionError(
            f"provider '{provider_name}' cannot resume session {binding.session_id!r} from provider "
            f"'{seen_provider}'; resuming across providers is forbidden and a new run is required."
        )


def resumable_session_id(provider_name: str, session: SessionBinding | None) -> str | None:
    """Return the session id only when it belongs to the requested provider."""

    if session is None:
        return None
    seen_provider = session.metadata.get("provider")
    if seen_provider == provider_name and session.session_id:
        return session.session_id
    return None


def render_verifier_input(verifier_prompt_text: str, producer_raw_output: str) -> str:
    """Render the verifier prompt and producer output in one deterministic packet."""

    return (
        "<verifier_prompt>\n"
        f"{verifier_prompt_text}\n"
        "</verifier_prompt>\n\n"
        "<producer_raw_output>\n"
        f"{producer_raw_output}\n"
        "</producer_raw_output>\n"
    )


def build_session_binding(
    binding: SessionBinding,
    *,
    session_id: str,
    provider_name: str,
    provider_metadata: dict[str, Any],
    model: str | None,
    effort: str | None,
) -> SessionBinding:
    """Build a canonical provider session binding."""

    if not session_id:
        message = f"provider '{provider_name}' did not return a resumable session_id."
        raise ProviderExecutionError(
            message,
            failure_context=FailureContext(
                kind="provider_transport_failure",
                step_name="",
                provider_attributable=True,
                details={"error": message, "provider_failure_stage": "adapter_output"},
            ),
            retry_kind="provider_transport_failure",
        )

    metadata = deepcopy(binding.metadata)
    metadata["provider"] = provider_name
    metadata["mode"] = str(metadata.get("mode") or "persistent")
    metadata["provider_metadata"] = {
        key: deepcopy(value)
        for key, value in dict(provider_metadata).items()
        if key not in {"thread_id", "usage", "token_usage", "provider_usage"}
    }
    metadata["model_override"] = model
    metadata["effort_override"] = effort
    return SessionBinding(
        key=binding.key,
        session_id=session_id,
        provider=provider_name,
        provider_metadata=metadata["provider_metadata"],
        metadata=metadata,
    )


def extract_token_usage(payload: Any, *, source: str) -> TokenUsage | None:
    """Extract normalized token usage from a provider payload when present."""

    usage_payload = _find_usage_payload(payload)
    if usage_payload is None:
        return None
    return TokenUsage(
        input_tokens=_first_int(usage_payload, "input_tokens", "prompt_tokens", "inputTokenCount"),
        output_tokens=_first_int(usage_payload, "output_tokens", "completion_tokens", "outputTokenCount"),
        total_tokens=_first_int(usage_payload, "total_tokens", "totalTokenCount"),
        cached_input_tokens=_first_int(
            usage_payload,
            "cached_input_tokens",
            "cache_read_input_tokens",
            "cachedPromptTokens",
        ),
        reasoning_tokens=_resolve_reasoning_tokens(usage_payload),
        source=source,
        provider_raw=deepcopy(dict(usage_payload)),
    )


def _find_usage_payload(payload: Any) -> Mapping[str, Any] | None:
    if isinstance(payload, Mapping):
        for key in ("usage", "token_usage", "provider_usage"):
            value = payload.get(key)
            if isinstance(value, Mapping):
                return value
        for value in payload.values():
            found = _find_usage_payload(value)
            if found is not None:
                return found
        return None
    if isinstance(payload, (list, tuple)):
        for item in payload:
            found = _find_usage_payload(item)
            if found is not None:
                return found
    return None


def _first_int(payload: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        resolved = _coerce_int(value)
        if resolved is not None:
            return resolved
    return None


def _resolve_reasoning_tokens(payload: Mapping[str, Any]) -> int | None:
    direct = _first_int(payload, "reasoning_tokens")
    if direct is not None:
        return direct
    details = payload.get("output_tokens_details")
    if isinstance(details, Mapping):
        return _first_int(details, "reasoning_tokens")
    return None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


async def communicate_text_subprocess(
    process: asyncio.subprocess.Process,
    *,
    input_text: str | None = None,
) -> tuple[str, str]:
    """Communicate with a subprocess and clean it up correctly on cancellation."""

    try:
        stdin_payload = None if input_text is None else input_text.encode("utf-8")
        stdout_bytes, stderr_bytes = await process.communicate(stdin_payload)
    except asyncio.CancelledError:
        await terminate_text_subprocess(process)
        raise
    return stdout_bytes.decode("utf-8"), stderr_bytes.decode("utf-8")


async def terminate_text_subprocess(process: asyncio.subprocess.Process) -> None:
    """Terminate, then kill, a subprocess that is still running."""

    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=1.0)
        return
    except asyncio.TimeoutError:
        pass
    if process.returncode is not None:
        return
    try:
        process.kill()
    except ProcessLookupError:
        return
    await process.wait()


def run_text_subprocess(
    command: list[str],
    *,
    input_text: str | None = None,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> tuple[str, str, int]:
    """Run a subprocess synchronously for explicit compatibility-only paths."""

    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        env=None if env is None else dict(env),
        cwd=str(cwd) if cwd is not None else None,
    )
    return completed.stdout, completed.stderr, completed.returncode


def merge_subprocess_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Merge subprocess environment overrides over the ambient environment."""

    env = dict(os.environ)
    if overrides:
        env.update({str(key): str(value) for key, value in overrides.items()})
    return env


def build_policy_step_key(step_name: str, *, step_execution_id: str | None = None) -> str:
    """Build the stable run-scoped step key for provider policy artifacts."""

    base_step = step_name
    scope_name: str | None = None
    item_id: str | None = None
    visit: str | None = None
    if step_execution_id:
        parts = [part for part in step_execution_id.split(":") if part]
        if len(parts) == 2:
            base_step, visit = parts
        elif len(parts) >= 4:
            base_step, scope_name, item_id, visit = parts[0], parts[1], parts[2], parts[3]
    sections = [_safe_step_key_component(base_step or step_name)]
    if scope_name:
        sections.append(f"scope-{_safe_step_key_component(scope_name)}")
    if item_id:
        sections.append(f"item-{_safe_step_key_component(item_id)}")
    if visit:
        sections.append(f"visit-{_safe_step_key_component(visit)}")
    return "__".join(section for section in sections if section)


def write_policy_json(path: Path, payload: Any) -> None:
    """Persist deterministic provider policy JSON artifacts."""

    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def redacted_policy_payload(policy: ResolvedProviderPolicy) -> dict[str, Any]:
    """Return a JSON policy payload with sensitive env values redacted."""

    payload = policy.model_dump(mode="json")
    env_payload = payload.get("env")
    if isinstance(env_payload, dict):
        set_payload = env_payload.get("set")
        if isinstance(set_payload, dict):
            env_payload["set"] = _redact_secret_mapping({str(key): str(value) for key, value in set_payload.items()})
    return payload


def provider_policy_capability_decision(
    validation: ProviderPolicyValidationConfig,
    *,
    unsupported: tuple[str, ...],
    lossy: tuple[str, ...],
    unsafe: tuple[str, ...],
) -> str:
    """Resolve provider policy capability status from validation config."""

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


def raise_for_policy_capability_failure(emission: ProviderPolicyEmission) -> None:
    """Raise the canonical policy capability failure for any provider target."""

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
        f"provider policy capability validation failed for target {report.target!r} on step {report.step_name!r}: {details}"
    )


def provider_metadata_with_policy(
    provider_metadata: dict[str, Any],
    *,
    emission: ProviderPolicyEmission,
) -> dict[str, Any]:
    """Attach policy artifact metadata to provider metadata."""

    metadata = dict(provider_metadata)
    metadata["policy"] = {
        "effective_policy_file": str(emission.config_files["effective_policy"]),
        "capability_report_file": str(emission.config_files["capability_report"]),
        "policy_fingerprint": emission.capability_report.policy_fingerprint,
    }
    return metadata


def emit_policy_event(turn: RenderedProviderTurn, event_type: str, **fields: object) -> None:
    """Emit the canonical provider policy runtime event payload."""

    if turn.runtime_event_sink is None:
        return
    payload: dict[str, object] = {
        "step_name": turn.step_name,
        "turn_kind": turn.turn_kind,
    }
    if turn.step_execution_id is not None:
        payload["step_execution_id"] = turn.step_execution_id
    payload.update(fields)
    turn.runtime_event_sink(event_type, payload)


def emit_turn_policy(
    emitter: Any,
    turn: RenderedProviderTurn,
    *,
    provider_target: str,
    validation: ProviderPolicyValidationConfig,
    emit_kwargs: Mapping[str, Any] | None = None,
) -> ProviderPolicyEmission | None:
    """Emit provider policy artifacts and matching runtime events for one turn."""

    if turn.policy is None or turn.run_folder is None:
        return None
    step_key = build_policy_step_key(turn.step_name, step_execution_id=turn.step_execution_id)
    policy_root = turn.run_folder / "provider_policy" / step_key / provider_target
    effective_policy_path = policy_root / "effective_policy.json"
    capability_report_path = policy_root / "capability_report.json"
    try:
        emission = emitter.emit(
            turn.policy,
            run_dir=turn.run_folder,
            step_key=step_key,
            validation=validation,
            step_name=turn.step_name,
            **dict(emit_kwargs or {}),
        )
    except ProviderExecutionError:
        fingerprint = policy_fingerprint(turn.policy)
        emit_policy_event(
            turn,
            "provider_policy_emitted",
            provider_target=provider_target,
            policy_fingerprint=fingerprint,
            decision="fail",
            effective_policy_path=str(effective_policy_path),
            capability_report_path=str(capability_report_path),
        )
        emit_policy_event(
            turn,
            "provider_policy_capability_report",
            provider_target=provider_target,
            policy_fingerprint=fingerprint,
            decision="fail",
            capability_report_path=str(capability_report_path),
        )
        raise
    emit_policy_event(
        turn,
        "provider_policy_emitted",
        provider_target=provider_target,
        policy_fingerprint=emission.capability_report.policy_fingerprint,
        decision=emission.capability_report.decision,
        effective_policy_path=str(emission.config_files["effective_policy"]),
        capability_report_path=str(emission.config_files["capability_report"]),
    )
    emit_policy_event(
        turn,
        "provider_policy_capability_report",
        provider_target=provider_target,
        policy_fingerprint=emission.capability_report.policy_fingerprint,
        decision=emission.capability_report.decision,
        capability_report_path=str(emission.config_files["capability_report"]),
    )
    return emission


def structured_output_metadata(
    *,
    provider_name: str,
    delivery_mode: str,
    reason: str | None = None,
    schema_path: str | None = None,
) -> dict[str, Any]:
    """Build stable structured-output delivery metadata."""

    payload: dict[str, Any] = {
        "provider": provider_name,
        "delivery_mode": delivery_mode,
    }
    if reason is not None:
        payload["reason"] = reason
    if schema_path is not None:
        payload["schema_path"] = schema_path
    return payload


def _safe_step_key_component(value: str) -> str:
    normalized = _SAFE_STEP_KEY_PATTERN.sub("-", value.strip())
    normalized = normalized.strip("._-")
    return normalized or "step"
