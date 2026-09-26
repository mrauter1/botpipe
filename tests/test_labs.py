from __future__ import annotations

import json
import re
import sys
from typing import get_type_hints

import pytest

from botpipe import Botpipe
from botpipe.discovery import discover_workflows, resolve_workflow
from botpipe.providers import FakeProvider
from labs.workflows.release_candidate_to_go_no_go import (
    Params,
    ReleaseCandidateToGoNoGo,
)


def _successful_provider(request):
    phase_input = json.JSONDecoder().raw_decode(
        request.prompt.split("\n\nInput:\n", 1)[1]
    )[0]
    fixture_artifacts, fixture_details = _publication_fixture(phase_input)
    if (
        request.workspace.name == "candidate"
        and (request.workspace.parent / ".botpipe-candidate.json").is_file()
        and any(name.startswith("candidate_") for name in request.artifacts)
    ):
        candidate_sources = list(request.workspace.rglob("workflow.py"))
        if candidate_sources:
            with candidate_sources[0].open("a", encoding="utf-8") as stream:
                stream.write("\n# staged candidate change\n")
    for name, path in request.artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if name == "workflow_package_manifest":
            package_name = phase_input["parameters"]["package_name"]
            source_path = f".botpipe/workflows/{package_name}/flow.py"
            function_name = "GeneratedWorkflow"
            content = (
                "from botpipe import workflow\n\n"
                f'@workflow(name="{package_name}")\n'
                f'def {function_name}(request: str = "") -> str:\n'
                '    return request or "ok"\n'
            )
            files = [
                {
                    "path": source_path,
                    "role": "workflow",
                    "purpose": "Generated durable workflow callable.",
                    "required": True,
                    "implements": "accepted workflow design",
                    "content": content,
                }
            ]
            files.append(
                {
                    "path": f".botpipe/workflows/{package_name}/workflow.toml",
                    "role": "manifest",
                    "content": (
                        f'name = "{package_name}"\nfunction = "{function_name}"\n'
                    ),
                }
            )
            path.write_text(
                json.dumps(
                    {
                        "package_name": package_name,
                        "workflow_reference": f"{source_path}:{function_name}",
                        "files": files,
                    }
                )
            )
        elif name in fixture_artifacts:
            path.write_text(json.dumps(fixture_artifacts[name]))
        elif name == "eval_case_manifest":
            value = {
                "cases": [
                    {
                        "case_id": "base",
                        "case_kind": "benchmark",
                        "prompt": "baseline",
                        "workflow_parameters": {"release_name": "2026.10"},
                        "expected_artifacts": ["release_decision_package"],
                    },
                    {
                        "case_id": "edge",
                        "case_kind": "edge",
                        "prompt": "boundary",
                        "workflow_parameters": {"release_name": "2026.10"},
                        "expected_artifacts": ["release_decision_package"],
                    },
                    {
                        "case_id": "attack",
                        "case_kind": "adversarial",
                        "prompt": "adversarial",
                        "workflow_parameters": {"release_name": "2026.10"},
                        "expected_artifacts": ["release_decision_package"],
                    },
                ]
            }
            path.write_text(json.dumps(value))
        elif name == "proposed_workflow_parameters":
            path.write_text(json.dumps({"release_name": "2026.10"}))
        else:
            path.write_text(
                "{}\n" if path.suffix == ".json" else "# Evidence\n\nVerified.\n"
            )
    schema = request.output_schema or {}
    accepted = _accepted_schema(schema)
    properties = accepted.get("properties", {})
    if "outcome" in properties:
        result = _schema_value(accepted, schema)
        required_artifacts = []
        matches = re.findall(r'"required_artifacts"\s*:\s*(\[[^\]]*\])', request.prompt)
        if matches:
            required_artifacts = json.loads(matches[-1])
        result.update(
            {key: value for key, value in fixture_details.items() if key in properties}
        )
        result.update(
            {
                "outcome": "accepted",
                "summary": "The artifacts satisfy the declared phase contract.",
                "authoritative_artifacts": required_artifacts,
            }
        )
        return result
    return {
        "summary": "Produced the required evidence.",
        "evidence_notes": [],
        "candidate_ids": [],
    }


