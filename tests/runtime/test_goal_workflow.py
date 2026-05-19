from __future__ import annotations

import json
from pathlib import Path

from botpipe import Outcome
from botpipe.core.providers.fake import ScriptedLLMProvider
from botpipe.core.workflow_catalog import discover_workflow_catalog
from botpipe.runtime.cli import main
from botpipe.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from botpipe.runtime.loader import resolve_workflow_reference
from botpipe.runtime.runner import RunnerOptions, run_workflow_package
from botpipe.workflows.goal import (
    GOAL_OBJECTIVE_MAX_CHARS,
    Goal,
    GoalPlan,
    GoalState,
    apply_goal_command,
    mark_plan_item_done,
    next_pending_item,
    parse_goal_request,
)


def _provider_factory(**_kwargs):
    return ScriptedLLMProvider()


def _runner_options(root: Path, **kwargs: object) -> RunnerOptions:
    kwargs.setdefault(
        "runtime_config",
        RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
    )
    return RunnerOptions(root=root, **kwargs)


def _run_goal_command(tmp_path: Path, message: str, *, task_id: str = "goal-thread") -> None:
    exit_code = main(
        [
            "run",
            "goal",
            message,
            "--task",
            task_id,
            "--workspace",
            str(tmp_path),
            "--no-git",
            "--progress",
            "off",
        ],
        provider_factory=_provider_factory,
    )
    assert exit_code == 0


def _goal_state_path(tmp_path: Path, *, task_id: str = "goal-thread") -> Path:
    return tmp_path / ".botpipe" / "tasks" / task_id / "goal" / "goal.json"


def _goal_state(tmp_path: Path, *, task_id: str = "goal-thread") -> dict[str, object]:
    return json.loads(_goal_state_path(tmp_path, task_id=task_id).read_text(encoding="utf-8"))


