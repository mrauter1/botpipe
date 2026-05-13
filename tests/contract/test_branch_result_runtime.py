from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

from pydantic import BaseModel

from botpipe.core.branch_groups.manifest import BranchManifest, build_branch_manifest, render_branch_group_context
from botpipe.core.branch_groups.outcomes import select_branch_group_outcome
from botpipe.core.branch_groups.results import BranchResult
from botpipe.core.branch_groups.runtime import BranchGroupRuntime
from botpipe.core.execution_services import ExecutionServices


class _State(BaseModel):
    pass


def _branch_result(*, name: str, index: int, status: str, route: str | None = None) -> BranchResult:
    return BranchResult(
        name=name,
        index=index,
        input={"name": name},
        step_name=f"{name}_step",
        status=status,
        route=route,
        destination=None,
        runtime_control=None,
        reason=None if status == "completed" else f"{name} {status}",
        question=None,
        artifacts=(),
        raw_output_path=None,
        raw_output_paths={},
        provider_session=None,
        provider_sessions={},
        error=None,
        started_at="2026-05-09T08:00:00+00:00",
        finished_at="2026-05-09T08:00:00+00:00",
        duration_ms=0,
        usage={},
        cancellation_requested=False,
        cancellation_completed=False,
        cancellation_supported=True,
    )


def test_run_branches_returns_typed_branch_results_and_fail_fast_skips_unscheduled() -> None:
    runtime = BranchGroupRuntime(
        services=ExecutionServices(
            artifacts=SimpleNamespace(),
            events=SimpleNamespace(serialize_exception=lambda exc: {"message": str(exc)}),
            state=SimpleNamespace(
                increment_step_runtime_state=lambda store: None,
                step_runtime_visits=lambda store: 1,
            ),
        ),
        step_dispatcher=SimpleNamespace(),
        route_finalizer=SimpleNamespace(),
        operation_recorder=SimpleNamespace(),
    )
    branches = (
        SimpleNamespace(name="stop", index=0, input={"name": "stop"}, step=SimpleNamespace(name="stop_step")),
        SimpleNamespace(name="later_a", index=1, input={"name": "later_a"}, step=SimpleNamespace(name="later_a_step")),
        SimpleNamespace(name="later_b", index=2, input={"name": "later_b"}, step=SimpleNamespace(name="later_b_step")),
    )
    spec = SimpleNamespace(
        name="reviews",
        kind="parallel",
        branches=branches,
        concurrency=1,
        settle="fail_fast",
    )
    context = SimpleNamespace(_emit_runtime_event=lambda *args, **kwargs: None, _step_execution_id=None)

    async def fake_execute_branch(_spec: object, branch: object, _context: object) -> BranchResult:
        name = getattr(branch, "name")
        if name == "stop":
            return _branch_result(name="stop", index=0, status="failed")
        return _branch_result(name=name, index=getattr(branch, "index"), status="completed", route="done")

    runtime._execute_branch = fake_execute_branch  # type: ignore[method-assign]

    results = asyncio.run(runtime._run_branches(spec, context=context, state=_State()))

    assert isinstance(results, dict)
    assert all(isinstance(result, BranchResult) for result in results.values())
    assert [results[index].status for index in range(len(branches))] == ["failed", "skipped", "skipped"]


def test_typed_branch_manifest_drives_rendering_and_outcome_without_shape_changes() -> None:
    completed = _branch_result(name="security", index=0, status="completed", route="done")
    needs_input = _branch_result(name="cost", index=1, status="needs_input")
    needs_input = replace(
        needs_input,
        destination="cost_step",
        runtime_control="request_input",
        reason="Awaiting reviewer input.",
        question="Approve cost review?",
    )
    spec = SimpleNamespace(
        kind="parallel",
        name="reviews",
        concurrency=2,
        settle="wait_all",
        success_routes=("done",),
        outcome="all_settled",
    )

    manifest = build_branch_manifest(
        spec=spec,
        started_at="2026-05-09T08:00:00+00:00",
        finished_at="2026-05-09T08:00:01+00:00",
        duration_ms=1000,
        branches=[completed, needs_input],
    )
    context_text = render_branch_group_context(manifest)
    event = select_branch_group_outcome(spec, manifest, context=None)

    assert isinstance(manifest, BranchManifest)
    assert all(isinstance(branch, BranchResult) for branch in manifest.branches)
    assert manifest.to_dict()["branches"][1]["question"] == "Approve cost review?"
    assert "- cost: Approve cost review?" in context_text
    assert event.tag == "question"
    assert event.question == "cost: Approve cost review?"
