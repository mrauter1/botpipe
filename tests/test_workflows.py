from __future__ import annotations

import json
from pathlib import Path

from botpipe import Botpipe
from botpipe.discovery import discover_workflows
from botpipe.providers import FakeProvider, ProviderResponse
from botpipe.workflows.code_to_workflow import code_to_workflow
from botpipe.workflows.devloop import devloop
from botpipe.workflows.goal import goal
from botpipe.workflows.image_to_game import image_to_game
from botpipe.workflows.ralph_loop import ralph_loop


def _write(request, name: str, value) -> None:
    path = request.artifacts[name]
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value), encoding="utf-8")


def _review(review_id: str, criteria: list[str], verdict: str = "passed", **extra):
    return {
        "review_id": review_id,
        "criteria": [
            {
                "id": item,
                "verdict": verdict,
                "evidence": ["current repository evidence"],
                "reason": "checked",
            }
            for item in criteria
        ],
        "findings": [],
        "summary": "reviewed",
        "repair_target": extra.get("repair_target", "candidate"),
    }


def test_packaged_workflows_are_discoverable(tmp_path: Path) -> None:
    names = {entry.name for entry in discover_workflows(tmp_path, include_labs=False)}
    assert {
        "ralph_loop",
        "devloop",
        "goal",
        "image-to-game",
        "code_to_workflow",
    } <= names


def test_ralph_loop_replans_then_completes_real_worklist(tmp_path: Path) -> None:
    plan = {
        "goal": "ship it",
        "items": [
            {
                "id": "one",
                "title": "Do one",
                "status": "planned",
                "goal": "one",
                "acceptance_checks": ["done"],
            }
        ],
    }

    def produce(request):
        _write(request, "work", plan)
        return "planned"

    def reject(request):
        _write(request, "plan_review", "needs rework\n")
        return {"verdict": "needs_rework"}

    def accept_plan(request):
        _write(request, "plan_review", "accepted\n")
        return {"verdict": "accepted"}

    def accept_item(request):
        _write(request, "implementation_review", "accepted\n")
        return {"verdict": "accepted"}

    provider = FakeProvider(
        [produce, reject, produce, accept_plan, "implemented", accept_item]
    )
    result = Botpipe(tmp_path, provider=provider).run(
        ralph_loop, "ship it", task_id="ralph", run_id="run"
    )

    assert result.status == "completed"
    assert result.value.read_json()["items"][0]["status"] == "completed"
    assert len(provider.calls) == 6


def test_devloop_docloop_runs_phase_repair_free_path_and_final_audit(
    tmp_path: Path,
) -> None:
    request_ref = str(
        tmp_path / ".botpipe-v2" / "tasks" / "dev" / "runs" / "run" / "request.md"
    )
    phase_plan = {
        "version": 1,
        "task_id": "dev",
        "request_snapshot_ref": request_ref,
        "status": "planned",
        "phases": [
            {
                "phase_id": "p1",
                "title": "Document",
                "objective": "write docs",
                "status": "planned",
                "scope": {"in_scope": ["docs"], "out_of_scope": ["code"]},
                "dependencies": [],
                "criteria": [{"id": "P1", "text": "docs are current"}],
                "deliverables": ["README"],
                "risks": [],
                "rollback": ["revert docs"],
            }
        ],
    }

    def plan_turn(req):
        _write(req, "phase_plan", phase_plan)
        return "planned"

    def plan_review(req):
        value = _review("plan:root:1", ["request_coverage", "executable_plan"])
        _write(req, "plan_review", value)
        return value

    def implement(req):
        (tmp_path / "README.md").write_text("current docs\n")
        _write(req, "impl_notes", "# Notes\n\nUpdated docs.\n")
        return "implemented"

    def implementation_review(req):
        value = _review("implement:p1:1", ["P1"])
        _write(req, "impl_review", value)
        return value

    def audit(req):
        _write(
            req,
            "audit_result",
            {
                "version": 1,
                "task_id": "dev",
                "request_snapshot_ref": request_ref,
                "status": "passed",
                "summary": "documentation is complete",
                "gaps": [],
            },
        )
        _write(req, "gap_report", "# Gaps\n\nNone.\n")
        _write(req, "revised_request", "No follow-up required.\n")
        return "audited"

    def audit_review(req):
        value = _review(
            "audit:root:1",
            ["grounded_audit", "consistent_findings", "actionable_followup"],
        )
        _write(req, "audit_review", value)
        return value

    provider = FakeProvider(
        [plan_turn, plan_review, implement, implementation_review, audit, audit_review]
    )
    result = Botpipe(tmp_path, provider=provider).run(
        devloop, "update docs", mode="docloop", task_id="dev", run_id="run"
    )

    assert result.status == "completed"
    assert result.value.status == "passed"
    assert result.value.completed_phases == ["p1"]
    strategy = (
        tmp_path
        / ".botpipe-v2"
        / "tasks"
        / "dev"
        / "test"
        / "phases"
        / "p1"
        / "test_strategy.md"
    )
    assert "docloop mode" in strategy.read_text()
    assert len(provider.calls) == 6


