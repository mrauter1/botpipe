"""Feedforward value operations with deterministic replay."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, field
import hashlib
import inspect
import json
from pathlib import Path
import re
from typing import Any, Callable, Literal, Mapping, Sequence

from pydantic import BaseModel, TypeAdapter

from .context import Context
from .errors import FailureContext, ProviderExecutionError, WorkflowExecutionError
from .mappings import normalize_mapping
from .prompts import Prompt, PromptRegistry, ResolvedPrompt, resolve_prompt_reference
from .providers.models import OperationRequest
from .providers.protocols import LLMProvider
from .schema_registry import OPERATION_REPLAY_SCHEMA, validate_persisted_schema
from .sessions import DEFAULT_SESSION_NAME
from .stores.protocols import SessionBinding


_JSON_FENCE_RE = re.compile(r"\A```(?:json)?\s*\n(?P<body>[\s\S]*?)\n?```\s*\Z")
_CURRENT_OPERATION_RUNTIME: ContextVar["OperationRuntime | None"] = ContextVar(
    "autoloop_operation_runtime",
    default=None,
)


@dataclass(slots=True)
class OperationRuntime:
    provider: LLMProvider
    provider_configuration: Mapping[str, Any] | None = None
    prompt_registry: PromptRegistry | None = None
    context: Context | None = None
    run_folder: Path | None = None
    workflow_name: str | None = None
    topology_hash: str | None = None
    source_hash: str | None = None
    step_name: str | None = None
    step_visit: int | None = None
    default_session_name: str = DEFAULT_SESSION_NAME
    replay_mismatch_behavior: Literal["warn", "fail"] = "warn"
    occurrence_counts: dict[str, int] = field(default_factory=dict)
    event_sink: Callable[[str, Mapping[str, Any]], None] | None = None


@dataclass(frozen=True, slots=True)
class OperationStepSpec:
    operation_kind: str
    prompt: Prompt | str
    returns: Any = str
    choices: tuple[str, ...] = ()
    retry: int = 3


def llm_call(
    prompt: Prompt | str,
    *,
    returns: Any = str,
    retry: int = 3,
    provider: LLMProvider | None = None,
    prompt_registry: PromptRegistry | None = None,
    context: Context | None = None,
    run_folder: Path | None = None,
    callsite: str | None = None,
) -> Any:
    runtime = _resolve_runtime(
        provider=provider,
        prompt_registry=prompt_registry,
        context=context,
        run_folder=run_folder,
    )
    return _run_operation(
        runtime,
        spec=OperationStepSpec(operation_kind="llm", prompt=prompt, returns=returns, retry=retry),
        callsite=callsite,
    )


def classify_call(
    prompt: Prompt | str,
    *,
    choices: Sequence[str],
    retry: int = 3,
    provider: LLMProvider | None = None,
    prompt_registry: PromptRegistry | None = None,
    context: Context | None = None,
    run_folder: Path | None = None,
    callsite: str | None = None,
) -> str:
    normalized_choices = _normalize_choices(choices)
    runtime = _resolve_runtime(
        provider=provider,
        prompt_registry=prompt_registry,
        context=context,
        run_folder=run_folder,
    )
    return _run_operation(
        runtime,
        spec=OperationStepSpec(operation_kind="classify", prompt=prompt, choices=normalized_choices, retry=retry),
        callsite=callsite,
    )


def execute_step_operation(ctx: Context, *, step_name: str, spec: OperationStepSpec) -> Any:
    runtime = _CURRENT_OPERATION_RUNTIME.get()
    if runtime is None:
        raise RuntimeError(f"operation step {step_name!r} requires an active workflow runtime")
    operation_runtime = OperationRuntime(
        provider=runtime.provider,
        provider_configuration=runtime.provider_configuration,
        prompt_registry=runtime.prompt_registry,
        context=ctx,
        run_folder=runtime.run_folder,
        workflow_name=runtime.workflow_name,
        topology_hash=runtime.topology_hash,
        source_hash=runtime.source_hash,
        step_name=step_name,
        step_visit=_step_visit(ctx),
        default_session_name=runtime.default_session_name,
        replay_mismatch_behavior=runtime.replay_mismatch_behavior,
        occurrence_counts=runtime.occurrence_counts,
        event_sink=runtime.event_sink,
    )
    value = _run_operation(operation_runtime, spec=spec, callsite=f"step:{step_name}")
    _record_context_value(ctx, step_name=step_name, value=value)
    return value


@contextmanager
def bind_operation_runtime(runtime: OperationRuntime):
    token: Token[OperationRuntime | None] = _CURRENT_OPERATION_RUNTIME.set(runtime)
    try:
        yield runtime
    finally:
        _CURRENT_OPERATION_RUNTIME.reset(token)


def current_operation_runtime() -> OperationRuntime | None:
    return _CURRENT_OPERATION_RUNTIME.get()


def serialize_context_values(values: Mapping[str, Any]) -> dict[str, Any]:
    return {name: _json_safe_value(value) for name, value in values.items()}


def _resolve_runtime(
    *,
    provider: LLMProvider | None,
    prompt_registry: PromptRegistry | None,
    context: Context | None,
    run_folder: Path | None,
) -> OperationRuntime:
    ambient = _CURRENT_OPERATION_RUNTIME.get()
    if ambient is not None:
        return OperationRuntime(
            provider=ambient.provider if provider is None else provider,
            provider_configuration=ambient.provider_configuration,
            prompt_registry=ambient.prompt_registry if prompt_registry is None else prompt_registry,
            context=ambient.context if context is None else context,
            run_folder=ambient.run_folder if run_folder is None else run_folder,
            workflow_name=ambient.workflow_name,
            topology_hash=ambient.topology_hash,
            source_hash=ambient.source_hash,
            step_name=ambient.step_name,
            step_visit=ambient.step_visit,
            default_session_name=ambient.default_session_name,
            replay_mismatch_behavior=ambient.replay_mismatch_behavior,
            occurrence_counts=ambient.occurrence_counts,
            event_sink=ambient.event_sink,
        )
    if provider is None:
        raise RuntimeError("llm() and classify() require an active workflow runtime or an explicit provider=...")
    return OperationRuntime(
        provider=provider,
        provider_configuration=provider_configuration(provider, default_session_name=DEFAULT_SESSION_NAME),
        prompt_registry=prompt_registry,
        context=context,
        run_folder=run_folder,
        workflow_name=None,
        topology_hash=None,
        source_hash=None,
        step_name=None,
        step_visit=_step_visit(context),
        replay_mismatch_behavior="warn",
        event_sink=None,
    )


def _run_operation(
    runtime: OperationRuntime,
    *,
    spec: OperationStepSpec,
    callsite: str | None,
) -> Any:
    max_attempts = _normalize_retry(retry=spec.retry)
    resolved_prompt = _resolve_prompt(spec.prompt, runtime=runtime)
    session = _resolve_session(runtime)
    callsite_id = callsite or _discover_callsite()
    occurrence = _next_occurrence(runtime, spec.operation_kind, callsite_id)
    replay_key = _operation_replay_key(runtime, spec.operation_kind, callsite_id, occurrence)
    fingerprint = _operation_fingerprint(
        runtime,
        spec=spec,
        prompt=resolved_prompt,
        session=session,
        callsite=callsite_id,
        occurrence=occurrence,
    )
    replay_path = _operation_replay_path(runtime.run_folder)
    replay_store = _load_replay_store(replay_path)
    replayed = _maybe_replay_value(
        runtime,
        replay_store,
        replay_key=replay_key,
        fingerprint=fingerprint,
        spec=spec,
    )
    if replayed is not _MISSING:
        return replayed

    retry_feedback: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            _emit_operation_attempt_event(
                runtime,
                "provider_attempt_started",
                operation_kind=spec.operation_kind,
                attempt=attempt,
            )
            response = runtime.provider.run_operation(
                OperationRequest(
                    step_name=runtime.step_name or "<operation>",
                    prompt=resolved_prompt,
                    context=runtime.context,
                    session=session,
                    operation_kind=spec.operation_kind,
                    return_schema=_return_schema(spec.returns) if spec.operation_kind == "llm" else None,
                    choices=spec.choices,
                    retry_feedback=retry_feedback,
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
            )
            value = _parse_operation_value(spec=spec, raw_output=response.raw_output)
            _emit_operation_attempt_event(
                runtime,
                "provider_attempt_finished",
                operation_kind=spec.operation_kind,
                attempt=attempt,
                token_usage=response.usage,
            )
            _persist_session(runtime, response.session)
            _record_attempt(
                replay_store,
                replay_key=replay_key,
                fingerprint=fingerprint,
                attempt=attempt,
                status="accepted",
            )
            replay_store["records"][replay_key] = {
                "fingerprint": fingerprint,
                "operation_kind": spec.operation_kind,
                "step_name": runtime.step_name,
                "step_visit": runtime.step_visit,
                "callsite": callsite_id,
                "occurrence": occurrence,
                "value": _json_safe_value(value),
                "raw_output": response.raw_output,
            }
            _write_replay_store(replay_path, replay_store)
            return value
        except Exception as exc:
            _emit_operation_attempt_event(
                runtime,
                "provider_attempt_failed",
                operation_kind=spec.operation_kind,
                attempt=attempt,
                failure_context=_operation_failure_context(exc),
            )
            _record_attempt(
                replay_store,
                replay_key=replay_key,
                fingerprint=fingerprint,
                attempt=attempt,
                status="failed",
                error=str(exc),
            )
            _write_replay_store(replay_path, replay_store)
            if attempt >= max_attempts:
                raise
            retry_feedback = _build_retry_feedback(
                exc,
                operation_kind=spec.operation_kind,
                step_name=runtime.step_name or "<operation>",
                attempt=attempt,
                max_attempts=max_attempts,
                choices=spec.choices,
            )
    raise AssertionError("operation retry loop exhausted without returning or raising")


class _Missing:
    pass


_MISSING = _Missing()


def _maybe_replay_value(
    runtime: OperationRuntime,
    replay_store: dict[str, Any],
    *,
    replay_key: str,
    fingerprint: str,
    spec: OperationStepSpec,
) -> Any:
    records = replay_store.get("records")
    if not isinstance(records, dict):
        return _MISSING
    record = records.get(replay_key)
    if not isinstance(record, dict):
        return _MISSING
    saved_fingerprint = record.get("fingerprint")
    if saved_fingerprint != fingerprint:
        message = (
            f"operation replay fingerprint mismatch for key {replay_key!r}: "
            f"saved={saved_fingerprint!r} current={fingerprint!r}"
        )
        if runtime.replay_mismatch_behavior == "fail":
            raise ProviderExecutionError(message)
        _emit_replay_warning(
            runtime,
            replay_key=replay_key,
            saved_fingerprint=saved_fingerprint,
            fingerprint=fingerprint,
        )
    return _hydrate_replayed_value(record.get("value"), spec=spec)


def _hydrate_replayed_value(payload: Any, *, spec: OperationStepSpec) -> Any:
    if spec.operation_kind == "classify":
        if not isinstance(payload, str):
            raise ProviderExecutionError("replayed classification value must be a string")
        if payload not in spec.choices:
            raise ProviderExecutionError("replayed classification value is not one of the declared choices")
        return payload
    if spec.returns in {None, str}:
        if not isinstance(payload, str):
            raise ProviderExecutionError("replayed llm value must be a string when returns=str")
        return payload
    adapter = TypeAdapter(spec.returns)
    return adapter.validate_python(payload)


def _parse_operation_value(*, spec: OperationStepSpec, raw_output: str) -> Any:
    if spec.operation_kind == "classify":
        return _parse_classification_value(raw_output, choices=spec.choices)
    if spec.returns in {None, str}:
        if not raw_output.strip():
            raise ProviderExecutionError("provider returned an empty llm value", retry_kind="empty_operation_value")
        return raw_output
    payload = _parse_json_value(raw_output)
    try:
        return TypeAdapter(spec.returns).validate_python(payload)
    except Exception as exc:
        raise ProviderExecutionError(
            f"provider returned an invalid typed llm value: {exc}",
            retry_kind="invalid_operation_value",
        ) from exc


def _parse_json_value(raw_output: str) -> Any:
    candidate = raw_output.strip()
    if not candidate:
        raise ProviderExecutionError(
            "provider returned an empty structured llm value",
            retry_kind="empty_operation_value",
        )
    match = _JSON_FENCE_RE.fullmatch(candidate)
    if match is not None:
        candidate = match.group("body").strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ProviderExecutionError(
            f"provider returned malformed operation JSON: {exc.msg}",
            retry_kind="malformed_operation_value",
        ) from exc


def _parse_classification_value(raw_output: str, *, choices: Sequence[str]) -> str:
    candidate = raw_output.strip()
    match = _JSON_FENCE_RE.fullmatch(candidate)
    if match is not None:
        candidate = match.group("body").strip()
    if candidate.startswith('"') and candidate.endswith('"'):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = candidate
        if isinstance(parsed, str):
            candidate = parsed.strip()
    if not candidate:
        raise ProviderExecutionError(
            "provider returned an empty classification value",
            retry_kind="empty_operation_value",
        )
    if candidate not in choices:
        raise ProviderExecutionError(
            f"provider returned invalid classification choice {candidate!r}; legal choices: {', '.join(choices)}",
            retry_kind="invalid_operation_choice",
        )
    return candidate


def _emit_operation_attempt_event(
    runtime: OperationRuntime,
    event_type: str,
    *,
    operation_kind: str,
    attempt: int,
    token_usage: Any | None = None,
    failure_context: Mapping[str, Any] | None = None,
) -> None:
    if runtime.event_sink is None:
        return
    payload: dict[str, Any] = {
        "step_name": runtime.step_name or "<operation>",
        "turn_kind": "operation",
        "operation_kind": operation_kind,
        "attempt": attempt,
    }
    if runtime.step_visit is not None:
        payload["visit"] = runtime.step_visit
    if runtime.step_name is not None:
        scope_name, item_id = _operation_scope_item(runtime.context)
        payload["step_execution_id"] = _operation_step_execution_id(
            step_name=runtime.step_name,
            visit=runtime.step_visit,
            scope_name=scope_name,
            item_id=item_id,
        )
        if scope_name is not None:
            payload["scope"] = scope_name
        if item_id is not None:
            payload["item_id"] = item_id
    if token_usage is not None:
        payload["token_usage"] = {key: value for key, value in asdict(token_usage).items() if value is not None}
    if failure_context:
        payload["failure_context"] = dict(failure_context)
    runtime.event_sink(event_type, payload)


def _operation_scope_item(ctx: Context | None) -> tuple[str | None, str | None]:
    if ctx is None:
        return None, None
    scope_name = getattr(ctx, "_active_worklist", None)
    if not isinstance(scope_name, str) or not scope_name:
        return None, None
    item_id = _scope_item_id(ctx)
    return scope_name, item_id


def _operation_step_execution_id(
    *,
    step_name: str,
    visit: int | None,
    scope_name: str | None,
    item_id: str | None,
) -> str | None:
    if visit is None:
        return None
    if scope_name is not None and item_id is not None:
        return f"{step_name}:{scope_name}:{item_id}:{visit}"
    return f"{step_name}:{visit}"


def _operation_failure_context(exc: Exception) -> dict[str, Any]:
    failure_context = getattr(exc, "failure_context", None)
    if isinstance(failure_context, FailureContext):
        return failure_context.to_payload()
    if isinstance(failure_context, dict) and failure_context:
        return dict(failure_context)
    return {
        "error": str(exc),
        "error_type": type(exc).__name__,
    }


def _record_context_value(ctx: Context, *, step_name: str, value: Any) -> None:
    serialized = _json_safe_value(value)
    if hasattr(ctx, "_values") and isinstance(ctx._values, dict):
        ctx._values[step_name] = serialized


def _resolve_prompt(prompt: Prompt | str, *, runtime: OperationRuntime) -> ResolvedPrompt:
    prompt = _normalize_operation_prompt(prompt)
    registry = runtime.prompt_registry
    if registry is not None:
        return registry.resolve(prompt)
    if prompt.source == "inline":
        return ResolvedPrompt(
            path=prompt.path,
            text=prompt.text,
            source="inline",
            reference_values={"source": "inline", "inline": True},
        )
    search_roots: tuple[Path, ...] = ()
    if runtime.context is not None:
        search_roots = (runtime.context.package_folder, runtime.context.workflow_folder)
    return resolve_prompt_reference(prompt.path, source=prompt.source, search_roots=search_roots)


def _normalize_operation_prompt(prompt: Prompt | str) -> Prompt:
    if isinstance(prompt, Prompt):
        return prompt
    if not isinstance(prompt, str):
        raise TypeError("operation prompt must be a Prompt or string")
    return Prompt.inline(prompt)


def _resolve_session(runtime: OperationRuntime) -> SessionBinding | None:
    ctx = runtime.context
    if ctx is None:
        return None
    session = ctx.get_session(runtime.default_session_name)
    if session is not None:
        return session
    return ctx.open_session(runtime.default_session_name)


def _persist_session(runtime: OperationRuntime, session: SessionBinding | None) -> None:
    if session is None or runtime.context is None:
        return
    runtime.context._session_store.upsert(session, activate=True)


def _normalize_retry(*, retry: int) -> int:
    if isinstance(retry, bool) or not isinstance(retry, int):
        raise TypeError("operation retry must be an integer")
    if retry < 1:
        raise ValueError("operation retry must be >= 1")
    return retry


def _normalize_choices(choices: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for choice in choices:
        if not isinstance(choice, str) or not choice.strip():
            raise TypeError("classification choices must be non-empty strings")
        normalized.append(choice.strip())
    if not normalized:
        raise ValueError("classification choices must not be empty")
    unique = tuple(dict.fromkeys(normalized))
    if len(unique) != len(normalized):
        raise ValueError("classification choices must not repeat")
    return unique


def _return_schema(returns: Any) -> dict[str, Any] | None:
    if returns in {None, str}:
        return None
    return TypeAdapter(returns).json_schema()


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    try:
        return json.loads(json.dumps(value))
    except TypeError as exc:
        raise WorkflowExecutionError(f"operation value is not JSON-serializable for replay: {exc}") from exc


def _operation_fingerprint(
    runtime: OperationRuntime,
    *,
    spec: OperationStepSpec,
    prompt: ResolvedPrompt,
    session: SessionBinding | None,
    callsite: str,
    occurrence: int,
) -> str:
    payload = {
        "workflow_name": runtime.workflow_name,
        "step_name": runtime.step_name,
        "step_visit": runtime.step_visit,
        "operation_kind": spec.operation_kind,
        "callsite": callsite,
        "prompt_source": prompt.source,
        "prompt_path": prompt.path,
        "prompt_hash": _sha256_text(prompt.text or ""),
        "prompt_reference_values_hash": _sha256_json(_prompt_reference_values(prompt)),
        "return_schema_hash": _sha256_json(_return_schema(spec.returns)),
        "choices_hash": _sha256_json(list(spec.choices)),
        "session_slot": None if session is None else session.ref_name,
        "scope_item_id": _scope_item_id(runtime.context),
        "occurrence_index": occurrence,
        "provider_configuration": _provider_configuration(runtime),
    }
    return _sha256_json(payload)


def _operation_replay_key(
    runtime: OperationRuntime,
    operation_kind: str,
    callsite: str,
    occurrence: int,
) -> str:
    payload = {
        "workflow_name": runtime.workflow_name,
        "step_name": runtime.step_name,
        "step_visit": runtime.step_visit,
        "operation_kind": operation_kind,
        "callsite": callsite,
        "occurrence_index": occurrence,
    }
    return _sha256_json(payload)


def _next_occurrence(runtime: OperationRuntime, operation_kind: str, callsite: str) -> int:
    key = json.dumps(
        {
            "workflow_name": runtime.workflow_name,
            "step_name": runtime.step_name,
            "step_visit": runtime.step_visit,
            "operation_kind": operation_kind,
            "callsite": callsite,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    next_value = runtime.occurrence_counts.get(key, 0) + 1
    runtime.occurrence_counts[key] = next_value
    return next_value


def _discover_callsite() -> str:
    this_file = Path(__file__).resolve()
    for frame_info in inspect.stack()[2:]:
        candidate = Path(frame_info.filename).resolve()
        if candidate == this_file:
            continue
        return f"{candidate}:{frame_info.function}:{frame_info.lineno}"
    return "<unknown>"


def _scope_item_id(ctx: Context | None) -> str | None:
    if ctx is None or ctx.item is None:
        return None
    item_id = getattr(ctx.item, "id", None)
    return item_id if isinstance(item_id, str) and item_id else None


def _step_visit(ctx: Context | None) -> int | None:
    if ctx is None:
        return None
    try:
        value = ctx.meta.step.visits
    except AttributeError:
        return None
    return value if isinstance(value, int) else None


def _build_retry_feedback(
    exc: Exception,
    *,
    operation_kind: str,
    step_name: str,
    attempt: int,
    max_attempts: int,
    choices: Sequence[str],
) -> str:
    problem = str(exc).strip() or f"{operation_kind} operation failed for step {step_name!r}"
    action_lines = ["- Repair the response using the current Runtime Operation Contract."]
    if operation_kind == "classify":
        action_lines.append(f"- Return exactly one declared choice: {', '.join(choices)}.")
    else:
        action_lines.append("- Return a non-empty value.")
        action_lines.append("- If a typed schema is declared, return valid JSON matching that schema.")
    return "\n".join(
        (
            "## Retry Feedback",
            "",
            "The previous operation attempt could not be accepted.",
            "",
            "Attempt:",
            f"- {attempt} of {max_attempts}",
            "",
            "Problem:",
            f"- {problem}",
            "",
            "Action required:",
            *action_lines,
        )
    )


def _operation_replay_path(run_folder: Path | None) -> Path | None:
    if run_folder is None:
        return None
    return run_folder / "operation_replay.json"


def _load_replay_store(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"schema": OPERATION_REPLAY_SCHEMA, "records": {}, "attempts": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"schema": OPERATION_REPLAY_SCHEMA, "records": {}, "attempts": []}
    validate_persisted_schema(payload, expected=OPERATION_REPLAY_SCHEMA, artifact_name=str(path))
    records = payload.get("records")
    attempts = payload.get("attempts")
    return {
        "schema": OPERATION_REPLAY_SCHEMA,
        "records": records if isinstance(records, dict) else {},
        "attempts": attempts if isinstance(attempts, list) else [],
    }


def _write_replay_store(path: Path | None, payload: Mapping[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    serialized = {"schema": OPERATION_REPLAY_SCHEMA, **dict(payload)}
    temp_path.write_text(json.dumps(serialized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _emit_replay_warning(
    runtime: OperationRuntime,
    *,
    replay_key: str,
    saved_fingerprint: Any,
    fingerprint: str,
) -> None:
    if runtime.event_sink is None:
        return
    payload: dict[str, Any] = {
        "step_name": runtime.step_name or "<operation>",
        "turn_kind": "operation",
        "event_type": "operation_replay_fingerprint_mismatch",
        "replay_key": replay_key,
        "saved_fingerprint": saved_fingerprint,
        "current_fingerprint": fingerprint,
        "behavior": runtime.replay_mismatch_behavior,
    }
    if runtime.context is not None:
        scope_name, item_id = _operation_scope_item(runtime.context)
        payload["step_execution_id"] = _operation_step_execution_id(
            step_name=runtime.step_name or "<operation>",
            visit=runtime.step_visit,
            scope_name=scope_name,
            item_id=item_id,
        )
    runtime.event_sink("operation_replay_fingerprint_mismatch", payload)


def _prompt_reference_values(prompt: ResolvedPrompt) -> dict[str, Any]:
    values = normalize_mapping(prompt.reference_values, stringify_keys=True)
    values.setdefault("source", prompt.source)
    values.setdefault("resolved_path", prompt.path)
    return values


def _provider_configuration(runtime: OperationRuntime) -> dict[str, Any]:
    if runtime.provider_configuration is not None:
        return normalize_mapping(runtime.provider_configuration, stringify_keys=True)
    return provider_configuration(runtime.provider, default_session_name=runtime.default_session_name)


def provider_configuration(provider: LLMProvider, *, default_session_name: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider_module": type(provider).__module__,
        "provider_type": type(provider).__qualname__,
        "default_session_name": default_session_name,
    }
    transport = getattr(provider, "_transport", None)
    if transport is not None:
        payload["transport"] = _configuration_payload(transport)
    provider_payload = _configuration_payload(provider)
    if provider_payload:
        payload["provider"] = provider_payload
    return payload


def _configuration_payload(value: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    config = getattr(value, "_config", None)
    if config is not None:
        payload["config"] = _json_safe_configuration_value(config)
    commands = getattr(value, "_commands", None)
    if commands is not None:
        payload["commands"] = _json_safe_configuration_value(commands)
    for source_name in (
        "model",
        "_model",
        "model_effort",
        "_model_effort",
        "effort",
        "_effort",
        "permission_strategy",
        "default_provider",
        "default_mode",
    ):
        if not hasattr(value, source_name):
            continue
        normalized_name = source_name.lstrip("_")
        payload[normalized_name] = _json_safe_configuration_value(getattr(value, source_name))
    return payload


def _json_safe_configuration_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe_configuration_value(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe_configuration_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_configuration_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _record_attempt(
    replay_store: dict[str, Any],
    *,
    replay_key: str,
    fingerprint: str,
    attempt: int,
    status: str,
    error: str | None = None,
) -> None:
    attempts = replay_store.setdefault("attempts", [])
    if not isinstance(attempts, list):
        attempts = []
        replay_store["attempts"] = attempts
    payload = {
        "replay_key": replay_key,
        "fingerprint": fingerprint,
        "attempt": attempt,
        "status": status,
    }
    if error is not None:
        payload["error"] = error
    attempts.append(payload)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


__all__ = [
    "OperationRuntime",
    "OperationStepSpec",
    "bind_operation_runtime",
    "classify_call",
    "current_operation_runtime",
    "execute_step_operation",
    "llm_call",
    "serialize_context_values",
]
