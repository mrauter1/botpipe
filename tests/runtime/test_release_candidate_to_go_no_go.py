from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.providers.fake import ScriptedLLMProvider
from autoloop_v3.runtime.loader import (
    WorkflowParameterError,
    coerce_workflow_parameter_mapping,
    discover_workflow_packages,
    resolve_workflow_reference,
)
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow_package
from workflow.primitives import Outcome


REPO_ROOT = Path(__file__).resolve().parents[2]


def _clear_workflow_modules() -> None:
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def test_repo_workflows_namespace_discovers_release_go_no_go_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "release_candidate_to_go_no_go" in discovered
    package = discovered["release_candidate_to_go_no_go"]
    assert package.package_name == "release_candidate_to_go_no_go"
    assert "release-go-no-go" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "workflows" / "release_candidate_to_go_no_go" / "workflow.toml"
    )


def test_release_go_no_go_package_compiles_with_explicit_control_contracts(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.release_candidate_to_go_no_go")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.ReleaseCandidateToGoNoGo)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "frame_release",
        "assemble_evidence_pack",
        "assess_go_no_go",
        "prepare_decision_package",
        "publish_decision",
    )

    frame_step = compiled.steps["frame_release"]
    assert frame_step.available_routes == (
        "release_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert frame_step.route_contracts["release_framed"]["required_artifacts"] == [
        "release_scope_brief",
        "decision_criteria",
        "evidence_intake_register",
    ]
    assert frame_step.route_contracts["release_framed"]["work_item_effect"] == (
        "Locks the release framing so evidence assembly can proceed against a fixed gate."
    )
    assert frame_step.expected_output_schema is not None

    assessment_step = compiled.steps["assess_go_no_go"]
    assert assessment_step.route_contracts["assessment_ready"]["required_artifacts"] == [
        "go_no_go_assessment",
        "risk_register",
        "decision_summary",
    ]
    assert assessment_step.expected_output_schema is not None

    package_step = compiled.steps["prepare_decision_package"]
    assert package_step.route_contracts["decision_package_ready"]["required_artifacts"] == [
        "release_decision_package",
        "release_communications_draft",
    ]


def test_release_go_no_go_package_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "release_candidate_to_go_no_go.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_release_candidate_to_go_no_go.py",
    ):
        assert required in text


def test_release_go_no_go_package_rejects_blank_release_name(tmp_path: Path) -> None:
    _install_repo_release_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "release_candidate_to_go_no_go").parameters_cls

    with pytest.raises(WorkflowParameterError, match="release_name"):
        coerce_workflow_parameter_mapping(parameters_cls, {"release_name": "   "})