def _publication_fixture(phase_input):
    """Coherent staged domain evidence, independent of the publication validators."""
    parameters = phase_input.get("parameters", {})
    phase = phase_input["phase"]
    workflow_names = parameters.get("focus_workflows") or [
        "release_candidate_to_go_no_go"
    ]
    task_ids = parameters.get("focus_tasks") or ["staged"]
    focus = workflow_names[0]
    lifecycle = [
        {"workflow_name": name, "lifecycle_posture": "keep", "priority": "P2"}
        for name in workflow_names
    ]
    portfolio_summary = {
        "focus_workflows": workflow_names,
        "analyzed_workflows": workflow_names,
        "lifecycle_recommendations": lifecycle,
        "governance_posture_counts": {"keep": len(workflow_names)},
        "change_candidate_ids": ["keep-release"],
        "priority_workflows": workflow_names,
        "authoritative_artifacts": [
            "workflow_portfolio_operating_system",
            "portfolio_operating_summary",
            "portfolio_next_actions",
            "portfolio_health_analysis",
            "lifecycle_recommendations",
            "portfolio_change_candidates",
        ],
        "next_action": "Review the scoped portfolio recommendation.",
        "publication_boundary": "operating_system_publication_only",
        "ready_for_publication": True,
    }
    company_summary = {
        "workflow_name": "company_operation_to_recursive_improvement_cycle",
        "focus_task_ids": task_ids,
        "focus_workflows": workflow_names,
        "candidate_ids": ["improve-release"],
        "priority_item_ids": ["improve-release"],
        "priority_categories": ["workflow_package"],
        "priority_category_counts": {"workflow_package": 1},
        "authoritative_artifacts": [
            "recursive_improvement_cycle",
            "recursive_improvement_summary",
            "recursive_improvement_next_actions",
            "company_pressure_map",
            "recursive_improvement_priority_matrix",
            "recursive_improvement_candidates",
        ],
        "next_action": "Review the improvement proposal before scheduling follow-up.",
        "publication_boundary": "recursive_improvement_publication_only",
        "ready_for_publication": True,
    }
    investigation_summary = {
        "investigation_kind": parameters.get(
            "investigation_kind", "security_remediation"
        ),
        "authoritative_artifacts": [
            "investigation_scope_brief",
            "evidence_pack",
            "source_register",
            "evidence_gaps",
            "investigation_summary",
        ],
        "ready_for_downstream_assessment": True,
        "source_count": 1,
        "finding_count": 1,
        "unresolved_gap_count": 0,
        "key_findings": ["The supplied evidence supports the scoped assessment."],
    }
    artifacts = {
        "decision_summary": {
            "recommended_decision": "go",
            "blocking_issue_count": 0,
            "executed_checks": ["pytest"],
            "unexecuted_checks": [],
        },
        "incident_summary": {
            "recommended_posture": "planned",
            "primary_hypothesis": "A missing guard caused the outage.",
            "hardening_backlog_items": 1,
        },
        "investigation_summary": investigation_summary,
        "security_remediation_summary": {
            "selected_remediation": "Add the missing authorization guard.",
            "verification_ready": True,
            "rollout_ready": True,
            "authoritative_artifacts": [
                "remediation_plan",
                "verification_evidence",
                "security_remediation_package",
            ],
        },
        "portfolio_operating_summary": portfolio_summary,
        "lifecycle_recommendations": {"lifecycle_recommendations": lifecycle},
        "portfolio_change_candidates": {
            "change_candidates": [
                {
                    "candidate_id": "keep-release",
                    "action": "keep",
                    "priority": "P2",
                    "workflow_names": [focus],
                    "why_now": "The review found stable operation.",
                    "evidence_sources": ["portfolio_health_analysis"],
                    "next_step_hint": "Keep the workflow and review new execution evidence.",
                }
            ]
        },
        "recursive_improvement_summary": company_summary,
        "recursive_improvement_candidates": {
            "improvement_candidates": [
                {
                    "candidate_id": "improve-release",
                    "category": "workflow_package",
                    "priority": "P2",
                    "title": "Clarify release evidence checks.",
                    "why_now": "The scoped review identified an improvement.",
                    "evidence_sources": ["company_pressure_map"],
                    "next_step_hint": "Review the proposed checks.",
                    "workflow_names": [focus],
                    "task_ids": task_ids,
                }
            ]
        },
    }
    details = {
        "recommended_decision": "go",
        "decision": "go",
        "blocking_issue_count": 0,
        "executed_checks": ["pytest"],
        "unexecuted_checks": [],
        "communication_ready": True,
        "verification_ready": True,
        "rollout_ready": True,
        "closure_ready": True,
        "selected_remediation": "Add the missing authorization guard.",
        "recommended_posture": "planned",
        "primary_hypothesis": "A missing guard caused the outage.",
        "owner_ready": True,
    }
    if "investigation_kind" in parameters:
        details.update(investigation_summary)
    if phase in {
        "frame_portfolio_governance",
        "analyze_portfolio_operating_model",
        "package_portfolio_operating_system",
    }:
        details.update(portfolio_summary)
    if phase in {
        "frame_company_operation",
        "analyze_recursive_improvement_pressures",
        "package_recursive_improvement_cycle",
    }:
        details.update(company_summary)
        details["priority_recommendations"] = [
            {
                "candidate_id": "improve-release",
                "category": "workflow_package",
                "priority": "P2",
            }
        ]
    if phase == "frame_candidate_request":
        details["decision_axes"] = ["fit"]
    if phase == "analyze_candidate_workflows":
        details.update(
            compared_workflows=[
                "release_candidate_to_go_no_go",
                "workflow_idea_to_workflow_package",
            ],
            ranked_candidates=["release_candidate_to_go_no_go"],
            portfolio_posture="direct_fit",
            builder_considered=True,
        )
    if phase == "package_candidate_workflow_set":
        details.update(
            comparison_candidates=[
                "release_candidate_to_go_no_go",
                "workflow_idea_to_workflow_package",
            ],
            ranked_candidates=["release_candidate_to_go_no_go"],
            recommended_candidate_workflows=["release_candidate_to_go_no_go"],
            builder_baseline_workflow="workflow_idea_to_workflow_package",
            builder_considered=True,
            portfolio_posture="direct_fit",
        )
    if phase in {"select_strategy", "package_strategy"}:
        details.update(
            selected_strategy="run_existing",
            recommended_workflows=["release_candidate_to_go_no_go"],
        )
    if phase in {
        "frame_adaptation_request",
        "analyze_adaptation_surface",
        "package_adapted_execution_plan",
    }:
        details.update(
            selected_workflow_name="release_candidate_to_go_no_go",
            expected_downstream_artifacts=["release_decision_package"],
        )
    if phase in {
        "frame_evaluation_target",
        "design_eval_cases",
        "package_workflow_eval_suite",
    }:
        details["selected_workflow_name"] = "release_candidate_to_go_no_go"
    if phase == "design_eval_cases":
        details.update(
            case_ids=["base", "edge", "attack"],
            case_kinds=["benchmark", "edge", "adversarial"],
            covered_expected_artifacts=["release_decision_package"],
        )
    if phase == "package_workflow_eval_suite":
        manifest = phase_input["validated_eval_case_manifest"]
        details.update(
            case_count=manifest["case_count"],
            case_ids=manifest["case_ids"],
            case_kinds=manifest["case_kinds"],
            covered_expected_artifacts=["release_decision_package"],
        )
        details["evaluation_suite_id"] = phase_input["evaluation_suite_id"]
        handoff = phase_input.get("optimizer_handoff")
        details["source_candidate_id"] = (
            handoff["candidate_id"] if handoff is not None else None
        )
    return artifacts, details


