"""Runtime-owned trace and raw-output persistence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:  # pragma: no branch - prefer installed-package imports when available
    from autoloop_v3.core.compiler import CompiledWorkflow
    from autoloop_v3.core.extensions import StepFinish, StepStart, TerminalFinish
    from autoloop_v3.core.providers.models import StepProviderUsage
    from autoloop_v3.core.primitives import Event, Outcome
    from autoloop_v3.core.schema_registry import RUNTIME_TRACE_SCHEMA
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core.compiler import CompiledWorkflow
    from core.extensions import StepFinish, StepStart, TerminalFinish
    from core.providers.models import StepProviderUsage
    from core.primitives import Event, Outcome
    from core.schema_registry import RUNTIME_TRACE_SCHEMA
from .config import TracingRuntimeConfig
from .static_graph import STATIC_GRAPH_FILENAME, write_static_step_graph_payload, write_topology_artifacts
from .workspace import append_run_warning, update_run_tracing


TRACE_SCHEMA = RUNTIME_TRACE_SCHEMA
RAW_DIRNAME = "raw"
_SAFE_STEP_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


class RuntimeTraceError(RuntimeError):
    """Raised when runtime trace persistence fails."""


class RuntimeTraceWriter:
    def __init__(
        self,
        *,
        run_dir: Path,
        workflow_name: str,
        task_id: str,
        run_id: str,
        config: TracingRuntimeConfig,
        static_step_graph: Mapping[str, Any],
        compiled_workflow: CompiledWorkflow | None = None,
    ) -> None:
        self._run_dir = run_dir.resolve()
        self._workflow_name = workflow_name
        self._task_id = task_id
        self._run_id = run_id
        self._config = config
        self._static_step_graph = dict(static_step_graph)
        self._compiled_workflow = compiled_workflow
        self._trace_path = _resolve_trace_path(self._run_dir, config.path)
        self._run_guarded(self._initialize)

    def step_started(
        self,
        *,
        sequence: int,
        event: StepStart,
        commit_before_step: str | None,
    ) -> None:
        if not self._config.enabled:
            return
        self._run_guarded(
            lambda: self._write_step_started(
                sequence=sequence,
                event=event,
                commit_before_step=commit_before_step,
            )
        )

    def _write_step_started(
        self,
        *,
        sequence: int,
        event: StepStart,
        commit_before_step: str | None,
    ) -> None:
        payload = self._base_payload(
            event_type="step_started",
            sequence=sequence,
            step_name=event.step_name,
            step_kind=event.step_kind,
            git={"commit_before_step": commit_before_step},
        )
        if self._config.include_state_snapshots:
            payload["state"] = event.state.model_dump(mode="json")
        self._write(payload)

    def step_finished(
        self,
        *,
        sequence: int,
        event: StepFinish,
        commit_before_step: str | None,
    ) -> None:
        if not self._config.enabled:
            return
        self._run_guarded(
            lambda: self._write_step_finished(
                sequence=sequence,
                event=event,
                commit_before_step=commit_before_step,
            )
        )

    def _write_step_finished(
        self,
        *,
        sequence: int,
        event: StepFinish,
        commit_before_step: str | None,
    ) -> None:
        raw_output_refs = self._persist_raw_outputs(sequence=sequence, event=event)
        payload = self._base_payload(
            event_type="step_finished",
            sequence=sequence,
            step_name=event.step_name,
            step_kind=event.step_kind,
            git={"commit_before_step": commit_before_step},
            event=self._serialize_event(event.event),
            outcome=self._serialize_outcome(event.outcome),
            raw_output_refs=raw_output_refs,
            provider_usage=self._serialize_provider_usage(event.provider_usage),
        )
        if event.hook_route_override_from is not None or event.hook_route_override_to is not None:
            payload["hook_route_override"] = {
                "from": event.hook_route_override_from,
                "to": event.hook_route_override_to,
            }
        if self._config.include_state_snapshots:
            payload["state_before"] = event.state_before.model_dump(mode="json")
            payload["state_after"] = event.state_after.model_dump(mode="json")
        self._write(payload)

    def terminal(
        self,
        *,
        event: TerminalFinish,
    ) -> None:
        if not self._config.enabled:
            return
        self._run_guarded(lambda: self._write_terminal(event=event))

    def _write_terminal(
        self,
        *,
        event: TerminalFinish,
    ) -> None:
        payload = self._base_payload(
            event_type="terminal",
            terminal=event.terminal,
            step_name=event.step_name,
            event=self._serialize_event(event.event),
            outcome=self._serialize_outcome(event.outcome),
        )
        if self._config.include_state_snapshots and event.state is not None:
            payload["state"] = event.state.model_dump(mode="json")
        self._write(payload)

    def fatal(
        self,
        *,
        event: TerminalFinish,
        error: BaseException,
    ) -> None:
        if not self._config.enabled:
            return
        self._run_guarded(lambda: self._write_fatal(event=event, error=error))

    def _write_fatal(
        self,
        *,
        event: TerminalFinish,
        error: BaseException,
    ) -> None:
        payload = self._base_payload(
            event_type="fatal",
            step_name=event.step_name,
            error_type=type(error).__name__,
            error_message=str(error),
        )
        if self._config.include_state_snapshots and event.state is not None:
            payload["state"] = event.state.model_dump(mode="json")
        self._write(payload)

    @property
    def _raw_dir(self) -> Path:
        return self._run_dir / RAW_DIRNAME

    def _initialize(self) -> None:
        if self._config.enabled:
            self._trace_path.parent.mkdir(parents=True, exist_ok=True)
            self._trace_path.touch(exist_ok=True)
            self._raw_dir.mkdir(parents=True, exist_ok=True)
        write_static_step_graph_payload(self._run_dir, self._static_step_graph)
        if self._compiled_workflow is not None:
            write_topology_artifacts(self._run_dir, self._compiled_workflow)
        self._update_metadata()

    def _base_payload(self, *, event_type: str, **fields: object) -> dict[str, object]:
        return {
            "schema": TRACE_SCHEMA,
            "event_type": event_type,
            "timestamp": _utcnow(),
            "workflow": self._workflow_name,
            "task_id": self._task_id,
            "run_id": self._run_id,
            **fields,
        }

    def _persist_raw_outputs(self, *, sequence: int, event: StepFinish) -> dict[str, dict[str, object]]:
        refs: dict[str, dict[str, object]] = {}
        raw_output_by_role: list[tuple[str, str]] = []
        if event.step_kind == "produce_verify":
            if event.producer_raw_output is not None:
                raw_output_by_role.append(("producer", event.producer_raw_output))
            if event.verifier_raw_output is not None:
                raw_output_by_role.append(("verifier", event.verifier_raw_output))
        elif event.step_kind == "step" and event.producer_raw_output is not None:
            raw_output_by_role.append(("step", event.producer_raw_output))
        for role, text in raw_output_by_role:
            refs[role] = self._persist_raw_output(sequence=sequence, step_name=event.step_name, role=role, text=text)
        return refs

    def _persist_raw_output(self, *, sequence: int, step_name: str, role: str, text: str) -> dict[str, object]:
        safe_step = _safe_step_name(step_name)
        relative_path = Path(RAW_DIRNAME) / f"{sequence:06d}_{safe_step}_{role}.txt"
        absolute_path = self._run_dir / relative_path
        if absolute_path.exists():
            raise RuntimeTraceError(f"refusing to overwrite existing raw output file {absolute_path}")
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        content = text.encode("utf-8")
        absolute_path.write_bytes(content)
        return {
            "path": relative_path.as_posix(),
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }

    def _serialize_event(self, event: Event | None) -> dict[str, object] | None:
        if event is None:
            return None
        payload: dict[str, object] = {"tag": event.tag}
        if event.reason:
            payload["reason"] = event.reason
        if event.question is not None:
            payload["question"] = event.question
        if event.handoff is not None:
            payload["handoff"] = event.handoff
        return payload

    def _serialize_outcome(self, outcome: Outcome | None) -> dict[str, object] | None:
        if outcome is None:
            return None
        payload: dict[str, object] = {"tag": outcome.tag}
        if outcome.payload:
            payload["payload"] = outcome.payload
        if outcome.reason:
            payload["reason"] = outcome.reason
        if outcome.question is not None:
            payload["question"] = outcome.question
        return payload

    def _serialize_provider_usage(self, usage: StepProviderUsage | None) -> dict[str, object] | None:
        if usage is None:
            return None
        payload = asdict(usage)
        return {key: value for key, value in payload.items() if value is not None}

    def _update_metadata(self) -> None:
        trace_file_value = (
            self._trace_path.relative_to(self._run_dir).as_posix()
            if self._trace_path.is_relative_to(self._run_dir)
            else str(self._trace_path)
        )
        update_run_tracing(
            self._run_dir,
            {
                "enabled": self._config.enabled,
                "trace_file": trace_file_value,
                "raw_dir": RAW_DIRNAME,
                "static_step_graph_file": STATIC_GRAPH_FILENAME,
                "schema": TRACE_SCHEMA,
            },
        )

    def _write(self, payload: Mapping[str, object]) -> None:
        self._trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self._trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), ensure_ascii=False) + "\n")

    def _run_guarded(self, operation) -> None:
        try:
            operation()
        except Exception as exc:
            self._handle_failure(exc)

    def _handle_failure(self, exc: Exception) -> None:
        if self._config.failure_mode == "ignore":
            try:
                append_run_warning(
                    self._run_dir,
                    {
                        "event_type": "runtime_tracing_write_failed",
                        "message": str(exc),
                    },
                )
            except Exception:
                return
            return
        if isinstance(exc, RuntimeTraceError):
            raise exc
        raise RuntimeTraceError(str(exc)) from exc


def _resolve_trace_path(run_dir: Path, configured_path: str) -> Path:
    candidate = Path(configured_path)
    if candidate.is_absolute():
        return candidate
    return run_dir / candidate


def _safe_step_name(step_name: str) -> str:
    normalized = _SAFE_STEP_PATTERN.sub("_", step_name).strip("_")
    return normalized or "step"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "RAW_DIRNAME",
    "RuntimeTraceError",
    "RuntimeTraceWriter",
    "TRACE_SCHEMA",
]