def _write_goal_state(tmp_path: Path, state: GoalState, *, task_id: str = "goal-thread") -> None:
    state_path = _goal_state_path(tmp_path, task_id=task_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _goal_plan(tmp_path: Path, *, task_id: str = "goal-thread", run_id: str = "goal-run") -> dict[str, object]:
    plan_path = tmp_path / ".botpipe" / "tasks" / task_id / "wf_goal" / "runs" / run_id / "goal_plan.json"
    return json.loads(plan_path.read_text(encoding="utf-8"))


def _goal_status(tmp_path: Path, *, task_id: str = "goal-thread") -> str:
    status_path = tmp_path / ".botpipe" / "tasks" / task_id / "wf_goal" / "goal_status.md"
    return status_path.read_text(encoding="utf-8")


def test_goal_workflow_is_packaged_and_resolvable(tmp_path: Path) -> None:
    entries = {entry.workflow_name: entry for entry in discover_workflow_catalog(tmp_path)}
    goal = entries["goal"]

    assert goal.source_root_kind == "package"
    assert goal.package_module == "botpipe.workflows.goal"
    assert goal.workflow_module == "botpipe.workflows.goal.workflow"
    assert goal.aliases == ()

    resolved = resolve_workflow_reference(tmp_path, "goal")
    assert resolved.reference.workflow_name == "goal"
    assert resolved.workflow_cls is Goal


def test_parse_goal_request_matches_codex_goal_commands() -> None:
    assert parse_goal_request("/goal").action == "view"
    assert parse_goal_request("/goal status").action == "view"
    assert parse_goal_request("/goal pause").action == "pause"
    assert parse_goal_request("/goal resume").action == "resume"
    assert parse_goal_request("/goal clear").action == "clear"

    set_command = parse_goal_request("/goal Finish the migration and keep tests green")
    assert set_command.action == "set"
    assert set_command.objective == "Finish the migration and keep tests green"

    criteria_command = parse_goal_request(
        "/goal Ship the feature\nAcceptance Criteria:\n- Tests pass\n- Docs are updated"
    )
    assert criteria_command.action == "set"
    assert criteria_command.objective == "Ship the feature"
    assert criteria_command.acceptance_criteria == ("Tests pass", "Docs are updated")

    bare_objective = parse_goal_request("Finish the migration and keep tests green")
    assert bare_objective.action == "set"
    assert bare_objective.objective == "Finish the migration and keep tests green"

    too_long = parse_goal_request("/goal " + ("x" * (GOAL_OBJECTIVE_MAX_CHARS + 1)))
    assert too_long.action == "invalid"
    assert "at most 4000" in (too_long.error or "")


def test_apply_goal_command_and_todo_helpers() -> None:
    state = GoalState()
    command = parse_goal_request("/goal Ship the feature\nCriteria:\n- Tests pass")
    active, note, ok = apply_goal_command(state, command, now="2026-05-19T00:00:00Z")

    assert ok is True
    assert note == "Goal set; execution loop will start."
    assert active.objective == "Ship the feature"
    assert active.acceptance_criteria == ["Tests pass"]
    assert active.status == "active"

    plan = GoalPlan(
        objective="Ship the feature",
        acceptance_criteria=["Tests pass"],
        items=[
            {"id": "item-1", "title": "Implement", "goal": "Implement the feature"},
            {"id": "item-2", "title": "Test", "goal": "Test the feature"},
        ],
    )
    assert next_pending_item(plan).id == "item-1"
    plan = mark_plan_item_done(plan, "item-1")
    assert plan.items[0].status == "done"
    assert next_pending_item(plan).id == "item-2"


def test_goal_workflow_state_commands_pause_view_and_clear_without_provider(
    tmp_path: Path,
    capsys,
) -> None:
    _write_goal_state(
        tmp_path,
        GoalState(
            objective="Keep the existing goal",
            acceptance_criteria=["Existing criterion"],
            status="active",
            last_command="set",
        ),
    )

    _run_goal_command(tmp_path, "/goal pause")
    capsys.readouterr()
    state = _goal_state(tmp_path)
    assert state["objective"] == "Keep the existing goal"
    assert state["status"] == "paused"
    assert state["last_command"] == "pause"

    _run_goal_command(tmp_path, "/goal")
    capsys.readouterr()
    assert "Keep the existing goal" in _goal_status(tmp_path)
    assert _goal_state(tmp_path)["last_command"] == "view"

    _run_goal_command(tmp_path, "/goal clear")
    capsys.readouterr()
    state = _goal_state(tmp_path)
    assert state["status"] == "unset"
    assert state["objective"] is None
    assert state["last_command"] == "clear"


def test_goal_workflow_executes_todo_loop_until_goal_is_met(tmp_path: Path) -> None:
    def plan_producer(request):
        goal_state = request.artifacts.goal_state.read_model()
        request.artifacts.goal_plan.write_json(
            {
                "schema_version": "botpipe.goal_plan/v1",
                "objective": goal_state.objective,
                "acceptance_criteria": goal_state.acceptance_criteria,
                "items": [
                    {
                        "id": "item-1",
                        "title": "Create output file",
                        "status": "planned",
                        "goal": "Create goal_output.txt",
                        "acceptance_checks": ["goal_output.txt exists"],
                    }
                ],
            }
        )
        return "planned"

    def plan_verifier(request):
        request.artifacts.plan_review.write_text("Plan accepted.\n")
        return Outcome(raw_output="accepted", tag="accepted", reason="Plan covers the goal.")

    def item_producer(request):
        (Path(request.context.root) / "goal_output.txt").write_text("done\n", encoding="utf-8")
        return "implemented"

    def item_verifier(request):
        current_item = request.artifacts.current_item.read_json()
        assert current_item["id"] == "item-1"
        assert (Path(request.context.root) / "goal_output.txt").is_file()
        request.artifacts.implementation_review.write_text("Item accepted.\n")
        return Outcome(raw_output="accepted", tag="accepted", reason="Item is complete.")

    def goal_producer(request):
        request.artifacts.goal_evidence.write_text("goal_output.txt exists.\n")
        return "evidence"

    def goal_verifier(request):
        request.artifacts.goal_review.write_text("Goal accepted.\n")
        return Outcome(raw_output="accepted", tag="accepted", reason="Acceptance criteria are met.")

    provider = ScriptedLLMProvider(
        producer_turns=[plan_producer, item_producer, goal_producer],
        verifier_turns=[plan_verifier, item_verifier, goal_verifier],
    )

    result = run_workflow_package(
        "goal",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="goal-thread",
            run_id="goal-run",
            message="/goal Create output file\nAcceptance Criteria:\n- goal_output.txt exists",
        ),
    )

    assert result.terminal == "FINISH"
    assert (tmp_path / "goal_output.txt").read_text(encoding="utf-8") == "done\n"

    state = _goal_state(tmp_path)
    assert state["objective"] == "Create output file"
    assert state["acceptance_criteria"] == ["goal_output.txt exists"]
    assert state["status"] == "met"
    assert state["last_command"] == "met"

    plan = _goal_plan(tmp_path)
    assert plan["items"][0]["status"] == "done"
    assert "[done] item-1" in _goal_status(tmp_path)
    assert [(call.kind, call.step_name) for call in provider.calls] == [
        ("producer", "plan"),
        ("verifier", "plan"),
        ("producer", "execute_item"),
        ("verifier", "execute_item"),
        ("producer", "verify_goal"),
        ("verifier", "verify_goal"),
    ]


def test_invalid_goal_objective_does_not_destroy_existing_goal(tmp_path: Path, capsys) -> None:
    _write_goal_state(
        tmp_path,
        GoalState(
            objective="Keep the existing goal",
            acceptance_criteria=["Existing criterion"],
            status="active",
            last_command="set",
        ),
    )

    _run_goal_command(tmp_path, "/goal " + ("x" * (GOAL_OBJECTIVE_MAX_CHARS + 1)))
    capsys.readouterr()

    state = _goal_state(tmp_path)
    assert state["objective"] == "Keep the existing goal"
    assert state["status"] == "active"
    assert state["last_command"] == "invalid"
    assert "at most 4000" in _goal_status(tmp_path)