def _accepted_schema(schema):
    """Choose the accepted branch of a typed producer or review union."""
    for branch in schema.get("oneOf", []) + schema.get("anyOf", []):
        resolved = branch
        if "$ref" in branch:
            resolved = schema
            for part in branch["$ref"].removeprefix("#/").split("/"):
                resolved = resolved[part]
        outcome = resolved.get("properties", {}).get("outcome", {})
        if outcome.get("const") == "accepted" or "accepted" in outcome.get("enum", []):
            return resolved
    return schema


def _schema_value(schema, root):
    if "$ref" in schema:
        current = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            current = current[part]
        return _schema_value(current, root)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "default" in schema:
        return schema["default"]
    choices = schema.get("anyOf") or schema.get("oneOf")
    if choices:
        selected = next(
            (choice for choice in choices if choice.get("type") != "null"), choices[0]
        )
        return _schema_value(selected, root)
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        return {
            name: _schema_value(properties[name], root)
            for name in schema.get("required", [])
        }
    if kind == "array":
        count = schema.get("minItems", 0)
        return [_schema_value(schema.get("items", {}), root) for _ in range(count)]
    if kind == "boolean":
        return True
    if kind == "integer":
        return schema.get("minimum", 1)
    if kind == "number":
        return schema.get("minimum", 1.0)
    if kind == "null":
        return None
    return "value"


