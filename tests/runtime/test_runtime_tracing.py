from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from pathlib import Path

import autoloop.simple as simple
import pytest
from pydantic import BaseModel

from autoloop.core.extensions import HookRouteRedirect, RunBinding, StepFinish, StepStart, TerminalFinish
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.providers.models import (
    LLMRequest,
    OutcomeResponse,
    ProducerRequest,
    ProducerResponse,
    StepProviderUsage,
    TokenUsage,
    VerifierRequest,
)
from autoloop.core.primitives import Event, Outcome
from autoloop.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig, TracingRuntimeConfig
from autoloop.runtime.runner import RunnerOptions, execute_workflow_package
from autoloop.core.schema_registry import RUNTIME_TRACE_SCHEMA, RUN_METADATA_SCHEMA, WORKFLOW_STATIC_STEP_GRAPH_SCHEMA
from autoloop.runtime.tracing import RuntimeTraceError, RuntimeTraceWriter
from autoloop.runtime.workspace import next_observability_sequence


class _State(BaseModel):
    note: str = ""


class _TracingAsyncLLMProvider:
    def __init__(
        self,
        *,
        delays: dict[str, float] | None = None,
        fail_steps: set[str] | None = None,
    ) -> None:
        self.delays = delays or {}
        self.fail_steps = fail_steps or set()

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:  # pragma: no cover - defensive
        raise AssertionError("sync producer path should not be used")

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:  # pragma: no cover - defensive
        raise AssertionError("sync verifier path should not be used")

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:  # pragma: no cover - defensive
        raise AssertionError("sync llm path should not be used")

    def run_operation(self, request: object) -> object:  # pragma: no cover - defensive
        raise AssertionError("operation path should not be used")

    async def run_producer_async(self, request: ProducerRequest) -> ProducerResponse:
        raise AssertionError("producer path should not be used")

    async def run_verifier_async(self, request: VerifierRequest) -> OutcomeResponse:
        raise AssertionError("verifier path should not be used")

    async def run_llm_async(self, request: LLMRequest) -> OutcomeResponse:
        await asyncio.sleep(self.delays.get(request.step_name, 0.01))
        if request.step_name in self.fail_steps:
            raise RuntimeError(f"{request.step_name} failed")
        return OutcomeResponse(outcome=Outcome(raw_output=f"{request.step_name} ok", tag="done"))


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
            "schema": WORKFLOW_STATIC_STEP_GRAPH_SCHEMA,
            "workflow_name": "demo",
            "steps": [],
            "transitions": {"steps": {}, "global": {}},
        },
    )


def _step_start(run_dir: Path, *, step_name: str = "assessment", step_kind: str = "produce_verify") -> StepStart:
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
    step_kind: str = "produce_verify",
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


def _terminal(run_dir: Path, *, terminal: str = "FINISH") -> TerminalFinish:
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
    assert run_meta["schema"] == RUN_METADATA_SCHEMA
    assert run_meta["tracing"]["enabled"] is True
    assert run_meta["tracing"]["trace_file"] == "trace.jsonl"