def test_devloop_repairs_phase_item_and_records_skipped_followup(
    tmp_path: Path,
) -> None:
    request_ref = str(
        tmp_path / ".botpipe-v2" / "tasks" / "repair" / "runs" / "run" / "request.md"
    )
    base = {
        "version": 1,
        "task_id": "repair",
        "request_snapshot_ref": request_ref,
        "status": "planned",
        "phases": [
            {
                "phase_id": "p1",
                "title": "Build",
                "objective": "build",
                "status": "planned",
                "scope": {"in_scope": ["src"], "out_of_scope": []},
                "dependencies": [],
                "criteria": [{"id": "P1", "text": "works"}],
                "deliverables": ["src/app.py"],
                "risks": [],
                "rollback": ["revert"],
            }
        ],
    }

    def plan(req):
        _write(req, "phase_plan", base)
        return "planned"

    def plan_review(req):
        value = _review("plan:root:1", ["request_coverage", "executable_plan"])
        _write(req, "plan_review", value)
        return value

    def implementation(req):
        _write(req, "impl_notes", "# Notes\n")
        return "implemented"

    def revise_needed(req):
        value = _review(
            "implement:p1:1", ["P1"], verdict="failed", repair_target="phase_item"
        )
        _write(req, "impl_review", value)
        return value

    def revise_phase(req):
        revised = json.loads(json.dumps(base))
        revised["status"] = "in_progress"
        revised["phases"][0]["status"] = "in_progress"
        revised["phases"][0]["objective"] = "build with the missing detail"
        _write(req, "phase_plan", revised)
        _write(req, "phase_item_review", "# Phase repair\n\nClarified.\n")
        return "revised"

    def accept_phase(req):
        value = _review("phase_item:p1:1", ["bounded_repair", "executable_item"])
        _write(req, "phase_item_review_report", value)
        return value

    def accept_impl(req):
        value = _review("implement:p1:2", ["P1"])
        _write(req, "impl_review", value)
        return value

    def audit(req):
        _write(
            req,
            "audit_result",
            {
                "version": 1,
                "task_id": "repair",
                "request_snapshot_ref": request_ref,
                "status": "needs_followup",
                "summary": "validation remains",
                "gaps": [
                    {
                        "id": "g1",
                        "severity": "medium",
                        "summary": "tests skipped",
                        "evidence": ["skip marker"],
                        "followup": "run tests",
                    }
                ],
            },
        )
        _write(req, "gap_report", "# Gap\n\nTests remain.\n")
        _write(req, "revised_request", "Run the missing tests.\n")
        return "audited"

    def audit_review(req):
        value = _review(
            "audit:root:1",
            ["grounded_audit", "consistent_findings", "actionable_followup"],
        )
        _write(req, "audit_review", value)
        return value

    provider = FakeProvider(
        [
            plan,
            plan_review,
            implementation,
            revise_needed,
            revise_phase,
            accept_phase,
            implementation,
            accept_impl,
            audit,
            audit_review,
        ]
    )
    result = Botpipe(tmp_path, provider=provider).run(
        devloop,
        "build",
        skip_test_phase=True,
        auto_followup_max_depth=0,
        task_id="repair",
        run_id="run",
    )
    assert result.status == "completed"
    assert result.value.status == "needs_followup"
    followup = json.loads(Path(result.value.followup_result_path).read_text())
    assert followup["status"] == "skipped"
    assert followup["reason"] == "auto_followup_max_depth_reached"