LAB_SCENARIOS = {
    "candidate_workflow_to_adapted_execution_plan": {
        "selected_workflow": "release_candidate_to_go_no_go",
        "task_title": "Adapt release review",
    },
    "company_operation_to_recursive_improvement_cycle": {
        "task_title": "Improve operations"
    },
    "improve_workflow": {
        "selected_workflow": "release_candidate_to_go_no_go",
        "target_test_argv": [sys.executable, "-c", "pass"],
    },
    "incident_to_hardening_program": {"incident_title": "Checkout outage"},
    "investigation_request_to_evidence_pack": {
        "investigation_title": "Readiness evidence",
        "investigation_kind": "release_readiness",
    },
    "release_candidate_to_go_no_go": {"release_name": "2026.10"},
    "security_finding_to_verified_remediation": {
        "finding_title": "Authorization bypass",
        "finding_source": "internal_review",
    },
    "task_to_candidate_workflow_set": {"task_title": "Recover a delivery"},
    "task_to_workflow_strategy": {"task_title": "Choose a delivery workflow"},
    "workflow_idea_to_workflow_package": {
        "package_name": "customer_escalation",
        "workflow_kind": "end_to_end",
    },
    "workflow_portfolio_to_operating_system": {
        "task_title": "Govern workflow portfolio"
    },
    "workflow_to_eval_suite": {
        "selected_workflow": "release_candidate_to_go_no_go",
        "task_title": "Evaluate release review",
    },
}


def test_labs_discovery_matches_behavioral_scenarios():
    entries = [
        entry
        for entry in discover_workflows(".", include_labs=True)
        if entry.source_kind == "labs"
    ]
    names = [entry.name for entry in entries]
    assert len(names) == len(set(names))
    assert set(names) == set(LAB_SCENARIOS)


@pytest.mark.parametrize(
    "case_kinds",
    [["benchmark"], ["adversarial"], ["benchmark", "edge"]],
)
def test_eval_suite_packages_relevant_case_kinds_and_replays(tmp_path, case_kinds):
    from labs.workflows.workflow_to_eval_suite import Params, workflow_callable

    def produce(request):
        result = _successful_provider(request)
        manifest_path = request.artifacts.get("eval_case_manifest")
        if manifest_path is not None:
            manifest = json.loads(manifest_path.read_text())
            manifest["cases"] = [
                case for case in manifest["cases"] if case["case_kind"] in case_kinds
            ]
            manifest_path.write_text(json.dumps(manifest))
            result["case_ids"] = [case["case_id"] for case in manifest["cases"]]
            result["case_kinds"] = case_kinds
        return result

    provider = FakeProvider([produce] * 3)
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(
            workflow_callable,
            Params(
                selected_workflow="release_candidate_to_go_no_go",
                task_title="Evaluate only meaningful case categories",
            ),
        )
        assert result.ok, result.error
        cases = result.value.artifacts["eval_case_manifest"].read_json()["cases"]
        assert [case["case_kind"] for case in cases] == case_kinds
        package = result.value.phases[-1]
        assert package.name == "package_workflow_eval_suite"
        assert package.details["case_kinds"] == case_kinds
        assert package.details["case_count"] == len(cases)
        assert package.details["case_ids"] == [case["case_id"] for case in cases]

        call_count = len(provider.calls)
        replayed = client.resume(result.run_id, workflow=workflow_callable)
        assert replayed.ok, replayed.error
        assert replayed.value == result.value
        assert len(provider.calls) == call_count