def test_runtime_trace_initialization_persists_static_step_graph(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    _writer(run_dir)

    payload = json.loads((run_dir / "static_step_graph.json").read_text(encoding="utf-8"))

    assert payload["schema"] == WORKFLOW_STATIC_STEP_GRAPH_SCHEMA
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


def test_runtime_trace_records_step_execution_identity(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)
    start = StepStart(
        binding=_binding(run_dir),
        step_name="assessment",
        step_kind="produce_verify",
        state=_State(note="before"),
        visit=3,
        step_execution_id="assessment:articles:item-7:3",
        scope="articles",
        item_id="item-7",
    )
    finish = StepFinish(
        binding=_binding(run_dir),
        step_name="assessment",
        step_kind="produce_verify",
        state_before=_State(note="before"),
        state_after=_State(note="after"),
        event=Event(tag="approved", reason="ok"),
        outcome=Outcome(raw_output="raw", tag="approved", reason="ok"),
        visit=3,
        step_execution_id="assessment:articles:item-7:3",
        scope="articles",
        item_id="item-7",
    )

    writer.step_started(sequence=1, event=start, commit_before_step="abc123")
    writer.step_finished(sequence=1, event=finish, commit_before_step="abc123")

    records = [
        json.loads(line)
        for line in (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert records[0]["visit"] == 3
    assert records[0]["step_execution_id"] == "assessment:articles:item-7:3"
    assert records[0]["scope"] == "articles"
    assert records[0]["item_id"] == "item-7"
    assert records[1]["visit"] == 3
    assert records[1]["step_execution_id"] == "assessment:articles:item-7:3"
    assert records[1]["scope"] == "articles"
    assert records[1]["item_id"] == "item-7"


def test_runtime_trace_writes_produce_verify_raw_producer_and_verifier_files(tmp_path: Path) -> None:
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
        step_kind="step",
        producer_raw_output="step output\n",
        verifier_raw_output=None,
    )

    writer.step_finished(sequence=2, event=event, commit_before_step="abc123")

    assert (run_dir / "raw" / "000002_survey_step.txt").read_text(encoding="utf-8") == "step output\n"


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
        candidate_route="ready",
        final_route="question",
        hook_route_override_from="ready",
        hook_route_override_to="question",
        hook_route_redirects=(
            HookRouteRedirect(
                hook="reroute_to_question",
                phase="on_taken",
                from_route="ready",
                to_route="question",
            ),
        ),
    )

    writer.step_finished(sequence=1, event=event, commit_before_step="abc123")

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["candidate_route"] == "ready"
    assert record["final_route"] == "question"
    assert record["hook_route_override"] == {"from": "ready", "to": "question"}
    assert record["hook_route_redirects"] == [
        {
            "hook": "reroute_to_question",
            "phase": "on_taken",
            "from_route": "ready",
            "to_route": "question",
        }
    ]


def test_runtime_trace_records_direct_runtime_control_metadata(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)
    event = StepFinish(
        binding=_binding(run_dir),
        step_name="assessment",
        step_kind="produce_verify",
        state_before=_State(note="before"),
        state_after=_State(note="after"),
        event=None,
        outcome=Outcome(raw_output="hidden raw", tag="ready", reason="validated"),
        producer_raw_output="producer output\n",
        verifier_raw_output="verifier output\n",
        candidate_route="ready",
        runtime_control="request_input",
        pending_input_id="pending-approval-1",
        terminal="AWAIT_INPUT",
        provider_attributable=False,
        provider_attempted=True,
        producer_attempted=True,
        verifier_attempted=False,
        source_hook="ask_for_input",
        source_phase="on_taken",
    )

    writer.step_finished(sequence=1, event=event, commit_before_step="abc123")

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["candidate_route"] == "ready"
    assert record["runtime_control"] == "request_input"
    assert record["pending_input_id"] == "pending-approval-1"
    assert record["terminal"] == "AWAIT_INPUT"
    assert record["provider_attributable"] is False
    assert record["provider_attempted"] is True
    assert record["producer_attempted"] is True
    assert record["verifier_attempted"] is False
    assert record["source_hook"] == "ask_for_input"
    assert record["source_phase"] == "on_taken"


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


def test_runtime_trace_records_generic_runtime_events(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir)

    writer.runtime_event(
        event_type="provider_attempt_finished",
        step_name="assessment",
        turn_kind="verifier",
        attempt=2,
        visit=4,
        step_execution_id="assessment:4",
        token_usage={"total_tokens": 9, "input_tokens": 4},
    )

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["event_type"] == "provider_attempt_finished"
    assert record["schema"] == RUNTIME_TRACE_SCHEMA
    assert record["step_name"] == "assessment"
    assert record["attempt"] == 2
    assert record["visit"] == 4
    assert record["step_execution_id"] == "assessment:4"
    assert record["token_usage"] == {"total_tokens": 9, "input_tokens": 4}


def test_runtime_trace_records_branch_group_runtime_events_with_additive_metadata(tmp_path: Path) -> None:
    class BranchTraceWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            branches={
                "security": simple.python_step(lambda ctx: Event("done"), name="security_review"),
                "cost": simple.python_step(lambda ctx: Event("done"), name="cost_review"),
                "clarify": simple.python_step(lambda ctx: simple.RequestInput("Need clarification."), name="clarify_review"),
            },
            fan_in=simple.python_step(
                lambda ctx: Event("approved"),
                name="combine_reviews",
                routes={"approved": simple.FINISH},
            ),
        )

    execution = execute_workflow_package(
        BranchTraceWorkflow,
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-branch-trace",
            run_id="run-branch-trace",
            message="trace branch group events",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    assert execution.result.terminal == simple.FINISH

    trace_path = execution.run_workspace.run_dir / "trace.jsonl"
    records = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    branch_group_started = next(record for record in records if record["event_type"] == "branch_group_started")
    branch_scheduled = [record for record in records if record["event_type"] == "branch_scheduled"]
    branch_started = next(record for record in records if record["event_type"] == "branch_started")
    branch_completed = [record for record in records if record["event_type"] == "branch_completed"]
    branch_needs_input = next(record for record in records if record["event_type"] == "branch_needs_input")
    manifest_written = next(record for record in records if record["event_type"] == "branch_manifest_written")
    fan_in_started = next(record for record in records if record["event_type"] == "fan_in_started")
    fan_in_completed = next(record for record in records if record["event_type"] == "fan_in_completed")
    branch_group_completed = next(record for record in records if record["event_type"] == "branch_group_completed")

    assert branch_group_started["step_name"] == "reviews"
    assert branch_group_started["group_name"] == "reviews"
    assert branch_group_started["group_kind"] == "parallel"
    assert branch_group_started["branch_count"] == 3

    assert len(branch_scheduled) == 3
    assert {record["branch_name"] for record in branch_scheduled} == {"security", "cost", "clarify"}

    assert branch_started["branch_name"] in {"security", "cost", "clarify"}
    assert branch_started["step_name"] in {"security_review", "cost_review", "clarify_review"}
    assert branch_started["execution_id"].startswith("reviews:")

    assert len(branch_completed) == 2
    assert {record["branch_name"] for record in branch_completed} == {"security", "cost"}
    assert branch_needs_input["branch_name"] == "clarify"
    assert branch_needs_input["status"] == "needs_input"

    assert manifest_written["step_name"] == "reviews"
    assert manifest_written["artifact_paths"] == [
        "_branch_groups/reviews/results.json",
        "_branch_groups/reviews/context.md",
    ]

    assert fan_in_started["composite_step_name"] == "reviews"
    assert fan_in_started["step_name"] == "combine_reviews"
    assert fan_in_started["artifact_paths"] == [
        "_branch_groups/reviews/results.json",
        "_branch_groups/reviews/context.md",
    ]
    assert fan_in_completed["route"] == "approved"
    assert fan_in_completed["status"] == "completed"

    assert branch_group_completed["step_name"] == "reviews"
    assert branch_group_completed["status"] == "completed"
    assert branch_group_completed["route"] == "approved"


def test_runtime_trace_records_fail_fast_branch_failure_cancellation_and_skip_events(tmp_path: Path) -> None:
    class FailFastTraceWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            name="reviews",
            settle="fail_fast",
            concurrency=3,
            outcome="all_settled",
            branches={
                "explode": simple.step("Explode.", name="explode_branch", session=simple.Session.fresh()),
                "slow_a": simple.step("Slow A.", name="slow_a_branch", session=simple.Session.fresh()),
                "slow_b": simple.step("Slow B.", name="slow_b_branch", session=simple.Session.fresh()),
                "later": simple.step("Later.", name="later_branch", session=simple.Session.fresh()),
            },
            routes={"partial": simple.FINISH, "done": simple.FINISH},
        )

    execution = execute_workflow_package(
        FailFastTraceWorkflow,
        provider=_TracingAsyncLLMProvider(
            delays={
                "explode_branch": 0.01,
                "slow_a_branch": 0.2,
                "slow_b_branch": 0.2,
                "later_branch": 0.2,
            },
            fail_steps={"explode_branch"},
        ),
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-fail-fast-trace",
            run_id="run-fail-fast-trace",
            message="trace fail-fast branch group events",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    assert execution.result.terminal == simple.FINISH

    trace_path = execution.run_workspace.run_dir / "trace.jsonl"
    records = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    branch_failed = next(record for record in records if record["event_type"] == "branch_failed")
    branch_cancelled = [record for record in records if record["event_type"] == "branch_cancelled"]
    branch_skipped = next(record for record in records if record["event_type"] == "branch_skipped")
    branch_group_completed = next(record for record in records if record["event_type"] == "branch_group_completed")

    assert branch_failed["branch_name"] == "explode"
    assert branch_failed["status"] == "failed"
    assert branch_failed["error"]["message"]

    assert {record["branch_name"] for record in branch_cancelled} == {"slow_a", "slow_b"}
    assert all(record["status"] == "cancelled" for record in branch_cancelled)

    assert branch_skipped["branch_name"] == "later"
    assert branch_skipped["status"] == "skipped"
    assert branch_skipped["reason"] == "Branch was not scheduled because fail_fast stopped new branch launches."

    assert branch_group_completed["route"] == "partial"
    assert branch_group_completed["status"] == "completed"


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
    assert payload["schema"] == WORKFLOW_STATIC_STEP_GRAPH_SCHEMA
    assert payload["workflow_name"] == "demo"


def test_runtime_trace_failure_policy_record_and_continue_swallows_initialization_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr(
        "autoloop.runtime.tracing.write_static_step_graph_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("graph write failed")),
    )

    writer = RuntimeTraceWriter(
        run_dir=run_dir,
        workflow_name="demo",
        task_id="task-1",
        run_id=run_dir.name,
        config=TracingRuntimeConfig(failure_policy="record_and_continue"),
        static_step_graph={"schema": WORKFLOW_STATIC_STEP_GRAPH_SCHEMA},
    )
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert isinstance(writer, RuntimeTraceWriter)
    assert run_meta["warnings"][-1]["event_type"] == "runtime_tracing_write_failed"
    assert "graph write failed" in run_meta["warnings"][-1]["message"]


def test_runtime_trace_failure_policy_record_and_continue_swallows_step_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path)
    writer = _writer(run_dir, config=TracingRuntimeConfig(failure_policy="record_and_continue"))
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

    writer.terminal(event=_terminal(run_dir, terminal="FINISH"))

    record = json.loads((run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["event_type"] == "terminal"
    assert record["schema"] == RUNTIME_TRACE_SCHEMA
    assert record["terminal"] == "FINISH"
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
    existing_raw = raw_dir / "000007_existing_step.txt"
    existing_raw.write_text("keep\n", encoding="utf-8")
    writer = _writer(run_dir)

    next_sequence = next_observability_sequence(run_dir)
    writer.step_finished(
        sequence=next_sequence,
        event=_step_finish(run_dir, step_name="resume step", step_kind="step", producer_raw_output="fresh\n", verifier_raw_output=None),
        commit_before_step="abc123",
    )

    assert next_sequence == 8
    assert existing_raw.read_text(encoding="utf-8") == "keep\n"
    assert (run_dir / "raw" / "000008_resume_step_step.txt").read_text(encoding="utf-8") == "fresh\n"

    with pytest.raises(RuntimeTraceError, match="refusing to overwrite existing raw output file"):
        writer.step_finished(
            sequence=7,
            event=_step_finish(run_dir, step_name="existing", step_kind="step", producer_raw_output="clobber\n", verifier_raw_output=None),
            commit_before_step="abc123",
        )


def test_trace_resume_falls_back_to_raw_sequence_when_jsonl_is_missing_or_malformed(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    (run_dir / "trace.jsonl").write_text("not-json\n", encoding="utf-8")
    (run_dir / "git_tracking.jsonl").write_text(json.dumps({"event_type": "run_initialized"}) + "\n", encoding="utf-8")
    raw_dir = run_dir / "raw"
    raw_dir.mkdir()
    (raw_dir / "000009_existing_step.txt").write_text("keep\n", encoding="utf-8")

    assert next_observability_sequence(run_dir) == 10
