"""Behavioral regression gates for the imperative packaged workflow ports."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from botpipe import Botpipe
from botpipe.providers import FakeProvider, ProviderResponse
from botpipe.workflows.code_to_workflow import code_to_workflow
from botpipe.workflows.devloop import devloop
from botpipe.workflows.goal import goal
from botpipe.workflows.ralph_loop import ralph_loop


def _write(request, name, value):
    path = request.artifacts[name]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))


def _input(request):
    return json.loads(request.prompt.split("\n\nInput:\n", 1)[1].split("\n\n", 1)[0])


def _reads(request):
    text = request.prompt.split("\n\nRead these immutable input artifacts:\n", 1)[1]
    return {
        item["name"]: Path(item["path"])
        for item in json.loads(text.split("\n\n", 1)[0])
    }


def _review(request, *, verdict="passed", repair_target="candidate"):
    data = _input(request)
    return {
        "review_id": data["review_id"],
        "criteria": [
            {
                "id": criterion["id"],
                "verdict": verdict,
                "evidence": ["checked current repository"],
                "reason": "concrete result",
            }
            for criterion in data["criteria"]
        ],
        "findings": [],
        "summary": "Reviewed",
        "repair_target": repair_target,
    }


@pytest.mark.parametrize("invalid_plan", [False, True])
def test_goal_budget_counts_provider_input_output_tokens_before_plan_review(
    tmp_path, invalid_plan
):
    def planning(request):
        data = _input(request)
        item = {
            "id": "build",
            "title": "Build",
            "description": "Build the feature",
            "status": "pending",
            "verifier_criteria": ["works"],
            "dependencies": [],
            "priority": 1,
        }
        _write(
            request,
            "subgoals",
            {
                "schema": "botpipe.goal.subgoals/v1",
                "goal_id": data["goal"]["goal_id"],
                "active_subgoal_id": None,
                "created_at": "",
                "updated_at": "",
                "subgoals": [item, item] if invalid_plan else [item],
            },
        )
        return ProviderResponse(
            "planned", "planner", {"input_tokens": 6, "output_tokens": 4}
        )

    provider = FakeProvider([planning])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(goal, "build feature", token_budget=5)
        assert result.ok, result.error
        assert result.value.status == "budget_limited"
        assert result.value.tokens_used == 10
        assert len(provider.calls) == 1
        persisted = json.loads(Path(result.value.goal_path).read_text())
        assert persisted["tokens_used"] == 10


def test_devloop_executes_later_phase_added_by_phase_item_repair(tmp_path):
    implemented = []
    state = {"first_implementation_review": True}

    def phase(phase_id, status="planned"):
        return {
            "phase_id": phase_id,
            "title": f"Deliver {phase_id}",
            "objective": f"Deliver {phase_id}",
            "status": status,
            "scope": {"in_scope": [phase_id], "out_of_scope": []},
            "dependencies": [],
            "criteria": [{"id": phase_id, "text": "works"}],
            "deliverables": [phase_id],
            "risks": [],
            "rollback": ["revert"],
        }

    def respond(request):
        data = _input(request)
        artifacts = request.artifacts
        if "phase_plan" in artifacts:
            if "active_phase_index" in data:
                document = data["plan"]
                document["status"] = "in_progress"
                document["phases"] = [phase("p1", "in_progress"), phase("p2")]
                _write(request, "phase_item_review", "Added required follow-on work.")
            else:
                document = {
                    "version": 1,
                    "task_id": data["task_id"],
                    "request_snapshot_ref": data["request_snapshot_ref"],
                    "status": "planned",
                    "phases": [phase("p1")],
                }
            _write(request, "phase_plan", document)
            return "planned"
        if "impl_notes" in artifacts:
            implemented.append(data["phase"]["phase_id"])
            _write(request, "impl_notes", "Implemented and checked.")
            return "implemented"
        if "audit_result" in artifacts:
            _write(
                request,
                "audit_result",
                {
                    "version": 1,
                    "task_id": data["task_id"],
                    "request_snapshot_ref": data["request_snapshot_ref"],
                    "status": "passed",
                    "summary": "All planned work completed",
                    "gaps": [],
                },
            )
            _write(request, "gap_report", "No gaps.")
            return "audited"
        key = next(iter(artifacts))
        if key == "impl_review" and state["first_implementation_review"]:
            state["first_implementation_review"] = False
            review = _review(request, verdict="failed", repair_target="phase_item")
        else:
            review = _review(request)
        _write(request, key, review)
        return review

    with Botpipe(tmp_path, provider=FakeProvider([respond] * 30)) as client:
        result = client.run(devloop, "deliver both required parts", mode="docloop")
        assert result.ok, result.error
        assert implemented == ["p1", "p1", "p2"]
        assert result.value.completed_phases == ["p1", "p2"]
        plan = json.loads(Path(result.value.phase_plan_path).read_text())
        assert [item["status"] for item in plan["phases"]] == ["completed", "completed"]


def test_code_to_workflow_preserves_verifier_basis_and_build_replan_feedback(tmp_path):
    (tmp_path / "source.py").write_text("print('hello')\n")
    state = {"designs": 0, "build_reviews": 0}
    feedback = "Repair the design: preserve a durable checkpoint before publication."

    def respond(request):
        artifacts = request.artifacts
        if "behavior_inventory" in artifacts:
            _write(
                request,
                "behavior_inventory",
                {"behaviors": [{"id": "hello", "required": True}]},
            )
            _write(request, "behavior_inventory_report", "Observable hello behavior")
            _write(request, "trace_pattern_notes", "No source traces")
            return "distilled"
        if "behavior_review" in artifacts:
            _write(request, "behavior_review", "Complete behavior inventory")
            return {
                "verdict": "behavior_distilled",
                "summary": "Complete",
                "behavior_count": 1,
                "evidence_artifacts": ["behavior_inventory.json"],
                "uncovered_areas": [],
            }
        if "workflow_design" in artifacts:
            state["designs"] += 1
            if state["designs"] == 2:
                assert _reads(request)["build_review"].read_text() == feedback
            _write(request, "workflow_design", "Durable workflow design")
            _write(request, "step_contracts", {"functions": ["generated"]})
            _write(request, "prompt_contract_matrix", "Prompt contracts")
            _write(request, "equivalence_plan", "Compare observable behavior")
            _write(
                request,
                "coverage_map",
                {"coverage": [{"behavior_id": "hello", "status": "covered"}]},
            )
            return "designed"
        if "design_review" in artifacts:
            assert {
                "source_manifest",
                "behavior_inventory",
                "behavior_inventory_report",
            } <= _reads(request).keys()
            _write(request, "design_review", "Design accepted")
            return {
                "verdict": "design_accepted",
                "summary": "Covered",
                "coverage_count": 1,
                "authoritative_artifacts": ["workflow_design.md"],
                "uncovered_required_behaviors": [],
            }
        if "generated_flow" in artifacts:
            _write(
                request,
                "generated_flow",
                "from botpipe import workflow\n@workflow(name='generated')\ndef generated():\n    return 'hello'\n",
            )
            _write(request, "generated_manifest", 'name = "generated"\n')
            _write(request, "generated_layout", {"files": ["flow.py", "workflow.toml"]})
            _write(request, "validation_report", "Imports and returns hello")
            return "built"
        assert "build_review" in artifacts
        assert {
            "source_manifest",
            "behavior_inventory",
            "workflow_design",
            "equivalence_plan",
            "coverage_map",
        } <= _reads(request).keys()
        state["build_reviews"] += 1
        verdict = "needs_replan" if state["build_reviews"] == 1 else "build_validated"
        _write(
            request,
            "build_review",
            feedback if verdict == "needs_replan" else "Accepted",
        )
        return {
            "verdict": verdict,
            "summary": "Reviewed",
            "changed_paths": ["flow.py"],
            "evidence_artifacts": ["validation_report.md"],
            "validation_commands": ["import"],
            "coverage_status": "needs_replan"
            if verdict == "needs_replan"
            else "complete",
            "replan_reason": feedback if verdict == "needs_replan" else None,
        }

    with Botpipe(tmp_path, provider=FakeProvider([respond] * 20)) as client:
        result = client.run(
            code_to_workflow, "recreate source", generated_workflow_name="generated"
        )
        assert result.ok, result.error
        assert state == {"designs": 2, "build_reviews": 2}
        assert Path(result.value.publication_receipt).is_file()


def test_ralph_item_rework_receives_feedback_and_retains_only_its_own_session(tmp_path):
    work = {
        "goal": "both items",
        "items": [
            {
                "id": label,
                "title": label,
                "status": "planned",
                "goal": label,
                "acceptance_checks": ["complete"],
            }
            for label in ("one", "two")
        ],
    }
    state = {"reviews": 0}
    implementation_sessions = []

    def respond(request):
        if "work" in request.artifacts:
            _write(request, "work", work)
            return ProviderResponse("planned", "planner")
        if "plan_review" in request.artifacts:
            _write(request, "plan_review", "Accepted")
            return ProviderResponse('{"verdict":"accepted"}', "plan-reviewer")
        item_id = _input(request)["id"]
        if "implementation_review" in request.artifacts:
            state["reviews"] += 1
            rejected = state["reviews"] == 1
            assert request.session_id == f"item-{item_id}"
            _write(
                request,
                "implementation_review",
                "Fix the missing acceptance check" if rejected else "Accepted",
            )
            return ProviderResponse(
                json.dumps({"verdict": "needs_rework" if rejected else "accepted"}),
                f"item-{item_id}",
            )
        implementation_sessions.append((item_id, request.session_id))
        if item_id == "one" and state["reviews"]:
            assert (
                "Fix the missing acceptance check"
                in _reads(request)["implementation_review"].read_text()
            )
        return ProviderResponse("implemented", f"item-{item_id}")

    provider = FakeProvider([respond] * 10)
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(ralph_loop, "deliver both items")
        assert result.ok, result.error
        assert implementation_sessions == [
            ("one", None),
            ("one", "item-one"),
            ("two", None),
        ]
        assert [item["status"] for item in result.value.read_json()["items"]] == [
            "completed",
            "completed",
        ]
        assert client.resume(result.run_id, workflow=ralph_loop).ok
        assert len(provider.calls) == 8


def test_ralph_interruption_resumes_without_repeating_completed_item(tmp_path):
    from botpipe.recovery import Stopped

    work = {
        "goal": "complete both durable items",
        "items": [
            {
                "id": item_id,
                "title": f"Deliver {item_id}",
                "status": "planned",
                "goal": f"Complete {item_id}",
                "acceptance_checks": [f"{item_id} is complete"],
            }
            for item_id in ("one", "two")
        ],
    }
    implementations = Counter()
    reviews = Counter()

    def plan(request):
        _write(request, "work", work)
        return ProviderResponse("planned", "planner")

    def plan_review(request):
        _write(request, "plan_review", "Accepted")
        return ProviderResponse('{"verdict":"accepted"}', "plan-reviewer")

    def implement(request):
        item_id = _input(request)["id"]
        implementations[item_id] += 1
        return ProviderResponse("implemented", f"item-{item_id}")

    def item_review(request):
        item_id = _input(request)["id"]
        reviews[item_id] += 1
        _write(request, "implementation_review", "Accepted")
        return ProviderResponse('{"verdict":"accepted"}', f"item-{item_id}")

    def interrupt_second_item(request):
        assert _input(request)["id"] == "two"
        implementations["two"] += 1
        raise SystemExit("lost process during second item")

    provider = FakeProvider(
        [
            plan,
            plan_review,
            implement,
            item_review,
            interrupt_second_item,
            implement,
            item_review,
        ]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit, match="second item"):
            client.run(
                ralph_loop,
                "deliver both items",
                task_id="ralph-interrupted",
                run_id="run",
            )

        interrupted = [
            row
            for row in client.inspect("run")["operations"]
            if row["kind"] == "provider" and row["status"] not in {"completed", "failed"}
        ]
        assert len(interrupted) == 1
        provider.recover = lambda request: Stopped(
            "the interrupted second-item process is confirmed stopped"
        )
        client.resolve("run", interrupted[0]["id"], retry=True)
        completed = client.resume("run", workflow=ralph_loop)

        assert completed.ok, completed.error
        assert [item["status"] for item in completed.value.read_json()["items"]] == [
            "completed",
            "completed",
        ]
        assert implementations == {"one": 1, "two": 2}
        assert reviews == {"one": 1, "two": 1}
        assert len(provider.calls) == 7

        replayed = client.resume("run", workflow=ralph_loop)
        assert replayed.value == completed.value
        assert len(provider.calls) == 7


def test_devloop_followup_preserves_parent_audit_and_plan_result_paths(tmp_path):
    def respond(request):
        data = _input(request)
        artifacts = request.artifacts
        if "phase_plan" in artifacts:
            _write(
                request,
                "phase_plan",
                {
                    "version": 1,
                    "task_id": data["task_id"],
                    "request_snapshot_ref": data["request_snapshot_ref"],
                    "status": "planned",
                    "phases": [
                        {
                            "phase_id": "p1",
                            "title": "Deliver objective",
                            "objective": data["request"],
                            "status": "planned",
                            "scope": {"in_scope": ["docs"], "out_of_scope": []},
                            "dependencies": [],
                            "criteria": [{"id": "P1", "text": "delivered"}],
                            "deliverables": ["README"],
                            "risks": [],
                            "rollback": ["revert"],
                        }
                    ],
                },
            )
            return "planned"
        if "impl_notes" in artifacts:
            _write(request, "impl_notes", "Implemented current objective")
            return "implemented"
        if "audit_result" in artifacts:
            parent = data["request"] == "parent objective"
            _write(
                request,
                "audit_result",
                {
                    "version": 1,
                    "task_id": data["task_id"],
                    "request_snapshot_ref": data["request_snapshot_ref"],
                    "status": "needs_followup" if parent else "passed",
                    "summary": data["request"],
                    "gaps": [
                        {
                            "id": "missing",
                            "severity": "medium",
                            "summary": "Missing outcome",
                            "evidence": ["review evidence"],
                            "followup": "repair missing outcome",
                        }
                    ]
                    if parent
                    else [],
                },
            )
            _write(request, "gap_report", "Missing outcome" if parent else "No gaps")
            if parent:
                _write(request, "revised_request", "repair missing outcome")
            return "audited"
        report = _review(request)
        _write(request, next(iter(artifacts)), report)
        return report

    with Botpipe(tmp_path, provider=FakeProvider([respond] * 20)) as client:
        result = client.run(devloop, "parent objective", mode="docloop")
        assert result.ok, result.error
        assert result.value.status == "needs_followup"
        parent_audit = json.loads(Path(result.value.audit_result_path).read_text())
        assert parent_audit["status"] == "needs_followup"
        assert parent_audit["summary"] == "parent objective"
        parent_plan = json.loads(Path(result.value.phase_plan_path).read_text())
        assert parent_plan["phases"][0]["objective"] == "parent objective"
        followup = json.loads(Path(result.value.followup_result_path).read_text())
        assert followup["child_status"] == "passed"
        child_audit = json.loads(Path(followup["child_audit_result"]).read_text())
        assert child_audit["status"] == "passed"
