from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

import botlane.core.compiler as workflow_compiler
from botlane.core import FINISH, Workflow
from botlane.core.engine import Engine
from botlane.core.errors import WorkflowExecutionError
from botlane.core.primitives import Outcome
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.steps import PromptStep
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore
from botlane.simple import Effects
from botlane.stdlib import (
    ProgressBoard,
    ProgressItem,
    SKIPPABLE_WORK_STATUS_POLICY,
    WorkStatusPolicy,
    progress_artifact_worklist,
)


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir(parents=True)
    run_folder.mkdir(parents=True)
    return task_folder, run_folder


class PhaseItem(ProgressItem):
    objective: str


class PhasePlan(ProgressBoard[PhaseItem]):
    pass


def _phase_plan(statuses: tuple[str, ...] | None = None) -> PhasePlan:
    raw_statuses = statuses or ("planned", "planned", "planned", "planned", "planned")
    return PhasePlan(
        items=[
            PhaseItem(id="p1", title="Phase 1", objective="One", status=raw_statuses[0]),
            PhaseItem(id="p2", title="Phase 2", objective="Two", status=raw_statuses[1]),
            PhaseItem(id="p3", title="Phase 3", objective="Three", status=raw_statuses[2]),
            PhaseItem(id="p4", title="Phase 4", objective="Four", status=raw_statuses[3]),
            PhaseItem(id="p5", title="Phase 5", objective="Five", status=raw_statuses[4]),
        ]
    )


def _make_workflow(*, status_policy: WorkStatusPolicy | None = None, statuses: tuple[str, ...] | None = None):
    def implicit_phase_plan(_ctx):
        return _phase_plan(statuses)

    def after_assess(ctx):
        item = ctx.item
        assert item is not None
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, item.id]})
        return Effects.complete_and_advance(exhausted="done")

    class ProgressRuntimeWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        phase = progress_artifact_worklist(
            "phase",
            model=PhasePlan,
            fallback=implicit_phase_plan,
            status_policy=status_policy,
        )
        assess = PromptStep(name="assess", producer="assess.md", scope=phase, after=after_assess)
        entry = assess
        transitions = {assess: {"accepted": assess, "done": FINISH}}

    return ProgressRuntimeWorkflow


def _run(
    tmp_path: Path,
    *,
    workflow_params: dict[str, object] | None = None,
    turn_count: int = 5,
    status_policy: WorkStatusPolicy | None = None,
    statuses: tuple[str, ...] | None = None,
):
    task_folder, run_folder = _workspace(tmp_path)
    workflow_cls = _make_workflow(status_policy=status_policy, statuses=statuses)
    workflow_compiler._COMPILED_WORKFLOW_CACHE.clear()
    result = Engine(
        workflow_cls,
        provider=ScriptedLLMProvider(
            llm_turns=[Outcome(raw_output=f"ok-{index}", tag="accepted") for index in range(turn_count)]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-progress",
        run_id="run-progress",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params=workflow_params or {},
    )
    workflow_folder = task_folder / "wf_progress_runtime_workflow"
    return result, workflow_folder


def test_progress_worklist_default_all_processes_all_items(tmp_path: Path) -> None:
    result, workflow_folder = _run(tmp_path, turn_count=5)

    payload = json.loads((workflow_folder / "worklists" / "phase.json").read_text(encoding="utf-8"))
    assert result.terminal == FINISH
    assert result.state.seen == ["p1", "p2", "p3", "p4", "p5"]
    assert [item["status"] for item in payload["items"]] == [
        "completed",
        "completed",
        "completed",
        "completed",
        "completed",
    ]


def test_progress_worklist_single_processes_selected_item(tmp_path: Path) -> None:
    result, workflow_folder = _run(
        tmp_path,
        workflow_params={"phase_mode": "single", "phase": "p3"},
        turn_count=1,
    )

    payload = json.loads((workflow_folder / "worklists" / "phase.json").read_text(encoding="utf-8"))
    assert result.state.seen == ["p3"]
    assert [item["status"] for item in payload["items"]] == [
        "planned",
        "planned",
        "completed",
        "planned",
        "planned",
    ]


def test_progress_worklist_up_to_processes_prefix(tmp_path: Path) -> None:
    result, workflow_folder = _run(
        tmp_path,
        workflow_params={"phase_mode": "up_to", "phase": "p3"},
        turn_count=3,
    )

    payload = json.loads((workflow_folder / "worklists" / "phase.json").read_text(encoding="utf-8"))
    assert result.state.seen == ["p1", "p2", "p3"]
    assert [item["status"] for item in payload["items"]] == [
        "completed",
        "completed",
        "completed",
        "planned",
        "planned",
    ]


def test_progress_worklist_from_to_processes_inclusive_range(tmp_path: Path) -> None:
    result, workflow_folder = _run(
        tmp_path,
        workflow_params={"phase_mode": "from_to", "from_phase": "p2", "to_phase": "p4"},
        turn_count=3,
    )

    payload = json.loads((workflow_folder / "worklists" / "phase.json").read_text(encoding="utf-8"))
    assert result.state.seen == ["p2", "p3", "p4"]
    assert [item["status"] for item in payload["items"]] == [
        "planned",
        "completed",
        "completed",
        "completed",
        "planned",
    ]


def test_progress_worklist_invalid_range_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(WorkflowExecutionError, match=r"selector mode 'from_to' has invalid range"):
        _run(
            tmp_path,
            workflow_params={"phase_mode": "from_to", "from_phase": "p4", "to_phase": "p2"},
            turn_count=0,
        )


def test_progress_worklist_skipped_status_requires_opt_in_policy(tmp_path: Path) -> None:
    skipped_statuses = ("planned", "skipped", "planned", "planned", "planned")

    with pytest.raises(WorkflowExecutionError, match=r"unsupported status 'skipped'"):
        _run(tmp_path / "default", statuses=skipped_statuses)

    result, workflow_folder = _run(
        tmp_path / "skippable",
        status_policy=SKIPPABLE_WORK_STATUS_POLICY,
        statuses=skipped_statuses,
        turn_count=5,
    )

    payload = json.loads((workflow_folder / "worklists" / "phase.json").read_text(encoding="utf-8"))
    assert result.terminal == FINISH
    assert payload["items"][1]["status"] == "completed"