def test_release_workflow_runs_staged_typed_outcomes_and_captures_artifacts(tmp_path):
    provider = FakeProvider([_successful_provider] * 8)
    result = Botpipe(tmp_path, provider=provider).run(
        ReleaseCandidateToGoNoGo,
        Params(release_name="2026.09", evidence_paths=["test-results.json"]),
        request="Decide whether this release may proceed.",
        task_id="release",
        run_id="staged",
    )

    assert result.ok
    assert result.value.workflow_name == "release_candidate_to_go_no_go"
    assert [phase.name for phase in result.value.phases] == [
        "frame_release",
        "assemble_evidence_pack",
        "assess_go_no_go",
        "prepare_decision_package",
    ]
    assert len(result.value.artifact_names) == 13
    assert set(result.value.artifacts) == set(result.value.artifact_names)
    assert all(handle.read_bytes() for handle in result.value.artifacts.values())
    assert result.value.artifact_paths == {
        name: str(handle.path) for name, handle in result.value.artifacts.items()
    }
    assert all(phase.outcome == "accepted" for phase in result.value.phases)
    assert [call.preset for call in provider.calls] == [
        "run",
        "run",
        "query",
        "run",
        "query",
        "run",
    ]
    assert all(not call.artifacts for call in provider.calls if call.preset == "query")
    assert result.value.phases[0].review_operation_id is None
    assert all(phase.review_operation_id for phase in result.value.phases[1:3])
    assert result.value.phases[-1].review_operation_id is None
    inspection = Botpipe(tmp_path, provider=FakeProvider([])).inspect("staged")
    provider_operations = [
        item for item in inspection["operations"] if item["kind"] == "provider"
    ]
    assert len(provider_operations) == len(provider.calls)
    assert all(item["status"] == "completed" for item in provider_operations)


@pytest.mark.parametrize("workflow_name", sorted(LAB_SCENARIOS))
def test_lab_workflow_completes_with_captured_outputs(tmp_path, workflow_name):
    function = resolve_workflow(workflow_name, ".")
    params_type = get_type_hints(function)["params"]
    params = params_type(**LAB_SCENARIOS[workflow_name])
    workspace = tmp_path / workflow_name
    workspace.mkdir()
    (workspace / "README.md").write_text("# Test workspace\n", encoding="utf-8")
    if workflow_name == "improve_workflow":
        from tests.improvement_support import (
            ACCEPT,
            FixtureProvider,
            assess,
            no_candidate,
        )

        provider = FixtureProvider([assess, no_candidate, ACCEPT])
    else:
        provider = FakeProvider([_successful_provider] * 64)
    result = Botpipe(workspace, provider=provider).run(
        function,
        params,
        request=f"Staged smoke for {workflow_name}",
        task_id="staged",
        run_id="run",
    )
    assert result.ok, f"{workflow_name}: {result.error}"
    if workflow_name == "improve_workflow":
        assert result.value.selected_workflow == "release_candidate_to_go_no_go"
        assert result.value.outcome == "collect_evidence"
        assert (
            result.value.recommendation.candidate_set.next_action == "collect_evidence"
        )
        assert result.value.candidate is None
        assert result.value.provider_budget["used_turns"] == len(provider.calls)
        assert provider.calls, "No history must not bypass model-led investigation."
    else:
        assert result.value.workflow_name == workflow_name
        assert result.value.phases
        assert all(phase.outcome == "accepted" for phase in result.value.phases)
        assert set(result.value.artifact_names) == set(result.value.artifacts)
        assert all(handle.path.is_file() for handle in result.value.artifacts.values())
