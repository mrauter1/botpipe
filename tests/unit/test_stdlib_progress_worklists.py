from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from autoloop.core.artifacts import Artifact
from autoloop.core.context import Context
from autoloop.core.errors import WorkflowExecutionError
from autoloop.core.stores import InMemorySessionStore
from autoloop.core.worklists import WorkItem
from autoloop.stdlib import (
    ProgressBoard,
    ProgressItem,
    ProgressJsonCollectionSource,
    SKIPPABLE_WORK_STATUS_POLICY,
    WorkStatus,
    WorkStatusPolicy,
    progress_artifact_worklist,
)


class _State(BaseModel):
    pass


class PhaseItem(ProgressItem):
    objective: str


class PhasePlan(ProgressBoard[PhaseItem]):
    pass


def _context(tmp_path: Path) -> Context:
    return Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="progress-workflow",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_progress_workflow",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )


def _artifact() -> Artifact:
    return Artifact.json("{workflow_folder}/worklists/phase.json", name="phase_board")


def test_work_status_policy_default_statuses_are_minimal() -> None:
    assert WorkStatusPolicy().statuses == (
        "planned",
        "in_progress",
        "blocked",
        "completed",
        "failed",
    )


def test_work_status_policy_supports_extra_statuses() -> None:
    policy = WorkStatusPolicy(extra_statuses=("skipped",))
    assert policy.statuses == (
        "planned",
        "in_progress",
        "blocked",
        "completed",
        "failed",
        "skipped",
    )
    assert policy.normalize("skipped") == "skipped"


def test_work_status_policy_can_enable_skipped() -> None:
    assert SKIPPABLE_WORK_STATUS_POLICY.normalize("skipped") == "skipped"
    assert SKIPPABLE_WORK_STATUS_POLICY.is_terminal("skipped") is True


def test_work_status_policy_normalizes_aliases() -> None:
    policy = WorkStatusPolicy()
    assert policy.normalize("  started  ") == WorkStatus.in_progress.value
    assert policy.normalize("In Progress") == WorkStatus.in_progress.value


def test_work_status_policy_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="unsupported work status"):
        WorkStatusPolicy().normalize("ready")


def test_progress_board_base_model_accepts_items() -> None:
    plan = PhasePlan(
        items=[
            PhaseItem(
                id="p1",
                title="Phase 1",
                objective="Ship the feature",
            )
        ]
    )
    assert plan.items[0].status == WorkStatus.planned.value
    assert plan.items[0].objective == "Ship the feature"


def test_progress_source_loads_canonical_items_collection(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    path = ctx.workflow_folder / "worklists" / "phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"items": [{"id": "p1", "title": "Phase 1", "status": "planned"}]}) + "\n",
        encoding="utf-8",
    )
    source = ProgressJsonCollectionSource(artifact=_artifact())

    items = source.load(ctx)

    assert [item.id for item in items] == ["p1"]
    assert items[0].status == "planned"


def test_progress_source_rejects_missing_items_collection(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    path = ctx.workflow_folder / "worklists" / "phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"phases": []}) + "\n", encoding="utf-8")

    with pytest.raises(WorkflowExecutionError, match=r"must contain an 'items' list"):
        ProgressJsonCollectionSource(artifact=_artifact()).load(ctx)


def test_progress_source_rejects_non_object_item(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    path = ctx.workflow_folder / "worklists" / "phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": ["bad"]}) + "\n", encoding="utf-8")

    with pytest.raises(WorkflowExecutionError, match=r"non-object entry in 'items'"):
        ProgressJsonCollectionSource(artifact=_artifact()).load(ctx)


def test_progress_source_rejects_missing_id(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    path = ctx.workflow_folder / "worklists" / "phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": [{"title": "Phase 1"}]}) + "\n", encoding="utf-8")

    with pytest.raises(WorkflowExecutionError, match=r"field 'id' must be a non-empty string"):
        ProgressJsonCollectionSource(artifact=_artifact()).load(ctx)


def test_progress_source_rejects_missing_title(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    path = ctx.workflow_folder / "worklists" / "phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": [{"id": "p1"}]}) + "\n", encoding="utf-8")

    with pytest.raises(WorkflowExecutionError, match=r"item 'p1' field 'title' must be a non-empty string"):
        ProgressJsonCollectionSource(artifact=_artifact()).load(ctx)