def test_release_go_no_go_package_runs_and_emits_terminal_receipt(tmp_path: Path) -> None:
    _install_repo_release_package(tmp_path)

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.release_scope_brief.write_text(
                    "\n".join(
                        (
                            "# Release Scope Brief",
                            "",
                            "Release: `2026.04`.",
                            "Target date: `2026-04-24`.",
                            "Environment: `production`.",
                            "Scope: billing, SSO, and audit-log fixes queued for the Friday deployment.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.decision_criteria.write_text(
                    "\n".join(
                        (
                            "# Decision Criteria",
                            "",
                            "- No unresolved Sev-1 blockers.",
                            "- Test evidence must cover the touched surfaces or gaps must be explicit.",
                            "- Rollback procedure must exist and be ready.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.evidence_intake_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Intake Register",
                            "",
                            "- docs/releases/2026.04.md",
                            "- reports/test-summary-2026.04.md",
                            "- runbooks/prod-release-checklist.md",
                            "",
                        )
                    )
                    + "\n"
                ),
                "framed release\n",
            )[3],
            lambda request: (
                request.artifacts.release_inventory.write_text(
                    "\n".join(
                        (
                            "# Release Inventory",
                            "",
                            "- Reviewed release notes and task summary for 2026.04.",
                            "- Candidate includes billing fixes, SSO updates, and audit-log stabilization.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.test_evidence_pack.write_text(
                    "\n".join(
                        (
                            "# Test Evidence Pack",
                            "",
                            "- Regression suite passed for billing and auth surfaces.",
                            "- Load testing evidence is missing for the audit-log path.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.operational_readiness.write_text(
                    "\n".join(
                        (
                            "# Operational Readiness",
                            "",
                            "- Deployment checklist is complete.",
                            "- On-call coverage is assigned.",
                            "- Dashboard link is still pending.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.rollback_readiness.write_text(
                    "\n".join(
                        (
                            "# Rollback Readiness",
                            "",
                            "- Rollback script exists and was reviewed.",
                            "- Database rollback is not required for this release.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.blocking_issues.write_text(
                    "\n".join(
                        (
                            "# Blocking Issues",
                            "",
                            "- Conditional blocker: audit-log dashboard validation is still pending.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "assembled evidence\n",
            )[5],
            lambda request: (
                request.artifacts.go_no_go_assessment.write_text(
                    "\n".join(
                        (
                            "# Go / No-Go Assessment",
                            "",
                            "Recommendation: `conditional_go`.",
                            "Rationale: release evidence is strong, but launch should stay conditional on dashboard validation.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.risk_register.write_text(
                    "\n".join(
                        (
                            "# Risk Register",
                            "",
                            "| Risk | Severity | Mitigation | Status |",
                            "| --- | --- | --- | --- |",
                            "| Audit-log observability gap | medium | Validate dashboard before cutover | conditional |",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.decision_summary.write_text(
                    json.dumps(
                        {
                            "recommended_decision": "conditional_go",
                            "blocking_issue_count": 1,
                            "ready_for_packaging": True,
                            "authoritative_artifacts": [
                                "go_no_go_assessment",
                                "risk_register",
                                "decision_summary",
                            ],
                            "justification_summary": "Proceed if the audit-log dashboard is validated before cutover.",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                "assessed release\n",
            )[3],
            lambda request: (
                request.artifacts.release_decision_package.write_text(
                    "\n".join(
                        (
                            "# Release Decision Package",
                            "",
                            "Decision: `conditional_go`.",
                            "Blocking condition: validate the audit-log dashboard before deployment.",
                            "Rollback posture: reviewed and ready.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.release_communications_draft.write_text(
                    "\n".join(
                        (
                            "# Release Communications Draft",
                            "",
                            "We are prepared to ship release 2026.04 once the audit-log dashboard is validated.",
                            "If the validation slips, hold the release.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "prepared package\n",
            )[2],
        ],
        verifier_turns=[
            Outcome(
                raw_output="release framed\n",
                tag="release_framed",
                payload={
                    "summary": "The release boundary and criteria are explicit.",
                    "authoritative_artifacts": [
                        "release_scope_brief",
                        "decision_criteria",
                        "evidence_intake_register",
                    ],
                    "evidence_focus": ["tests", "rollback", "operations"],
                },
            ),
            Outcome(
                raw_output="evidence ready\n",
                tag="evidence_pack_ready",
                payload={
                    "summary": "The evidence pack covers scope, testing, operations, rollback, and blockers.",
                    "evidence_artifacts": [
                        "release_inventory",
                        "test_evidence_pack",
                        "operational_readiness",
                        "rollback_readiness",
                        "blocking_issues",
                    ],
                    "blocker_artifacts": ["blocking_issues"],
                    "unresolved_gaps": ["audit-log dashboard validation pending"],
                },
            ),
            Outcome(
                raw_output="assessment ready\n",
                tag="assessment_ready",
                payload={
                    "summary": "The assessment supports conditional release packaging.",
                    "evidence_artifacts": [
                        "go_no_go_assessment",
                        "risk_register",
                        "decision_summary",
                    ],
                    "recommended_decision": "conditional_go",
                    "blocking_issue_count": 1,
                },
            ),
            Outcome(
                raw_output="decision package ready\n",
                tag="decision_package_ready",
                payload={
                    "summary": "The package and communication draft are aligned to the assessed recommendation.",
                    "package_artifacts": [
                        "release_decision_package",
                        "release_communications_draft",
                    ],
                    "decision": "conditional_go",
                    "communication_ready": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "release_candidate_to_go_no_go",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="release-go-no-go-task",
            message="We want to ship release 2026.04 on Friday.",
            workflow_params={
                "release_name": "2026.04",
                "target_date": "2026-04-24",
                "deployment_environment": "production",
                "release_owner": "Release Captain",
                "evidence_paths": [
                    "docs/releases/2026.04.md",
                    "reports/test-summary-2026.04.md",
                ],
            },
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "release-go-no-go-task" / "wf_release_candidate_to_go_no_go"
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    decision_summary = json.loads((workflow_dir / "decision_summary.json").read_text(encoding="utf-8"))
    decision_receipt = json.loads((workflow_dir / "decision_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "SUCCESS"
    assert (workflow_dir / "release_scope_brief.md").exists()
    assert (workflow_dir / "decision_criteria.md").exists()
    assert (workflow_dir / "release_inventory.md").exists()
    assert (workflow_dir / "go_no_go_assessment.md").exists()
    assert (workflow_dir / "release_decision_package.md").exists()
    assert (workflow_dir / "release_communications_draft.md").exists()
    assert (workflow_dir / "decision_receipt.json").exists()
    assert invocation_contract == {
        "deployment_environment": "production",
        "evidence_paths": [
            "docs/releases/2026.04.md",
            "reports/test-summary-2026.04.md",
        ],
        "message": "We want to ship release 2026.04 on Friday.\n",
        "release_name": "2026.04",
        "release_owner": "Release Captain",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "target_date": "2026-04-24",
        "task_id": "release-go-no-go-task",
        "workflow_name": "release_candidate_to_go_no_go",
    }
    assert decision_summary == {
        "authoritative_artifacts": [
            "go_no_go_assessment",
            "risk_register",
            "decision_summary",
        ],
        "blocking_issue_count": 1,
        "justification_summary": "Proceed if the audit-log dashboard is validated before cutover.",
        "ready_for_packaging": True,
        "recommended_decision": "conditional_go",
    }
    assert decision_receipt == {
        "blocking_issue_count": 1,
        "communications_draft": str(workflow_dir / "release_communications_draft.md"),
        "decision_package": str(workflow_dir / "release_decision_package.md"),
        "decision_summary": str(workflow_dir / "decision_summary.json"),
        "deployment_environment": "production",
        "published": True,
        "recommended_decision": "conditional_go",
        "release_name": "2026.04",
        "release_owner": "Release Captain",
        "target_date": "2026-04-24",
        "workflow_name": "release_candidate_to_go_no_go",
    }

    assert [call.step_name for call in provider.calls] == [
        "frame_release",
        "frame_release",
        "assemble_evidence_pack",
        "assemble_evidence_pack",
        "assess_go_no_go",
        "assess_go_no_go",
        "prepare_decision_package",
        "prepare_decision_package",
    ]
    assert provider.calls[1].available_routes == (
        "release_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert provider.calls[7].route_contracts["decision_package_ready"]["required_artifacts"] == [
        "release_decision_package",
        "release_communications_draft",
    ]
    assert provider.calls[7].route_contracts["decision_package_ready"]["work_item_effect"] == (
        "Advances the release workflow to deterministic publication of the terminal receipt."
    )
    assert (run_dir / "run.json").exists()


def _install_repo_release_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    shutil.copytree(
        REPO_ROOT / "workflows" / "release_candidate_to_go_no_go",
        workflows_root / "release_candidate_to_go_no_go",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        REPO_ROOT / "docs",
        root / "docs",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (root / "Workflow_Instructions.md").write_text(
        (REPO_ROOT / "Workflow_Instructions.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
