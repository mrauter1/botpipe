from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import BaseModel

from autoloop_v3.core.extensions import RunBinding, StepFinish, StepStart, TerminalFinish
from autoloop_v3.core.providers.models import StepProviderUsage, TokenUsage
from autoloop_v3.core.primitives import Event, Outcome
from autoloop_v3.runtime.config import TracingRuntimeConfig
from autoloop_v3.runtime.tracing import RuntimeTraceError, RuntimeTraceWriter
from autoloop_v3.runtime.workspace import next_observability_sequence


class _State(BaseModel):
    note: str = ""


def _binding(run_dir: Path) -> RunBinding:
    root = run_dir.parents[5]
    task_folder = run_dir.parents[3]
    workflow_folder = run_dir.parents[1]
    return RunBinding(
        root=root,
        task_id="task-1",
        run_id=run_dir.name,
        workflow_name="demo",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_dir,
        package_folder=root / "workflows" / "demo",
    )


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / ".autoloop" / "tasks" / "task-1" / "wf_demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    return run_dir


def _writer(run_dir: Path, *, config: TracingRuntimeConfig | None = None) -> RuntimeTraceWriter:
    return RuntimeTraceWriter(
        run_dir=run_dir,
        workflow_name="demo",
        task_id="task-1",
        run_id=run_dir.name,
        config=config or TracingRuntimeConfig(),
        static_step_graph={
            "schema": "autoloop.workflow_static_step_graph/v1",
            "workflow_name": "demo",
            "steps": [],
            "transitions": {"steps": {}, "global": {}},
        },
    )


def _step_start(run_dir: Path, *, step_name: str = "assessment", step_kind: str = "pair") -> StepStart:
    return StepStart(
        binding=_binding(run_dir),
        step_name=step_name,
        step_kind=step_kind,
        state=_State(note="before"),
    )


def _step_finish(
    run_dir: Path,
    *,
    step_name: str = "assessment",
    step_kind: str = "pair",
    producer_raw_output: str | None = "producer output\n",
    verifier_raw_output: str | None = "verifier output\n",
    provider_usage: StepProviderUsage | None = None,
) -> StepFinish:
    return StepFinish(
        binding=_binding(run_dir),
        step_name=step_name,
        step_kind=step_kind,
        state_before=_State(note="before"),
        state_after=_State(note="after"),
        event=Event(tag="ready", reason="validated"),
        outcome=Outcome(raw_output="hidden raw", tag="ready", reason="validated", payload={"ok": True}),
        producer_raw_output=producer_raw_output,
        verifier_raw_output=verifier_raw_output,
        provider_usage=provider_usage,
    )


def _terminal(run_dir: Path, *, terminal: str = "SUCCESS") -> TerminalFinish:
    return TerminalFinish(
        binding=_binding(run_dir),
        terminal=terminal,
        step_name="assessment",
        state=_State(note="done"),
        event=Event(tag="ready", reason="validated"),
        outcome=Outcome(raw_output="hidden raw", tag="ready", payload={"ok": True}),
    )


def test_runtime_trace_enabled_by_default_writes_trace_jsonl(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)

    writer.step_started(sequence=1, event=_step_start(run_dir), commit_before_step="abc123")

    assert (run_dir / "trace.jsonl").exists()
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_meta["tracing"]["enabled"] is True
    assert run_meta["tracing"]["trace_file"] == "trace.jsonl"