def _goal_provider(tmp_path: Path, task_id: str) -> FakeProvider:
    def plan(req):
        goal_payload = json.loads(
            (
                tmp_path / ".botpipe-v2" / "tasks" / task_id / "goal" / "goal.json"
            ).read_text()
        )
        _write(
            req,
            "subgoals",
            {
                "schema": "botpipe.goal.subgoals/v1",
                "goal_id": goal_payload["goal_id"],
                "active_subgoal_id": None,
                "created_at": "",
                "updated_at": "",
                "subgoals": [
                    {
                        "id": "build",
                        "title": "Build",
                        "description": "build it",
                        "status": "pending",
                        "verifier_criteria": ["feature works"],
                        "dependencies": [],
                        "priority": 1,
                    }
                ],
            },
        )
        return "planned"

    def plan_review(req):
        _write(req, "plan_audit", "accepted\n")
        return {"verdict": "accepted", "coverage_summary": "covered", "risks": []}

    def work(req):
        _write(req, "subgoal_progress", "# Progress\n\nBuilt and tested.\n")
        return "worked"

    def verify(req):
        _write(req, "subgoal_audit", "# Audit\n\nComplete.\n")
        return {
            "verdict": "complete",
            "reason": "criterion proven",
            "completion_summary": "built",
            "criteria_results": {"feature works": "passed"},
            "evidence": ["test output"],
        }

    def summarize(req):
        _write(req, "goal_summary", "# Summary\n\nAll work complete.\n")
        return "summarized"

    def final(req):
        _write(req, "goal_audit", "# Final audit\n\nComplete.\n")
        return {
            "verdict": "complete",
            "reason": "objective proven",
            "completion_summary": "done",
            "evidence": ["tests"],
        }

    return FakeProvider([plan, plan_review, work, verify, summarize, final])


def test_goal_persists_objective_subgoals_and_status_commands(tmp_path: Path) -> None:
    provider = _goal_provider(tmp_path, "goal-task")
    client = Botpipe(tmp_path, provider=provider)
    completed = client.run(
        goal, "build feature", task_id="goal-task", run_id="goal-run"
    )
    assert completed.status == "completed"
    assert completed.value.status == "complete"
    assert completed.value.completed_subgoal_count == 1

    status = Botpipe(tmp_path, provider=FakeProvider([])).run(
        goal, action="status", task_id="goal-task", run_id="status-run"
    )
    assert status.status == "completed"
    assert status.value.goal_id == completed.value.goal_id
    assert status.value.objective == "build feature"


def test_goal_budget_pause_and_explicit_replan(tmp_path: Path) -> None:
    initial = _goal_provider(tmp_path, "budget")
    limited_provider = FakeProvider([next(initial._responses) for _ in range(4)])
    limited = Botpipe(tmp_path, provider=limited_provider).run(
        goal, "ship", max_goal_turns=1, task_id="budget", run_id="limited"
    )
    assert limited.status == "completed"
    assert limited.value.status == "budget_limited"

    paused = Botpipe(tmp_path, provider=FakeProvider([])).run(
        goal, action="pause", task_id="budget", run_id="paused"
    )
    assert paused.value.status == "paused"

    replanned = Botpipe(tmp_path, provider=_goal_provider(tmp_path, "budget")).run(
        goal, action="replan", max_goal_turns=5, task_id="budget", run_id="replanned"
    )
    assert replanned.status == "completed"
    assert replanned.value.status == "complete"


