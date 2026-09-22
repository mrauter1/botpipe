"""PRD A37 branch matrix for every ordinary labs workflow."""

from __future__ import annotations

import json
import sys
from collections import Counter

import pytest

from botpipe import Botpipe
from botpipe.discovery import resolve_workflow
from botpipe.providers import FakeProvider
from test_labs import _successful_provider


LAB_CASES = {
    "candidate_workflow_to_adapted_execution_plan": {
        "selected_workflow": "release_candidate_to_go_no_go",
        "task_title": "Adapt release review",
    },
    "company_operation_to_recursive_improvement_cycle": {
        "task_title": "Improve operations",
        "focus_tasks": ["staged"],
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
    "workflow_and_eval_to_refined_workflow_package": {
        "selected_workflow": "release_candidate_to_go_no_go",
        "task_title": "Refine release review",
        "evaluation_summary_path": "evaluation-summary.json",
        "evaluation_findings_path": "evaluation-findings.json",
        "target_test_argv": [sys.executable, "-c", "pass"],
    },
    "workflow_idea_to_workflow_package": {
        "package_name": "customer_escalation",
        "workflow_kind": "end_to_end",
    },
    "workflow_package_to_composable_building_blocks": {
        "selected_workflow": "release_candidate_to_go_no_go",
        "task_title": "Decompose release review",
        "target_test_argv": [sys.executable, "-c", "pass"],
    },
    "workflow_portfolio_to_operating_system": {
        "task_title": "Govern workflow portfolio"
    },
    "workflow_run_history_to_failure_modes": {
        "selected_workflow": "release_candidate_to_go_no_go",
        "task_title": "Diagnose release review",
    },
    "workflow_to_eval_suite": {
        "selected_workflow": "release_candidate_to_go_no_go",
        "task_title": "Evaluate release review",
    },
}

# Use a non-framing phase so the test proves each workflow's surrounding
# checkpoint-reset code, rather than only run_phase's local branch.
REPLAN_PHASES = {
    "candidate_workflow_to_adapted_execution_plan": "analyze_adaptation_surface",
    "company_operation_to_recursive_improvement_cycle": "analyze_recursive_improvement_pressures",
    "incident_to_hardening_program": "assemble_evidence_pack",
    "investigation_request_to_evidence_pack": "assemble_evidence_pack",
    "release_candidate_to_go_no_go": "assemble_evidence_pack",
    "security_finding_to_verified_remediation": "assess_security_finding",
    "task_to_candidate_workflow_set": "analyze_candidate_workflows",
    "task_to_workflow_strategy": "select_strategy",
    "workflow_and_eval_to_refined_workflow_package": "design_refinement_plan",
    "workflow_idea_to_workflow_package": "design_package",
    "workflow_package_to_composable_building_blocks": "design_decomposition_plan",
    "workflow_portfolio_to_operating_system": "analyze_portfolio_operating_model",
    "workflow_run_history_to_failure_modes": "map_failure_modes",
    "workflow_to_eval_suite": "design_eval_cases",
}

REPLAN_RESTART_PHASES = {
    "candidate_workflow_to_adapted_execution_plan": "frame_adaptation_request",
    "company_operation_to_recursive_improvement_cycle": "frame_company_operation",
    "incident_to_hardening_program": "frame_incident",
    "investigation_request_to_evidence_pack": "frame_investigation",
    "release_candidate_to_go_no_go": "frame_release",
    "security_finding_to_verified_remediation": "frame_investigation",
    "task_to_candidate_workflow_set": "frame_candidate_request",
    "task_to_workflow_strategy": "frame_task",
    "workflow_and_eval_to_refined_workflow_package": "frame_refinement_request",
    "workflow_idea_to_workflow_package": "frame_candidate",
    "workflow_package_to_composable_building_blocks": "frame_decomposition_request",
    "workflow_portfolio_to_operating_system": "frame_portfolio_governance",
    "workflow_run_history_to_failure_modes": "frame_diagnostic_scope",
    "workflow_to_eval_suite": "frame_evaluation_target",
}


def _input(request):
    return json.JSONDecoder().raw_decode(
        request.prompt.split("\n\nInput:\n", 1)[1]
    )[0]


def _case(tmp_path, name):
    workspace = tmp_path / name
    workspace.mkdir()
    (workspace / "README.md").write_text("# Test workspace\n", encoding="utf-8")
    if name == "workflow_and_eval_to_refined_workflow_package":
        (workspace / "evaluation-summary.json").write_text(
            json.dumps({"selected_workflow_name": "release_candidate_to_go_no_go"}),
            encoding="utf-8",
        )
        (workspace / "evaluation-findings.json").write_text(
            "# Findings\n\nNo blocking regression.\n", encoding="utf-8"
        )
    definition = resolve_workflow(name, ".")
    module = __import__(definition.__module__, fromlist=["Params"])
    return workspace, definition, module.Params(**LAB_CASES[name])


class ControlledProvider:
    def __init__(self, outcome, *, phase=None):
        self.outcome = outcome
        self.phase = phase
        self.triggered = False
        self.producers = Counter()
        self.verifiers = Counter()
        self.producer_inputs = []

    def __call__(self, request):
        payload = _input(request)
        phase = payload["phase"]
        if request.artifacts:
            self.producers[phase] += 1
            self.producer_inputs.append(payload)
        else:
            self.verifiers[phase] += 1
        response = _successful_provider(request)
        if (
            not request.artifacts
            and not self.triggered
            and (self.phase is None or phase == self.phase)
        ):
            self.triggered = True
            response["outcome"] = self.outcome
            response["summary"] = f"Controlled {self.outcome} for {phase}."
            if self.outcome == "needs_replan":
                response["replan_reason"] = "The earlier checkpoint must change."
            if self.outcome in {"question", "blocked"}:
                response["question"] = "Supply the missing acceptance evidence."
        return response


@pytest.mark.parametrize("name", sorted(LAB_CASES))
def test_each_ordinary_lab_reworks_only_the_rejected_phase(tmp_path, name):
    workspace, definition, params = _case(tmp_path, name)
    controlled = ControlledProvider("needs_rework")
    provider = FakeProvider([controlled] * 96)
    with Botpipe(workspace, provider=provider) as client:
        result = client.run(definition, params, request="Exercise local rework")

    assert result.ok, f"{name}: {result.error}"
    assert controlled.triggered
    [reworked] = [phase for phase, count in controlled.producers.items() if count == 2]
    assert controlled.verifiers[reworked] == 2
    second = [item for item in controlled.producer_inputs if item["phase"] == reworked][1]
    assert second["rework_feedback"]["outcome"] == "needs_rework"


@pytest.mark.parametrize("name", sorted(LAB_CASES))
def test_each_ordinary_lab_replans_from_its_declared_checkpoint(tmp_path, name):
    workspace, definition, params = _case(tmp_path, name)
    phase = REPLAN_PHASES[name]
    controlled = ControlledProvider("needs_replan", phase=phase)
    provider = FakeProvider([controlled] * 128)
    with Botpipe(workspace, provider=provider) as client:
        result = client.run(definition, params, request="Exercise backward replan")

    assert result.ok, f"{name}: {result.error}"
    assert controlled.triggered
    assert controlled.producers[phase] == 2
    assert controlled.verifiers[phase] == 2
    restart_phase = REPLAN_RESTART_PHASES[name]
    assert controlled.producers[restart_phase] == 2
    assert controlled.verifiers[restart_phase] == 2
    assert [item.name for item in result.value.phases].count(phase) == 1
    replanned = [
        item for item in controlled.producer_inputs
        if item["phase"] == phase and "replan_feedback" in item
    ]
    assert replanned
    assert replanned[-1]["replan_feedback"]["details"]["outcome"] == "needs_replan"


@pytest.mark.parametrize("outcome", ["question", "blocked"])
@pytest.mark.parametrize("name", sorted(LAB_CASES))
def test_each_ordinary_lab_suspends_and_resumes_the_same_phase(
    tmp_path, name, outcome
):
    workspace, definition, params = _case(tmp_path, name)
    controlled = ControlledProvider(outcome)
    provider = FakeProvider([controlled] * 96)
    with Botpipe(workspace, provider=provider) as client:
        paused = client.run(definition, params, request=f"Exercise {outcome}")
        assert paused.status == "awaiting_input", f"{name}: {paused.error}"
        [pending] = client.pending(paused.run_id)
        assert "Supply the missing acceptance evidence" in pending["question"]
        result = client.answer(
            paused.run_id,
            pending["operation_id"],
            "The evidence is attached to the durable run.",
        )

    assert result.ok, f"{name}: {result.error}"
    assert controlled.triggered
    [resumed_phase] = [
        phase for phase, count in controlled.producers.items() if count == 2
    ]
    second = [
        item for item in controlled.producer_inputs
        if item["phase"] == resumed_phase
    ][1]
    assert second["rework_feedback"]["outcome"] == outcome
    assert second["rework_feedback"]["input_answer"].startswith("The evidence")


@pytest.mark.parametrize("name", sorted(LAB_CASES))
def test_each_ordinary_lab_terminal_failure_stops_later_turns(tmp_path, name):
    workspace, definition, params = _case(tmp_path, name)
    controlled = ControlledProvider("failed")
    provider = FakeProvider([controlled] * 8)
    with Botpipe(workspace, provider=provider) as client:
        result = client.run(definition, params, request="Exercise terminal failure")

    assert result.status == "failed"
    assert "verification returned failed" in result.error
    assert controlled.triggered
    assert len(provider.calls) == 2
    assert sum(bool(request.artifacts) for request in provider.calls) == 1


@pytest.mark.parametrize(
    ("name", "artifact_name"),
    [
        ("company_operation_to_recursive_improvement_cycle", "recursive_improvement_summary"),
        ("incident_to_hardening_program", "incident_summary"),
        ("investigation_request_to_evidence_pack", "investigation_summary"),
        ("release_candidate_to_go_no_go", "decision_summary"),
        ("security_finding_to_verified_remediation", "security_remediation_summary"),
        ("workflow_portfolio_to_operating_system", "portfolio_operating_summary"),
    ],
)
def test_domain_publication_gate_rejects_invalid_captured_summary(
    tmp_path, name, artifact_name
):
    workspace, definition, params = _case(tmp_path, name)

    def corrupt_summary(request):
        response = _successful_provider(request)
        if artifact_name in request.artifacts:
            request.artifacts[artifact_name].write_text("{}", encoding="utf-8")
        return response

    provider = FakeProvider([corrupt_summary] * 96)
    with Botpipe(workspace, provider=provider) as client:
        result = client.run(
            definition, params, request="Reject inconsistent publication evidence"
        )

    assert result.status == "failed"
    assert result.value is None
    assert result.error