def test_runtime_trace_initialization_persists_static_step_graph(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    _writer(run_dir)

    payload = json.loads((run_dir / "static_step_graph.json").read_text(encoding="utf-8"))

    assert payload["schema"] == "autoloop.workflow_static_step_graph/v1"
    assert payload["workflow_name"] == "demo"


def test_runtime_trace_records_step_started_and_finished(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)

    writer.step_started(sequence=1, event=_step_start(run_dir), commit_before_step="abc123")
    writer.step_finished(sequence=1, event=_step_finish(run_dir), commit_before_step="abc123")

    lines = [
        json.loads(line)
        for line in (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert [line["event_type"] for line in lines] == ["step_started", "step_finished"]
    assert lines[0]["state"]["note"] == "before"
    assert lines[1]["state_after"]["note"] == "after"


def test_runtime_trace_writes_pair_raw_producer_and_verifier_files(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)

    writer.step_finished(sequence=1, event=_step_finish(run_dir), commit_before_step="abc123")

    assert (run_dir / "raw" / "000001_assessment_producer.txt").read_text(encoding="utf-8") == "producer output\n"
    assert (run_dir / "raw" / "000001_assessment_verifier.txt").read_text(encoding="utf-8") == "verifier output\n"


def test_runtime_trace_writes_llm_raw_file(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)
    event = _step_finish(
        run_dir,
        step_name="survey",
        step_kind="llm",
        producer_raw_output="llm output\n",
        verifier_raw_output=None,
    )

    writer.step_finished(sequence=2, event=event, commit_before_step="abc123")

    assert (run_dir / "raw" / "000002_survey_llm.txt").read_text(encoding="utf-8") == "llm output\n"


def test_runtime_trace_records_raw_file_sha256_and_bytes(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)

    writer.step_finished(sequence=1, event=_step_finish(run_dir), commit_before_step="abc123")

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    producer_ref = record["raw_output_refs"]["producer"]

    assert producer_ref["bytes"] == len("producer output\n".encode("utf-8"))
    assert producer_ref["sha256"] == sha256("producer output\n".encode("utf-8")).hexdigest()


def test_runtime_trace_records_outcome_route_tag(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)

    writer.step_finished(sequence=1, event=_step_finish(run_dir), commit_before_step="abc123")

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["event"]["tag"] == "ready"
    assert record["outcome"]["tag"] == "ready"
    assert "raw_output" not in record["outcome"]


def test_runtime_trace_records_hook_route_override_metadata(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)
    event = _step_finish(run_dir)
    event = StepFinish(
        binding=event.binding,
        step_name=event.step_name,
        step_kind=event.step_kind,
        state_before=event.state_before,
        state_after=event.state_after,
        event=Event(tag="question", question="Need approval?"),
        outcome=event.outcome,
        producer_raw_output=event.producer_raw_output,
        verifier_raw_output=event.verifier_raw_output,
        provider_usage=event.provider_usage,
        hook_route_override_from="ready",
        hook_route_override_to="question",
    )

    writer.step_finished(sequence=1, event=event, commit_before_step="abc123")

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["hook_route_override"] == {"from": "ready", "to": "question"}


def test_runtime_trace_records_provider_usage_when_available(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)
    provider_usage = StepProviderUsage(
        producer=TokenUsage(input_tokens=5, output_tokens=7, total_tokens=12, source="provider"),
        verifier=TokenUsage(input_tokens=2, output_tokens=3, total_tokens=5, source="provider"),
    )

    writer.step_finished(
        sequence=1,
        event=_step_finish(run_dir, provider_usage=provider_usage),
        commit_before_step="abc123",
    )

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["provider_usage"]["producer"]["total_tokens"] == 12
    assert record["provider_usage"]["verifier"]["total_tokens"] == 5


def test_runtime_trace_can_be_disabled(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir, config=TracingRuntimeConfig(enabled=False))

    writer.step_started(sequence=1, event=_step_start(run_dir), commit_before_step="abc123")
    writer.step_finished(sequence=1, event=_step_finish(run_dir), commit_before_step="abc123")
    writer.terminal(event=_terminal(run_dir))

    assert not (run_dir / "trace.jsonl").exists()
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_meta["tracing"]["enabled"] is False


def test_runtime_trace_disabled_still_persists_static_step_graph(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    _writer(run_dir, config=TracingRuntimeConfig(enabled=False))

    assert not (run_dir / "trace.jsonl").exists()
    payload = json.loads((run_dir / "static_step_graph.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "autoloop.workflow_static_step_graph/v1"
    assert payload["workflow_name"] == "demo"


def test_runtime_trace_failure_mode_ignore_swallows_initialization_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr(
        "autoloop_v3.runtime.tracing.write_static_step_graph_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("graph write failed")),
    )

    writer = RuntimeTraceWriter(
        run_dir=run_dir,
        workflow_name="demo",
        task_id="task-1",
        run_id=run_dir.name,
        config=TracingRuntimeConfig(failure_mode="ignore"),
        static_step_graph={"schema": "autoloop.workflow_static_step_graph/v1"},
    )
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert isinstance(writer, RuntimeTraceWriter)
    assert run_meta["warnings"][-1]["event_type"] == "runtime_tracing_write_failed"
    assert "graph write failed" in run_meta["warnings"][-1]["message"]


def test_runtime_trace_failure_mode_ignore_swallows_step_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir, config=TracingRuntimeConfig(failure_mode="ignore"))
    monkeypatch.setattr(
        writer,
        "_write",
        lambda payload: (_ for _ in ()).throw(RuntimeError("trace append failed")),
    )

    writer.step_finished(sequence=1, event=_step_finish(run_dir), commit_before_step="abc123")

    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_meta["warnings"][-1]["event_type"] == "runtime_tracing_write_failed"
    assert "trace append failed" in run_meta["warnings"][-1]["message"]


def test_runtime_trace_terminal_writes_terminal_event_payload(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)

    writer.terminal(event=_terminal(run_dir, terminal="SUCCESS"))

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["event_type"] == "terminal"
    assert record["terminal"] == "SUCCESS"
    assert record["step_name"] == "assessment"
    assert record["state"]["note"] == "done"
    assert record["outcome"]["tag"] == "ready"


def test_runtime_trace_fatal_writes_error_payload(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)

    writer.fatal(event=_terminal(run_dir, terminal="FAILED"), error=RuntimeError("boom"))

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["event_type"] == "fatal"
    assert record["step_name"] == "assessment"
    assert record["error_type"] == "RuntimeError"
    assert record["error_message"] == "boom"
    assert record["state"]["note"] == "done"


def test_trace_events_include_commit_before_step_not_commit_after_step(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)

    writer.step_finished(sequence=1, event=_step_finish(run_dir), commit_before_step="abc123")

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["git"] == {"commit_before_step": "abc123"}
    assert "commit_after_step" not in json.dumps(record)


def test_trace_resume_uses_next_sequence_and_never_overwrites_raw_files(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    (run_dir / "trace.jsonl").write_text(json.dumps({"sequence": 2}) + "\nnot-json\n", encoding="utf-8")
    (run_dir / "git_tracking.jsonl").write_text(json.dumps({"sequence": 7}) + "\n", encoding="utf-8")
    raw_dir = run_dir / "raw"
    raw_dir.mkdir()
    existing_raw = raw_dir / "000007_existing_llm.txt"
    existing_raw.write_text("keep\n", encoding="utf-8")
    writer = _writer(run_dir)

    next_sequence = next_observability_sequence(run_dir)
    writer.step_finished(
        sequence=next_sequence,
        event=_step_finish(run_dir, step_name="resume step", step_kind="llm", producer_raw_output="fresh\n", verifier_raw_output=None),
        commit_before_step="abc123",
    )

    assert next_sequence == 8
    assert existing_raw.read_text(encoding="utf-8") == "keep\n"
    assert (run_dir / "raw" / "000008_resume_step_llm.txt").read_text(encoding="utf-8") == "fresh\n"

    with pytest.raises(RuntimeTraceError, match="refusing to overwrite existing raw output file"):
        writer.step_finished(
            sequence=7,
            event=_step_finish(run_dir, step_name="existing", step_kind="llm", producer_raw_output="clobber\n", verifier_raw_output=None),
            commit_before_step="abc123",
        )


def test_trace_resume_falls_back_to_raw_sequence_when_jsonl_is_missing_or_malformed(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    (run_dir / "trace.jsonl").write_text("not-json\n", encoding="utf-8")
    (run_dir / "git_tracking.jsonl").write_text(json.dumps({"event_type": "run_initialized"}) + "\n", encoding="utf-8")
    raw_dir = run_dir / "raw"
    raw_dir.mkdir()
    (raw_dir / "000009_existing_llm.txt").write_text("keep\n", encoding="utf-8")

    assert next_observability_sequence(run_dir) == 10