def test_goal_edit_resume_clear_and_missing_status(tmp_path: Path) -> None:
    initial = _goal_provider(tmp_path, "commands")
    limited_provider = FakeProvider([next(initial._responses) for _ in range(4)])
    with Botpipe(tmp_path, provider=limited_provider) as runtime:
        limited = runtime.run(
            goal, "original objective", max_goal_turns=1,
            task_id="commands", run_id="limited",
        )
        assert limited.value.status == "budget_limited"

    with Botpipe(tmp_path, provider=_goal_provider(tmp_path, "commands")) as runtime:
        edited = runtime.run(
            goal, action="edit", objective="revised objective", max_goal_turns=5,
            task_id="commands", run_id="edited",
        )
        assert edited.ok, edited.error
        assert edited.value.status == "complete"
        assert edited.value.objective == "revised objective"

    no_calls = FakeProvider([])
    with Botpipe(tmp_path, provider=no_calls) as runtime:
        resumed = runtime.run(goal, action="resume", task_id="commands")
        assert resumed.value.status == "complete"
        assert resumed.value.goal_id == edited.value.goal_id
        cleared = runtime.run(goal, action="clear", task_id="commands")
        assert cleared.value.status == "cleared"
        assert not Path(cleared.value.goal_path).exists()
        missing = runtime.run(goal, action="status", task_id="commands")
        assert missing.value.status == "missing"
    assert no_calls.calls == []


def test_goal_budget_counts_provider_contract_repair_attempts(tmp_path: Path) -> None:
    def malformed(req):
        _write(req, "subgoals", "not json")
        return ProviderResponse("bad", usage={"input_tokens": 3, "output_tokens": 3})

    def repaired(req):
        goal_payload = json.loads(
            (
                tmp_path / ".botpipe-v2" / "tasks" / "repair-budget" / "goal" / "goal.json"
            ).read_text()
        )
        _write(
            req,
            "subgoals",
            {
                "schema": "botpipe.goal.subgoals/v1",
                "goal_id": goal_payload["goal_id"],
                "subgoals": [
                    {
                        "id": "one",
                        "title": "One",
                        "description": "one",
                        "verifier_criteria": ["done"],
                    }
                ],
            },
        )
        return ProviderResponse(
            "repaired", usage={"input_tokens": 1, "output_tokens": 0}
        )

    provider = FakeProvider([malformed, repaired])
    result = Botpipe(tmp_path, provider=provider).run(
        goal, "one", token_budget=5, task_id="repair-budget", run_id="run"
    )
    assert result.status == "completed"
    assert result.value.status == "budget_limited"
    assert result.value.tokens_used == 7
    assert len(provider.calls) == 2


def test_goal_marks_repeated_identical_blocker_terminal(tmp_path: Path) -> None:
    base = _goal_provider(tmp_path, "blocked")
    plan, plan_review = next(base._responses), next(base._responses)

    def work(req):
        _write(req, "subgoal_progress", "blocked\n")
        return "blocked"

    def blocked(req):
        _write(req, "subgoal_audit", "same blocker\n")
        return {
            "verdict": "blocked",
            "reason": "external dependency",
            "blocker_fingerprint": "dep-1",
        }

    provider = FakeProvider(
        [plan, plan_review, work, blocked, work, blocked, work, blocked]
    )
    result = Botpipe(tmp_path, provider=provider).run(
        goal, "blocked work", task_id="blocked", run_id="run"
    )
    assert result.status == "completed"
    assert result.value.status == "blocked"


def test_image_to_game_builds_goal_and_runs_child(tmp_path: Path) -> None:
    image = tmp_path / "reference.png"
    image.write_bytes(b"not visually inspected")
    child_provider = _goal_provider(tmp_path, "game")

    def build(req):
        _write(req, "goal_input", "# Objective\n\nBuild the playable game.\n")
        return "built"

    def reject(req):
        _write(req, "goal_input_audit", "needs rework\n")
        return {
            "verdict": "needs_rework",
            "reference_mode": "provided_file",
            "coverage_summary": "missing a gate",
            "required_fixes": ["add browser audit"],
            "risks": [],
        }

    def verify(req):
        _write(req, "goal_input_audit", "accepted\n")
        return {
            "verdict": "accepted",
            "reference_mode": "provided_file",
            "coverage_summary": "all required headings and gates",
            "required_fixes": [],
            "risks": [],
        }

    provider = FakeProvider(
        [build, reject, build, verify, *list(child_provider._responses)]
    )
    result = Botpipe(tmp_path, provider=provider).run(
        image_to_game,
        "make a board game",
        reference_image_path=str(image),
        task_id="game",
        run_id="game-run",
    )
    assert result.status == "completed"
    assert result.value.status == "complete"
    assert result.value.reference_mode == "provided_file"
    assert Path(result.value.final_report_path).is_file()
    assert len(provider.calls) == 10


