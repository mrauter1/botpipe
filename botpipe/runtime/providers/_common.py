"""Shared helpers for runtime-side CLI providers."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import os
import re
import signal
import threading
from pathlib import Path
import subprocess
from typing import Any, Mapping

from ...core.errors import FailureContext, ProviderExecutionError
from ...core.process_containment import ProcessContainment
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
_MAX_PROVIDER_STREAM_BYTES = 1024 * 1024
_PROCESS_CONTAINMENTS: dict[int, ProcessContainment] = {}
_OWNED_PROCESS_GROUPS: dict[int, int] = {}


def require_prompt_text(
    prompt: ResolvedPrompt, provider_name: str, step_name: str
) -> str:
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


def ensure_session_provider_match(
    provider_name: str, binding: SessionBinding | None
) -> None:
    """Reject attempts to resume a session across provider backends."""

    if binding is None:
        return
    seen_provider = binding.metadata.get("provider")
    if isinstance(seen_provider, str) and seen_provider != provider_name:
        raise ProviderExecutionError(
            f"provider '{provider_name}' cannot resume session {binding.session_id!r} from provider "
            f"'{seen_provider}'; resuming across providers is forbidden and a new run is required."
        )


def resumable_session_id(
    provider_name: str, session: SessionBinding | None
) -> str | None:
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
        input_tokens=_first_int(
            usage_payload, "input_tokens", "prompt_tokens", "inputTokenCount"
        ),
        output_tokens=_first_int(
            usage_payload, "output_tokens", "completion_tokens", "outputTokenCount"
        ),
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
    """Stream bounded tails and clean up the owned tree on cancellation."""
    stdout = getattr(process, "stdout", None)
    stderr = getattr(process, "stderr", None)
    if not isinstance(stdout, asyncio.StreamReader) or not isinstance(
        stderr, asyncio.StreamReader
    ):
        try:
            out, err = await process.communicate(
                None if input_text is None else input_text.encode()
            )
        except BaseException:
            await terminate_text_subprocess(process)
            raise
        finally:
            if process.returncode is not None:
                close_provider_subprocess_containment(process)
        return _bounded_text(out), _bounded_text(err)

    async def read_tail(reader):
        tail = bytearray()
        truncated = False
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            tail.extend(chunk)
            if len(tail) > _MAX_PROVIDER_STREAM_BYTES:
                del tail[: len(tail) - _MAX_PROVIDER_STREAM_BYTES]
                truncated = True
        return bytes(tail), truncated

    async def write():
        stream = getattr(process, "stdin", None)
        if stream is None:
            return
        try:
            if input_text is not None:
                stream.write(input_text.encode())
                await stream.drain()
        except (BrokenPipeError, ConnectionResetError, ProcessLookupError):
            pass
        finally:
            stream.close()

    tasks = [
        asyncio.create_task(write()),
        asyncio.create_task(read_tail(stdout)),
        asyncio.create_task(read_tail(stderr)),
    ]
    try:
        await _wait_for_process_leader(process, tasks)
        await _cleanup_provider_subprocess_descendants(process)
        _, (out, out_cut), (err, err_cut) = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await terminate_text_subprocess(process)
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        if process.returncode is not None:
            close_provider_subprocess_containment(process)
    marker = b"[... provider stream truncated ...]\n"
    return (marker + out if out_cut else out).decode(errors="replace"), (
        marker + err if err_cut else err
    ).decode(errors="replace")


def _bounded_text(value: bytes) -> str:
    if len(value) <= _MAX_PROVIDER_STREAM_BYTES:
        return value.decode("utf-8", errors="replace")
    return "[... provider stream truncated ...]\n" + value[
        -_MAX_PROVIDER_STREAM_BYTES:
    ].decode("utf-8", errors="replace")


async def create_provider_subprocess_exec(
    *command: str, **kwargs: object
) -> asyncio.subprocess.Process:
    containment = ProcessContainment.create()
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            *command, **kwargs, **containment.creation_kwargs
        )
        handle: Any = process
        if os.name == "nt":  # pragma: no cover
            transport = getattr(process, "_transport", None)
            getter = getattr(transport, "get_extra_info", None)
            handle = getter("subprocess") if callable(getter) else None
            if handle is None:
                raise RuntimeError("could not access Windows provider process handle")
        containment.attach_and_start(handle)
    except BaseException:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        containment.close()
        raise
    _PROCESS_CONTAINMENTS[id(process)] = containment
    if os.name == "posix" and isinstance(getattr(process, "pid", None), int):
        _OWNED_PROCESS_GROUPS[id(process)] = process.pid
    return process


def close_provider_subprocess_containment(process: asyncio.subprocess.Process) -> None:
    containment = _PROCESS_CONTAINMENTS.pop(id(process), None)
    _OWNED_PROCESS_GROUPS.pop(id(process), None)
    if containment is not None:
        containment.close()


async def terminate_text_subprocess(
    process: asyncio.subprocess.Process, *, termination_grace_seconds: float = 5.0
) -> None:
    """Terminate, force-kill, and reap only a registered owned process tree."""
    containment = _PROCESS_CONTAINMENTS.get(id(process))
    group = _OWNED_PROCESS_GROUPS.get(id(process))
    if group is not None:
        try:
            group = _verified_owned_process_group(process, group)
            try:
                os.killpg(group, signal.SIGTERM)
            except ProcessLookupError:
                pass
            else:
                deadline = asyncio.get_running_loop().time() + termination_grace_seconds
                while asyncio.get_running_loop().time() < deadline:
                    try:
                        os.killpg(group, 0)
                    except ProcessLookupError:
                        break
                    await asyncio.sleep(0.02)
                else:
                    try:
                        os.killpg(group, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            if process.returncode is None:
                try:
                    await process.wait()
                except ProcessLookupError:
                    pass
        finally:
            close_provider_subprocess_containment(process)
        return
    if containment is not None and os.name == "nt":  # pragma: no cover
        try:
            if containment._windows_job is None:
                raise RuntimeError(
                    "registered Windows provider process has no Job Object"
                )
            containment._windows_job.terminate(1)
            if process.returncode is None:
                await asyncio.wait_for(
                    process.wait(), timeout=termination_grace_seconds
                )
        finally:
            close_provider_subprocess_containment(process)
        return
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        try:
            await process.wait()
        except ProcessLookupError:
            pass
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=termination_grace_seconds)
        return
    except asyncio.TimeoutError:
        pass
    try:
        process.kill()
    except ProcessLookupError:
        return
    await process.wait()


def _verified_owned_process_group(
    process: asyncio.subprocess.Process, group: int
) -> int:
    pid = getattr(process, "pid", None)
    if not isinstance(pid, int) or group != pid or group == os.getpgrp():
        raise RuntimeError("refusing to signal an unverified provider process group")
    try:
        live_group = os.getpgid(pid)
    except ProcessLookupError:
        live_group = None
    if live_group is not None and live_group != group:
        raise RuntimeError(
            "registered provider PID now belongs to another process group"
        )
    return group


async def _cleanup_provider_subprocess_descendants(
    process: asyncio.subprocess.Process,
) -> None:
    if id(process) in _PROCESS_CONTAINMENTS:
        await terminate_text_subprocess(process)


async def _wait_for_process_leader(
    process: asyncio.subprocess.Process,
    stream_tasks: list[asyncio.Task[Any]],
) -> None:
    waiter = asyncio.create_task(process.wait())
    pending = set(stream_tasks)
    try:
        while not waiter.done():
            done, _ = await asyncio.wait(
                {waiter, *pending}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                if task is waiter:
                    continue
                pending.discard(task)
                task.result()
        await waiter
    except BaseException:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        raise


def run_text_subprocess(
    command: list[str],
    *,
    input_text: str | None = None,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> tuple[str, str, int]:
    """Run a subprocess synchronously for explicit compatibility-only paths."""

    containment = ProcessContainment.create()
    attached = False
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=None if env is None else dict(env),
            cwd=str(cwd) if cwd is not None else None,
            **containment.creation_kwargs,
        )
        containment.attach_and_start(process)
        attached = True
        tails = {"stdout": bytearray(), "stderr": bytearray()}
        truncated = {"stdout": False, "stderr": False}

        def read_stream(name, stream):
            while True:
                chunk = (
                    stream.buffer.read(65536)
                    if hasattr(stream, "buffer")
                    else stream.read(65536)
                )
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode()
                tails[name].extend(chunk)
                if len(tails[name]) > _MAX_PROVIDER_STREAM_BYTES:
                    del tails[name][: len(tails[name]) - _MAX_PROVIDER_STREAM_BYTES]
                    truncated[name] = True

        threads = [
            threading.Thread(
                target=read_stream, args=("stdout", process.stdout), daemon=True
            ),
            threading.Thread(
                target=read_stream, args=("stderr", process.stderr), daemon=True
            ),
        ]
        for thread in threads:
            thread.start()
        if input_text is not None and process.stdin is not None:
            process.stdin.write(input_text)
            process.stdin.close()
        process.wait()
        containment.terminate(process, grace_seconds=5.0)
        for thread in threads:
            thread.join(timeout=5.0)
            if thread.is_alive():
                raise RuntimeError(
                    "provider stream reader did not stop after process-tree cleanup"
                )
        marker = b"[... provider stream truncated ...]\n"
        stdout = (marker if truncated["stdout"] else b"") + bytes(tails["stdout"])
        stderr = (marker if truncated["stderr"] else b"") + bytes(tails["stderr"])
        return (
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
            process.returncode,
        )
    except BaseException:
        if process is not None and attached:
            containment.terminate(process, grace_seconds=5.0)
        elif process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise
    finally:
        containment.close()


def merge_subprocess_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Merge subprocess environment overrides over the ambient environment."""

    env = dict(os.environ)
    env.pop("CODEX_HOME", None)
    if overrides:
        env.update({str(key): str(value) for key, value in overrides.items()})
    return env


def build_policy_step_key(
    step_name: str, *, step_execution_id: str | None = None
) -> str:
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
            base_step, scope_name, item_id, visit = (
                parts[0],
                parts[1],
                parts[2],
                parts[3],
            )
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

    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def redacted_policy_payload(policy: ResolvedProviderPolicy) -> dict[str, Any]:
    """Return a JSON policy payload with sensitive env values redacted."""

    payload = policy.model_dump(mode="json")
    env_payload = payload.get("env")
    if isinstance(env_payload, dict):
        set_payload = env_payload.get("set")
        if isinstance(set_payload, dict):
            env_payload["set"] = _redact_secret_mapping(
                {str(key): str(value) for key, value in set_payload.items()}
            )
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


def emit_policy_event(
    turn: RenderedProviderTurn, event_type: str, **fields: object
) -> None:
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
    step_key = build_policy_step_key(
        turn.step_name, step_execution_id=turn.step_execution_id
    )
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