def test_progress_source_normalizes_missing_status_to_initial(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    path = ctx.workflow_folder / "worklists" / "phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": [{"id": "p1", "title": "Phase 1"}]}) + "\n", encoding="utf-8")

    items = ProgressJsonCollectionSource(artifact=_artifact()).load(ctx)

    assert items[0].status == WorkStatus.planned.value


def test_progress_source_rejects_duplicate_ids(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    path = ctx.workflow_folder / "worklists" / "phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "items": [
                    {"id": "p1", "title": "Phase 1"},
                    {"id": "p1", "title": "Phase 1 again"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkflowExecutionError, match=r"duplicate item id 'p1'"):
        ProgressJsonCollectionSource(artifact=_artifact()).load(ctx)


def test_progress_source_validates_with_pydantic_model(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    path = ctx.workflow_folder / "worklists" / "phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "p1",
                        "title": "Phase 1",
                        "objective": "Ship the feature",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source = ProgressJsonCollectionSource(artifact=_artifact(), model=PhasePlan)

    items = source.load(ctx)

    assert items[0].payload["objective"] == "Ship the feature"
    assert items[0].status == WorkStatus.planned.value


def test_progress_source_writes_fallback_when_missing(tmp_path: Path) -> None:
    ctx = _context(tmp_path)

    def fallback(_ctx: Context) -> dict[str, object]:
        return {"items": [{"id": "p1", "title": "Phase 1"}]}

    source = ProgressJsonCollectionSource(artifact=_artifact(), fallback=fallback)
    source.ensure(ctx)

    payload = json.loads((ctx.workflow_folder / "worklists" / "phase.json").read_text(encoding="utf-8"))
    assert payload["items"][0]["status"] == WorkStatus.planned.value


def test_progress_source_missing_without_fallback_fails(tmp_path: Path) -> None:
    with pytest.raises(WorkflowExecutionError, match="is missing at"):
        ProgressJsonCollectionSource(artifact=_artifact()).load(_context(tmp_path))


def test_progress_source_save_updates_status_only(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    path = ctx.workflow_folder / "worklists" / "phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "items": [
                    {"id": "p1", "title": "Phase 1", "status": "planned", "objective": "Keep me"},
                    {"id": "p2", "title": "Phase 2", "status": "planned", "objective": "Also keep me"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source = ProgressJsonCollectionSource(artifact=_artifact())

    source.save(
        ctx,
        (
            WorkItem(
                id="p2",
                title="Phase 2",
                payload={"id": "p2", "title": "Phase 2", "objective": "Also keep me"},
                status="completed",
            ),
        ),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["items"][0] == {
        "id": "p1",
        "title": "Phase 1",
        "status": "planned",
        "objective": "Keep me",
    }
    assert payload["items"][1] == {
        "id": "p2",
        "title": "Phase 2",
        "status": "completed",
        "objective": "Also keep me",
    }


def test_progress_source_save_preserves_order(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    path = ctx.workflow_folder / "worklists" / "phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "items": [
                    {"id": "p1", "title": "Phase 1", "status": "planned"},
                    {"id": "p2", "title": "Phase 2", "status": "planned"},
                    {"id": "p3", "title": "Phase 3", "status": "planned"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source = ProgressJsonCollectionSource(artifact=_artifact())

    source.save(
        ctx,
        (
            WorkItem(id="p3", title="Phase 3", payload={"id": "p3", "title": "Phase 3"}, status="completed"),
            WorkItem(id="p1", title="Phase 1", payload={"id": "p1", "title": "Phase 1"}, status="blocked"),
        ),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [item["id"] for item in payload["items"]] == ["p1", "p2", "p3"]


def test_progress_artifact_worklist_uses_default_artifact_path() -> None:
    worklist = progress_artifact_worklist("phase", model=PhasePlan)
    assert worklist.artifact is not None
    assert worklist.artifact.template == "{workflow_folder}/worklists/phase.json"
    assert worklist.artifact.name == "phase_board"


def test_progress_artifact_worklist_uses_default_selector_names() -> None:
    worklist = progress_artifact_worklist("phase", model=PhasePlan)
    assert worklist.selector.item_param == "phase"
    assert worklist.selector.start_param == "from_phase"
    assert worklist.selector.end_param == "to_phase"
    assert worklist.selector.mode_param == "phase_mode"
