from __future__ import annotations

import json
from pathlib import Path

from botpipe.core.providers.fake import ScriptedLLMProvider
from botpipe.core.workflow_catalog import discover_workflow_catalog
from botpipe.runtime.cli import main
from botpipe.runtime.loader import resolve_workflow_reference
from botpipe.workflows.goal import GOAL_OBJECTIVE_MAX_CHARS, Goal, parse_goal_request


def _provider_factory(**_kwargs):
    return ScriptedLLMProvider()


def _run_goal(tmp_path: Path, message: str, *, task_id: str = "goal-thread") -> None:
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


def _goal_state(tmp_path: Path, *, task_id: str = "goal-thread") -> dict[str, object]:
    state_path = tmp_path / ".botpipe" / "tasks" / task_id / "goal" / "goal.json"
    return json.loads(state_path.read_text(encoding="utf-8"))


def _goal_status(tmp_path: Path, *, task_id: str = "goal-thread") -> str:
    status_path = tmp_path / ".botpipe" / "tasks" / task_id / "wf_goal" / "goal_status.md"
    return status_path.read_text(encoding="utf-8")


def test_goal_workflow_is_packaged_and_resolvable(tmp_path: Path) -> None:
    entries = {entry.workflow_name: entry for entry in discover_workflow_catalog(tmp_path)}
    goal = entries["goal"]

    assert goal.source_root_kind == "package"
    assert goal.package_module == "botpipe.workflows.goal"
    assert goal.workflow_module == "botpipe.workflows.goal.workflow"
    assert goal.aliases == ("/goal",)

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

    bare_objective = parse_goal_request("Finish the migration and keep tests green")
    assert bare_objective.action == "set"
    assert bare_objective.objective == "Finish the migration and keep tests green"

    too_long = parse_goal_request("/goal " + ("x" * (GOAL_OBJECTIVE_MAX_CHARS + 1)))
    assert too_long.action == "invalid"
    assert "at most 4000" in (too_long.error or "")


def test_goal_workflow_sets_views_pauses_resumes_and_clears_task_goal(
    tmp_path: Path,
    capsys,
) -> None:
    _run_goal(tmp_path, "/goal Finish the migration and keep tests green")
    capsys.readouterr()
    state = _goal_state(tmp_path)
    assert state["objective"] == "Finish the migration and keep tests green"
    assert state["status"] == "active"
    assert state["last_command"] == "set"

    _run_goal(tmp_path, "/goal")
    capsys.readouterr()
    assert "Finish the migration and keep tests green" in _goal_status(tmp_path)
    assert _goal_state(tmp_path)["last_command"] == "view"

    _run_goal(tmp_path, "/goal pause")
    capsys.readouterr()
    state = _goal_state(tmp_path)
    assert state["status"] == "paused"
    assert state["last_command"] == "pause"

    _run_goal(tmp_path, "/goal resume")
    capsys.readouterr()
    state = _goal_state(tmp_path)
    assert state["status"] == "active"
    assert state["last_command"] == "resume"

    _run_goal(tmp_path, "/goal clear")
    capsys.readouterr()
    state = _goal_state(tmp_path)
    assert state["status"] == "unset"
    assert state["objective"] is None
    assert state["last_command"] == "clear"


def test_invalid_goal_objective_does_not_destroy_existing_goal(tmp_path: Path, capsys) -> None:
    _run_goal(tmp_path, "/goal Keep the existing goal")
    capsys.readouterr()

    _run_goal(tmp_path, "/goal " + ("x" * (GOAL_OBJECTIVE_MAX_CHARS + 1)))
    capsys.readouterr()

    state = _goal_state(tmp_path)
    assert state["objective"] == "Keep the existing goal"
    assert state["status"] == "active"
    assert state["last_command"] == "invalid"
    assert "at most 4000" in _goal_status(tmp_path)