def test_code_to_workflow_runs_distill_design_build_and_publication(
    tmp_path: Path,
) -> None:
    (tmp_path / "app.py").write_text("print('hello')\n")

    def distill(req):
        _write(
            req,
            "behavior_inventory",
            {"behaviors": [{"id": "hello", "required": True}]},
        )
        _write(req, "behavior_inventory_report", "# Behaviors\n\nhello\n")
        _write(req, "trace_pattern_notes", "# Traces\n\nnone\n")
        return "distilled"

    def distill_review(req):
        _write(req, "behavior_review", "accepted\n")
        return {
            "verdict": "behavior_distilled",
            "summary": "covered",
            "behavior_count": 1,
            "evidence_artifacts": ["behavior_inventory.json"],
            "uncovered_areas": [],
        }

    def design(req):
        _write(req, "workflow_design", "# Design\n\nOne workflow.\n")
        _write(req, "step_contracts", {"functions": ["generated"]})
        _write(req, "prompt_contract_matrix", "# Prompts\n")
        _write(req, "equivalence_plan", "# Equivalence\n")
        _write(
            req,
            "coverage_map",
            {"coverage": [{"behavior_id": "hello", "status": "covered"}]},
        )
        return "designed"

    def design_review(req):
        _write(req, "design_review", "accepted\n")
        return {
            "verdict": "design_accepted",
            "summary": "sound",
            "authoritative_artifacts": ["workflow_design.md"],
            "coverage_count": 1,
            "uncovered_required_behaviors": [],
        }

    def build(req):
        _write(
            req,
            "generated_flow",
            "from botpipe import workflow\n\n@workflow(name='generated')\ndef generated():\n    return 'hello'\n",
        )
        _write(req, "generated_manifest", 'name = "generated"\n')
        _write(req, "generated_layout", {"files": ["flow.py", "workflow.toml"]})
        _write(req, "validation_report", "# Validation\n\nImported successfully.\n")
        return "built"

    def build_review(req):
        _write(req, "build_review", "accepted\n")
        return {
            "verdict": "build_validated",
            "summary": "valid",
            "changed_paths": ["flow.py"],
            "evidence_artifacts": ["validation_report.md"],
            "validation_commands": ["import"],
            "coverage_status": "complete",
        }

    provider = FakeProvider(
        [distill, distill_review, design, design_review, build, build_review]
    )
    result = Botpipe(tmp_path, provider=provider).run(
        code_to_workflow,
        "recreate app",
        generated_workflow_name="generated",
        task_id="code",
        run_id="run",
    )
    assert result.status == "completed"
    assert result.value.generated_workflow_name == "generated"
    assert Path(result.value.publication_receipt).is_file()


def test_code_to_workflow_trace_corpus_reads_current_journal_projection(tmp_path):
    from botpipe import Provider, workflow
    from botpipe.workflows.code_to_workflow.specs import collect_trace_corpus

    @workflow(name="trace_fixture")
    def traced():
        return Provider(session=None).generate("record evidence").value

    with Botpipe(tmp_path, provider=FakeProvider(["observed"])) as client:
        completed = client.run(
            traced, task_id="trace-task", run_id="trace-run"
        )
        assert completed.ok, completed.error

    corpus = collect_trace_corpus(tmp_path)
    projected = next(
        run for run in corpus["botpipe_runs"] if run["run_id"] == "trace-run"
    )
    assert projected["workflow_name"] == "trace_fixture"
    assert projected["status"] == "completed"
    assert any(step["event"] == "provider" for step in projected["step_outcomes"])


def test_code_to_workflow_trace_corpus_rejects_unknown_state_store(tmp_path):
    import sqlite3

    import pytest

    from botpipe.workflows.code_to_workflow.specs import collect_trace_corpus

    state = tmp_path / ".botpipe-v2" / "state.sqlite3"
    state.parent.mkdir()
    with sqlite3.connect(state) as connection:
        connection.execute("PRAGMA application_id=1")
        connection.execute("PRAGMA user_version=1")

    with pytest.raises(ValueError, match="Incompatible Botpipe state store"):
        collect_trace_corpus(tmp_path)
