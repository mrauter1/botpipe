from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from autoloop.core.compiler import compile_workflow
from autoloop.core.context import ChildWorkflowResult, Context
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.stores import InMemorySessionStore
from autoloop.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from autoloop.runtime.loader import (
    WorkflowParameterError,
    coerce_workflow_parameter_mapping,
    discover_workflow_packages,
    resolve_workflow_reference,
)
from autoloop.runtime.runner import RunnerOptions, run_workflow_package
from autoloop.core.primitives import Event, Outcome
from tests.runtime.workflow_contract_helpers import invoke_python_step


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMON_PROMPT_CONTRACT_MARKERS = (
    "## Step Contract",
    "## Artifact Contract",
    "| Artifact | Direction | Notes |",
    "## Output Requirements",
    "## Routes",
    "## Forbidden",
)
LEGACY_PROMPT_SCAFFOLDING_MARKERS = ("Read these artifacts", "Write these artifacts")


def _assert_compact_prompt_contract(
    prompt_name: str,
    text: str,
    required_markers: tuple[str, ...],
) -> None:
    for marker in COMMON_PROMPT_CONTRACT_MARKERS:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"

    for marker in required_markers:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"

    for marker in LEGACY_PROMPT_SCAFFOLDING_MARKERS:
        assert marker not in text, f"{prompt_name} still contains legacy scaffolding marker: {marker}"


def _clear_workflow_modules() -> None:
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows.") or name == "autoloop.workflows" or name.startswith("autoloop.workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def test_repo_workflows_namespace_discovers_security_remediation_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "security_finding_to_verified_remediation" in discovered
    package = discovered["security_finding_to_verified_remediation"]
    assert package.package_name == "security_finding_to_verified_remediation"
    assert "security-remediation" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "autoloop" / "workflows" / "security_finding_to_verified_remediation" / "workflow.toml"
    )


def test_security_remediation_package_compiles_with_explicit_control_contracts(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("autoloop.workflows.security_finding_to_verified_remediation")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.SecurityFindingToVerifiedRemediation)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "compose_evidence_pack",
        "assess_security_finding",
        "plan_verified_remediation",
        "prepare_closure_package",
        "publish_remediation",
    )

    assess_step = compiled.steps["assess_security_finding"]
    assert assess_step.available_routes == (
        "finding_assessed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(compiled.routes["assess_security_finding"]["finding_assessed"].required_writes) == [
        "assess_security_finding.exploit_summary",
        "assess_security_finding.affected_surface",
        "assess_security_finding.root_cause_analysis",
        "assess_security_finding.remediation_options",
        "assess_security_finding.assessment_summary",
    ]
    assert assess_step.expected_output_schema is not None

    remediation_step = compiled.steps["plan_verified_remediation"]
    assert list(compiled.routes["plan_verified_remediation"]["remediation_planned"].required_writes) == [
        "plan_verified_remediation.selected_remediation_plan",
        "plan_verified_remediation.verification_plan",
        "plan_verified_remediation.rollout_plan",
        "plan_verified_remediation.rollback_safety_plan",
        "plan_verified_remediation.remediation_summary",
    ]
    assert remediation_step.expected_output_schema is not None

    closure_step = compiled.steps["prepare_closure_package"]
    assert list(compiled.routes["prepare_closure_package"]["closure_package_ready"].required_writes) == [
        "prepare_closure_package.security_remediation_package",
        "prepare_closure_package.stakeholder_communication_draft",
        "prepare_closure_package.closure_evidence_requirements",
    ]
    assert closure_step.expected_output_schema is not None


def test_security_remediation_package_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "security_finding_to_verified_remediation.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_security_finding_to_verified_remediation.py",
    ):
        assert required in text


def test_security_remediation_prompt_readme_uses_shared_contract_sections() -> None:
    text = (
        REPO_ROOT
        / "autoloop" / "workflows" / "security_finding_to_verified_remediation"
        / "prompts"
        / "README.md"
    ).read_text(encoding="utf-8")

    for required in (
        "## Shared README Boundary",
        "## Keep In Each Prompt",
        "## Step Surface",
        "## Route Surface",
        "## Verifier Payloads",
        "Runtime control route:",
        "`question` when provider questions are allowed by the interaction policy",
        "Application routes:",
        "ordinary application routes rather than framework defaults",
        "`evidence_pack_adopted`",
        "`finding_assessed`",
        "`remediation_planned`",
        "`closure_package_ready`",
        "`needs_rework`",
        "`needs_replan`",
        "System step (no prompt files)",
        "SecurityClosurePackagePayload",
        "compact human-readable step contract",
        "Provider raw output is runtime telemetry",
    ):
        assert required in text


def test_security_remediation_prompt_inventory_matches_expected_contract_surface() -> None:
    prompt_dir = REPO_ROOT / "autoloop" / "workflows" / "security_finding_to_verified_remediation" / "prompts"

    assert sorted(path.name for path in prompt_dir.glob("*.md")) == [
        "README.md",
        "assessment_producer.md",
        "assessment_verifier.md",
        "closure_producer.md",
        "closure_verifier.md",
        "remediation_producer.md",
        "remediation_verifier.md",
    ]


@pytest.mark.parametrize(
    ("prompt_name", "required_markers"),
    (
        (
            "assessment_producer.md",
            (
                "`exploit_summary`",
                "`root_cause_analysis`",
                "`assessment_summary`",
                "`finding_assessed`",
                "`preferred_remediation_option`",
            ),
        ),
        (
            "assessment_verifier.md",
            (
                "Required outcome structure",
                "`finding_assessed`",
                "`needs_rework`",
                "`needs_replan`",
                "`exploitability`",
            ),
        ),
        (
            "remediation_producer.md",
            (
                "`selected_remediation_plan`",
                "`verification_plan`",
                "`remediation_summary`",
                "`remediation_planned`",
                "`selected_remediation`",
            ),
        ),
        (
            "remediation_verifier.md",
            (
                "Required outcome structure",
                "`remediation_planned`",
                "`needs_rework`",
                "`needs_replan`",
                "`rollout_ready`",
            ),
        ),
        (
            "closure_producer.md",
            (
                "`security_remediation_package`",
                "`stakeholder_communication_draft`",
                "`closure_evidence_requirements`",
                "`closure_package_ready`",
                "`needs_replan`",
            ),
        ),
        (
            "closure_verifier.md",
            (
                "Required outcome structure",
                "`closure_package_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`closure_ready`",
            ),
        ),
    ),
)
def test_security_remediation_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (
        REPO_ROOT
        / "autoloop" / "workflows" / "security_finding_to_verified_remediation"
        / "prompts"
        / prompt_name
    ).read_text(encoding="utf-8")

    _assert_compact_prompt_contract(prompt_name, text, required_markers)


def test_security_remediation_package_rejects_blank_finding_title(tmp_path: Path) -> None:
    _install_repo_security_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "security_finding_to_verified_remediation").parameters_cls

    with pytest.raises(WorkflowParameterError, match="finding_title"):
        coerce_workflow_parameter_mapping(parameters_cls, {"finding_title": "   ", "finding_source": "pentest"})


def test_security_remediation_package_normalizes_repeatable_inputs(tmp_path: Path) -> None:
    _install_repo_security_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "security_finding_to_verified_remediation").parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "finding_title": " Admin impersonation privilege escalation ",
            "finding_source": " pentest ",
            "severity": " high ",
            "affected_system": " delegated admin impersonation ",
            "sponsor_role": " Security Engineering ",
            "evidence_paths": [
                " pentest/findings/admin-impersonation.md ",
                "",
                "pentest/findings/admin-impersonation.md",
                "src/auth/impersonation.py",
            ],
            "deployment_constraints": [
                " preserve emergency admin access during rollout ",
                "",
                "preserve emergency admin access during rollout",
                "Avoid schema changes in the same patch.",
            ],
        },
    )

    assert normalized == {
        "affected_system": "delegated admin impersonation",
        "deployment_constraints": [
            "preserve emergency admin access during rollout",
            "Avoid schema changes in the same patch.",
        ],
        "evidence_paths": [
            "pentest/findings/admin-impersonation.md",
            "src/auth/impersonation.py",
        ],
        "finding_source": "pentest",
        "finding_title": "Admin impersonation privilege escalation",
        "severity": "high",
        "sponsor_role": "Security Engineering",
    }


def test_security_remediation_bootstrap_reads_typed_ctx_params(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("autoloop.workflows.security_finding_to_verified_remediation")
    parameters_cls = resolve_workflow_reference(REPO_ROOT, "security_finding_to_verified_remediation").parameters_cls
    assert parameters_cls is not None
    typed_params = parameters_cls.model_validate(
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "finding_title": " Admin impersonation privilege escalation ",
                "finding_source": " pentest ",
                "severity": " high ",
                "affected_system": " delegated admin impersonation ",
                "sponsor_role": " Security Engineering ",
                "evidence_paths": [
                    " pentest/findings/admin-impersonation.md ",
                    "",
                    "pentest/findings/admin-impersonation.md",
                    "src/auth/impersonation.py",
                ],
                "deployment_constraints": [
                    " preserve emergency admin access during rollout ",
                    "",
                    "preserve emergency admin access during rollout",
                    "Avoid schema changes in the same patch.",
                ],
            },
        )
    )

    task_folder = tmp_path / ".autoloop" / "tasks" / "typed-bootstrap-task"
    workflow_folder = task_folder / "wf_security_finding_to_verified_remediation"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Typed bootstrap request.\n", encoding="utf-8")

    ctx = Context(
        task_id="typed-bootstrap-task",
        run_id="run-1",
        workflow_name="security_finding_to_verified_remediation",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "autoloop" / "workflows" / "security_finding_to_verified_remediation",
        state=workflow_pkg.SecurityFindingToVerifiedRemediation.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={
            "finding_title": "wrong finding",
            "finding_source": "other",
            "severity": "low",
            "affected_system": "wrong system",
            "sponsor_role": "Wrong Sponsor",
            "evidence_paths": ["wrong/path.md"],
            "deployment_constraints": ["wrong constraint"],
        },
    )

    event = invoke_python_step(
        workflow_pkg.SecurityFindingToVerifiedRemediation,
        "bootstrap",
        ctx,
    )

    assert event.tag == "inputs_prepared"
    assert ctx.state.finding_title == "Admin impersonation privilege escalation"
    assert ctx.state.finding_source == "pentest"
    assert ctx.state.severity == "high"
    assert ctx.state.affected_system == "delegated admin impersonation"
    assert ctx.state.sponsor_role == "Security Engineering"
    assert ctx.state.evidence_paths == [
        "pentest/findings/admin-impersonation.md",
        "src/auth/impersonation.py",
    ]
    assert ctx.state.deployment_constraints == [
        "preserve emergency admin access during rollout",
        "Avoid schema changes in the same patch.",
    ]
    assert ctx.get_session("assessment_session") is not None
    assert ctx.get_session("remediation_session") is not None
    assert ctx.get_session("closure_session") is not None

    invocation_contract = json.loads((workflow_folder / "invocation_contract.json").read_text(encoding="utf-8"))
    assert invocation_contract["finding_title"] == "Admin impersonation privilege escalation"
    assert invocation_contract["finding_source"] == "pentest"
    assert invocation_contract["severity"] == "high"
    assert invocation_contract["affected_system"] == "delegated admin impersonation"
    assert invocation_contract["sponsor_role"] == "Security Engineering"
    assert invocation_contract["evidence_paths"] == ctx.state.evidence_paths
    assert invocation_contract["deployment_constraints"] == ctx.state.deployment_constraints


def test_security_remediation_package_runs_and_emits_terminal_receipt(tmp_path: Path) -> None:
    _install_repo_security_package(tmp_path)
    provider = _successful_security_remediation_provider()

    result = run_workflow_package(
        "security_finding_to_verified_remediation",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="security-remediation-task",
            message="Pentest found privilege escalation in admin impersonation.",
            workflow_params={
                "finding_title": "Admin impersonation privilege escalation",
                "finding_source": "pentest",
                "severity": "high",
                "affected_system": "delegated admin impersonation",
                "sponsor_role": "security engineering",
                "evidence_paths": [
                    "pentest/findings/admin-impersonation.md",
                    "src/auth/impersonation.py",
                ],
                "deployment_constraints": [
                    "Preserve emergency admin access during rollout.",
                    "Avoid schema changes in the same patch.",
                ],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "security-remediation-task"
    workflow_dir = task_dir / "wf_security_finding_to_verified_remediation"
    run_dir = next((workflow_dir / "runs").iterdir())
    child_workflow_dir = task_dir / "wf_investigation_request_to_evidence_pack"
    child_run_dir = next((child_workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    remediation_summary = json.loads((workflow_dir / "remediation_summary.json").read_text(encoding="utf-8"))
    remediation_receipt = json.loads((workflow_dir / "remediation_receipt.json").read_text(encoding="utf-8"))
    child_records = [
        json.loads(line)
        for line in (run_dir / "children.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert result.terminal == "FINISH"
    assert (workflow_dir / "finding_scope_brief.md").exists()
    assert (workflow_dir / "security_evidence_pack.md").exists()
    assert (workflow_dir / "security_evidence_pack_summary.json").exists()
    assert (workflow_dir / "security_evidence_gap_register.md").exists()
    assert (workflow_dir / "exploit_summary.md").exists()
    assert (workflow_dir / "root_cause_analysis.md").exists()
    assert (workflow_dir / "selected_remediation_plan.md").exists()
    assert (workflow_dir / "security_remediation_package.md").exists()
    assert (workflow_dir / "closure_evidence_requirements.md").exists()
    assert (workflow_dir / "remediation_receipt.json").exists()
    assert invocation_contract == {
        "affected_system": "delegated admin impersonation",
        "deployment_constraints": [
            "Preserve emergency admin access during rollout.",
            "Avoid schema changes in the same patch.",
        ],
        "evidence_paths": [
            "pentest/findings/admin-impersonation.md",
            "src/auth/impersonation.py",
        ],
        "finding_source": "pentest",
        "finding_title": "Admin impersonation privilege escalation",
        "message": "Pentest found privilege escalation in admin impersonation.\n",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "severity": "high",
        "sponsor_role": "security engineering",
        "task_id": "security-remediation-task",
        "workflow_name": "security_finding_to_verified_remediation",
    }
    assert remediation_summary == {
        "authoritative_artifacts": [
            "selected_remediation_plan",
            "verification_plan",
            "rollout_plan",
            "rollback_safety_plan",
            "remediation_summary",
        ],
        "rollout_ready": True,
        "selected_remediation": "Unify impersonation authorization in the shared policy helper and require delegated-admin audit fields.",
        "summary": "The shared helper remediation is implementable, verifiable, and safe to roll out with a guarded migration.",
        "verification_ready": True,
    }
    assert remediation_receipt["finding_title"] == "Admin impersonation privilege escalation"
    assert remediation_receipt["finding_source"] == "pentest"
    assert remediation_receipt["severity"] == "high"
    assert remediation_receipt["selected_remediation"] == (
        "Unify impersonation authorization in the shared policy helper and require delegated-admin audit fields."
    )
    assert remediation_receipt["verification_ready"] is True
    assert remediation_receipt["rollout_ready"] is True
    assert remediation_receipt["source_count"] == 3
    assert remediation_receipt["finding_count"] == 3
    assert remediation_receipt["unresolved_gap_count"] == 1
    assert remediation_receipt["evidence_pack_child_run_id"] == child_run_dir.name
    assert remediation_receipt["security_evidence_pack_summary"] == str(workflow_dir / "security_evidence_pack_summary.json")
    assert remediation_receipt["security_evidence_pack_receipt"] == str(workflow_dir / "security_evidence_pack_receipt.json")
    assert remediation_receipt["remediation_summary"] == str(workflow_dir / "remediation_summary.json")
    assert remediation_receipt["security_remediation_package"] == str(workflow_dir / "security_remediation_package.md")
    assert remediation_receipt["published"] is True
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "Pentest found privilege escalation in admin impersonation.\n"
    assert (child_run_dir / "request.md").read_text(encoding="utf-8") == (
        'Assemble the evidence pack for the security finding "Admin impersonation privilege escalation" affecting delegated admin impersonation.\n'
    )
    assert (workflow_dir / "finding_scope_brief.md").read_text(encoding="utf-8") == (
        child_workflow_dir / "investigation_scope_brief.md"
    ).read_text(encoding="utf-8")
    assert (workflow_dir / "security_evidence_pack.md").read_text(encoding="utf-8") == (
        child_workflow_dir / "evidence_pack.md"
    ).read_text(encoding="utf-8")
    assert json.loads((workflow_dir / "security_evidence_pack_summary.json").read_text(encoding="utf-8")) == json.loads(
        (child_workflow_dir / "evidence_pack_summary.json").read_text(encoding="utf-8")
    )
    assert child_records[0]["workflow_name"] == "investigation_request_to_evidence_pack"
    assert child_records[0]["status"] == "success"
    assert child_records[0]["last_event"] == {
        "tag": "evidence_pack_published",
        "reason": "",
        "question": None,
        "handoff": None,
    }
    assert child_records[0]["output_artifacts"]["evidence_pack_receipt"] == str(
        child_workflow_dir / "evidence_pack_receipt.json"
    )
    assert [call.step_name for call in provider.calls] == [
        "frame_investigation",
        "frame_investigation",
        "assemble_evidence_pack",
        "assemble_evidence_pack",
        "assess_security_finding",
        "assess_security_finding",
        "plan_verified_remediation",
        "plan_verified_remediation",
        "prepare_closure_package",
        "prepare_closure_package",
    ]
    assert list(provider.calls[5].route_required_writes["finding_assessed"]) == [
        "assess_security_finding.exploit_summary",
        "assess_security_finding.affected_surface",
        "assess_security_finding.root_cause_analysis",
        "assess_security_finding.remediation_options",
        "assess_security_finding.assessment_summary",
    ]
    assert list(provider.calls[9].route_required_writes["closure_package_ready"]) == [
        "prepare_closure_package.security_remediation_package",
        "prepare_closure_package.stakeholder_communication_draft",
        "prepare_closure_package.closure_evidence_requirements",
    ]


def test_security_remediation_package_propagates_child_question_without_adopting_artifacts(tmp_path: Path) -> None:
    _install_repo_security_package(tmp_path)
    provider = _child_question_provider()

    result = run_workflow_package(
        "security_finding_to_verified_remediation",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="security-remediation-question-task",
            message="Pentest found privilege escalation in admin impersonation.",
            workflow_params={
                "finding_title": "Admin impersonation privilege escalation",
                "finding_source": "pentest",
                "severity": "high",
                "affected_system": "delegated admin impersonation",
                "sponsor_role": "security engineering",
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "security-remediation-question-task"
    workflow_dir = task_dir / "wf_security_finding_to_verified_remediation"
    run_dir = next((workflow_dir / "runs").iterdir())
    child_workflow_dir = task_dir / "wf_investigation_request_to_evidence_pack"
    child_run_dir = next((child_workflow_dir / "runs").iterdir())
    parent_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    child_meta = json.loads((child_run_dir / "run.json").read_text(encoding="utf-8"))
    child_records = [
        json.loads(line)
        for line in (run_dir / "children.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert result.terminal == "AWAIT_INPUT"
    assert parent_meta["status"] == "awaiting_input"
    assert parent_meta["pending_input"]["question"] == "Which production environment should bound the blast radius?"
    assert child_meta["status"] == "awaiting_input"
    assert child_meta["pending_input"]["question"] == "Which production environment should bound the blast radius?"
    assert not (workflow_dir / "finding_scope_brief.md").exists()
    assert not (workflow_dir / "security_evidence_pack.md").exists()
    assert child_records[0]["workflow_name"] == "investigation_request_to_evidence_pack"
    assert child_records[0]["status"] == "awaiting_input"
    assert child_records[0]["last_event"] == {
        "handoff": None,
        "tag": "question",
        "reason": "",
        "question": "Which production environment should bound the blast radius?",
    }
    assert [call.step_name for call in provider.calls] == [
        "frame_investigation",
        "frame_investigation",
    ]


def test_security_remediation_package_blocks_when_child_publishes_not_ready_pack(tmp_path: Path) -> None:
    _install_repo_security_package(tmp_path)
    provider = _child_not_ready_provider()

    result = run_workflow_package(
        "security_finding_to_verified_remediation",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="security-remediation-blocked-task",
            message="Pentest found privilege escalation in admin impersonation.",
            workflow_params={
                "finding_title": "Admin impersonation privilege escalation",
                "finding_source": "pentest",
                "severity": "high",
                "affected_system": "delegated admin impersonation",
                "sponsor_role": "security engineering",
                "evidence_paths": [
                    "pentest/findings/admin-impersonation.md",
                    "src/auth/impersonation.py",
                ],
                "deployment_constraints": [
                    "Preserve emergency admin access during rollout.",
                    "Avoid schema changes in the same patch.",
                ],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "security-remediation-blocked-task"
    workflow_dir = task_dir / "wf_security_finding_to_verified_remediation"
    run_dir = next((workflow_dir / "runs").iterdir())
    child_workflow_dir = task_dir / "wf_investigation_request_to_evidence_pack"
    child_run_dir = next((child_workflow_dir / "runs").iterdir())
    parent_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    child_meta = json.loads((child_run_dir / "run.json").read_text(encoding="utf-8"))
    child_invocation_contract = json.loads((child_workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    child_records = [
        json.loads(line)
        for line in (run_dir / "children.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert result.terminal == "AWAIT_INPUT"
    assert result.last_event is not None
    assert result.last_event.tag == "blocked"
    assert result.last_event.reason == "Child evidence pack published without downstream-readiness approval."
    assert parent_meta["status"] == "blocked"
    assert child_meta["status"] == "success"
    assert child_invocation_contract["source_constraints"] == []
    assert child_invocation_contract["evidence_paths"] == [
        "pentest/findings/admin-impersonation.md",
        "src/auth/impersonation.py",
    ]
    assert not (workflow_dir / "finding_scope_brief.md").exists()
    assert not (workflow_dir / "security_evidence_pack.md").exists()
    assert not (workflow_dir / "security_evidence_pack_summary.json").exists()
    assert not (workflow_dir / "exploit_summary.md").exists()
    assert child_records[0]["workflow_name"] == "investigation_request_to_evidence_pack"
    assert child_records[0]["status"] == "success"
    assert child_records[0]["last_event"] == {
        "tag": "evidence_pack_published",
        "reason": "",
        "question": None,
        "handoff": None,
    }
    assert [call.step_name for call in provider.calls] == [
        "frame_investigation",
        "frame_investigation",
        "assemble_evidence_pack",
        "assemble_evidence_pack",
    ]


def test_security_remediation_compose_step_blocks_not_ready_child_and_keeps_deployment_constraints_local(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("autoloop.workflows.security_finding_to_verified_remediation")
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_security_finding_to_verified_remediation"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    child_workflow_folder = task_folder / "wf_investigation_request_to_evidence_pack"
    child_workflow_folder.mkdir(parents=True, exist_ok=True)
    child_run_folder = child_workflow_folder / "runs" / "child-run-1"
    child_run_folder.mkdir(parents=True, exist_ok=True)
    (child_run_folder / "sessions").mkdir(parents=True, exist_ok=True)
    (child_run_folder / "raw").mkdir(parents=True, exist_ok=True)
    (child_run_folder / "request.md").write_text(
        'Assemble the evidence pack for the security finding "Admin impersonation privilege escalation".\n',
        encoding="utf-8",
    )

    child_artifacts = {
        "investigation_scope_brief": child_workflow_folder / "investigation_scope_brief.md",
        "evidence_pack": child_workflow_folder / "evidence_pack.md",
        "evidence_pack_summary": child_workflow_folder / "evidence_pack_summary.json",
        "evidence_gap_register": child_workflow_folder / "evidence_gap_register.md",
        "evidence_pack_receipt": child_workflow_folder / "evidence_pack_receipt.json",
    }
    child_artifacts["investigation_scope_brief"].write_text("# Investigation Scope Brief\n", encoding="utf-8")
    child_artifacts["evidence_pack"].write_text("# Evidence Pack\n", encoding="utf-8")
    child_artifacts["evidence_pack_summary"].write_text(
        json.dumps(
            {
                "authoritative_artifacts": [
                    "evidence_source_inventory",
                    "evidence_coverage_matrix",
                    "evidence_findings",
                    "evidence_gap_register",
                    "evidence_pack",
                    "evidence_pack_summary",
                ],
                "finding_count": 2,
                "investigation_kind": "security_remediation",
                "key_findings": ["Delegated-admin bypass confirmed."],
                "ready_for_downstream_assessment": False,
                "source_count": 2,
                "unresolved_gap_count": 1,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    child_artifacts["evidence_gap_register"].write_text("# Evidence Gap Register\n", encoding="utf-8")
    child_artifacts["evidence_pack_receipt"].write_text("{}\n", encoding="utf-8")

    child_result = ChildWorkflowResult(
        workflow_name="investigation_request_to_evidence_pack",
        run_id="child-run-1",
        terminal="FINISH",
        status="success",
        last_event=Event("evidence_pack_published"),
        output_metadata={},
        output_artifacts=child_artifacts,
        task_folder=task_folder,
        workflow_folder=child_workflow_folder,
        run_folder=child_run_folder,
        package_folder=REPO_ROOT / "autoloop" / "workflows" / "investigation_request_to_evidence_pack",
        request_file=child_run_folder / "request.md",
        run_meta_file=child_run_folder / "run.json",
        events_file=child_run_folder / "events.jsonl",
        checkpoint_file=child_run_folder / "checkpoint.json",
        sessions_dir=child_run_folder / "sessions",
        trace_file=child_run_folder / "trace.jsonl",
        raw_dir=child_run_folder / "raw",
        parent_file=child_run_folder / "parent.json",
    )
    child_invocation: dict[str, object] = {}

    def _invoke_child(workflow, *, message: str, parameters: dict[str, object]):
        child_invocation["workflow"] = workflow
        child_invocation["message"] = message
        child_invocation["parameters"] = parameters
        return child_result

    state = workflow_pkg.SecurityFindingToVerifiedRemediation.State(
        finding_title="Admin impersonation privilege escalation",
        finding_source="pentest",
        severity="high",
        affected_system="delegated admin impersonation",
        sponsor_role="security engineering",
        evidence_paths=[
            "pentest/findings/admin-impersonation.md",
            "src/auth/impersonation.py",
        ],
        deployment_constraints=[
            "Preserve emergency admin access during rollout.",
            "Avoid schema changes in the same patch.",
        ],
    )
    ctx = Context(
        task_id="security-remediation-task",
        run_id="run-1",
        workflow_name="security_finding_to_verified_remediation",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "autoloop" / "workflows" / "security_finding_to_verified_remediation",
        state=state,
        session_store=InMemorySessionStore(),
        workflow_invoker=_invoke_child,
    )

    event = invoke_python_step(
        workflow_pkg.SecurityFindingToVerifiedRemediation,
        "compose_evidence_pack",
        ctx,
    )

    assert child_invocation == {
        "workflow": "investigation_request_to_evidence_pack",
        "message": (
            'Assemble the evidence pack for the security finding "Admin impersonation privilege escalation" '
            "affecting delegated admin impersonation."
        ),
        "parameters": {
            "investigation_title": "Admin impersonation privilege escalation",
            "investigation_kind": "security_remediation",
            "sponsor_role": "security engineering",
            "evidence_paths": [
                "pentest/findings/admin-impersonation.md",
                "src/auth/impersonation.py",
            ],
        },
    }
    assert event.tag == "blocked"
    assert event.reason == "Child evidence pack published without downstream-readiness approval."
    assert ctx.state.evidence_pack_status == "blocked"
    assert ctx.state.evidence_pack_child_run_id == "child-run-1"
    assert ctx.state.ready_for_downstream_assessment is False
    assert not (workflow_folder / "finding_scope_brief.md").exists()
    assert not (workflow_folder / "security_evidence_pack.md").exists()
    assert not (workflow_folder / "security_evidence_pack_summary.json").exists()
    assert not (workflow_folder / "security_evidence_gap_register.md").exists()
    assert not (workflow_folder / "security_evidence_pack_receipt.json").exists()


def test_security_remediation_publish_rejects_missing_selected_remediation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("autoloop.workflows.security_finding_to_verified_remediation")
    workflow_folder = tmp_path / "task" / "wf_security_finding_to_verified_remediation"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    (workflow_folder / "security_evidence_pack_summary.json").write_text(
        json.dumps(
            {
                "investigation_kind": "security_remediation",
                "source_count": 3,
                "finding_count": 2,
                "unresolved_gap_count": 1,
                "key_findings": ["Delegated-admin bypass confirmed."],
                "ready_for_downstream_assessment": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "security_evidence_pack_receipt.json").write_text("{}\n", encoding="utf-8")
    (workflow_folder / "remediation_summary.json").write_text(
        json.dumps(
            {
                "authoritative_artifacts": ["selected_remediation_plan"],
                "rollout_ready": True,
                "verification_ready": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for name in (
        "selected_remediation_plan.md",
        "verification_plan.md",
        "rollout_plan.md",
        "rollback_safety_plan.md",
        "security_remediation_package.md",
        "stakeholder_communication_draft.md",
        "closure_evidence_requirements.md",
    ):
        (workflow_folder / name).write_text(f"# {name}\n", encoding="utf-8")

    state = workflow_pkg.SecurityFindingToVerifiedRemediation.State(
        finding_title="Admin impersonation privilege escalation",
        finding_source="pentest",
        severity="high",
        affected_system="delegated admin impersonation",
        sponsor_role="security engineering",
    )
    ctx = Context(
        task_id="security-remediation-task",
        run_id="run-1",
        workflow_name="security_finding_to_verified_remediation",
        task_folder=tmp_path / "task",
        workflow_folder=workflow_folder,
        run_folder=tmp_path / "task" / "wf_security_finding_to_verified_remediation" / "runs" / "run-1",
        package_folder=REPO_ROOT / "autoloop" / "workflows" / "security_finding_to_verified_remediation",
        state=state,
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(ValueError, match="selected_remediation"):
        invoke_python_step(workflow_pkg.SecurityFindingToVerifiedRemediation, "publish_remediation", ctx)

    assert not (workflow_folder / "remediation_receipt.json").exists()


def _successful_security_remediation_provider() -> ScriptedLLMProvider:
    return ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.investigation_scope_brief.write_text(
                    "\n".join(
                        (
                            "# Investigation Scope Brief",
                            "",
                            "Trigger: pentest evidence of privilege escalation in admin impersonation.",
                            "Sponsor: security engineering.",
                            "Scope: delegated-admin impersonation authorization, audit logging, and session traceability.",
                            "Out of scope: unrelated billing and reporting code paths.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.investigation_objectives.write_text(
                    "\n".join(
                        (
                            "# Investigation Objectives",
                            "",
                            "- Bound the exploitability of delegated-admin impersonation.",
                            "- Capture the proof and remaining evidence gaps the remediation workflow must respect.",
                            "- Publish an evidence pack a downstream security-remediation workflow can consume directly.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_intake_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Intake Register",
                            "",
                            "- pentest/findings/admin-impersonation.md",
                            "- src/auth/impersonation.py",
                            "- docs/admin-impersonation-audit.md",
                            "- Missing: production audit excerpt for delegated-admin impersonation sessions.",
                            "",
                        )
                    )
                    + "\n",
                ),
                "framed investigation\n",
            )[3],
            lambda request: (
                request.artifacts.evidence_source_inventory.write_text(
                    "\n".join(
                        (
                            "# Evidence Source Inventory",
                            "",
                            "- `pentest/findings/admin-impersonation.md`: confirms a delegated-admin impersonation bypass path.",
                            "- `src/auth/impersonation.py`: shows API-side checks diverge from the shared authorization helper.",
                            "- `docs/admin-impersonation-audit.md`: documents missing delegated-admin audit fields.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_coverage_matrix.write_text(
                    "\n".join(
                        (
                            "# Evidence Coverage Matrix",
                            "",
                            "| Objective | Supporting evidence | Gaps |",
                            "| --- | --- | --- |",
                            "| Bound exploitability | pentest finding, impersonation code path | production audit excerpt for affected sessions |",
                            "| Confirm auditability | audit doc and code review | no production sample with delegated-admin trace |",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_findings.write_text(
                    "\n".join(
                        (
                            "# Evidence Findings",
                            "",
                            "1. Admin impersonation checks diverge between the API handler and the shared role-enforcement helper.",
                            "2. The pentest finding and the code path point to the same delegated-admin bypass surface.",
                            "3. Audit logging does not capture delegated-admin scope for impersonation sessions.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_gap_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Gap Register",
                            "",
                            "- Missing production audit excerpt for delegated-admin sessions; blast radius cannot be fully bounded from repo evidence alone.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_pack.write_text(
                    "\n".join(
                        (
                            "# Evidence Pack",
                            "",
                            "This evidence pack covers the admin impersonation privilege-escalation finding.",
                            "",
                            "## Sources reviewed",
                            "- pentest finding",
                            "- impersonation code path",
                            "- audit documentation",
                            "",
                            "## Key findings",
                            "- API and helper checks diverge.",
                            "- Audit logging is incomplete for delegated-admin impersonation.",
                            "",
                            "## Unresolved gaps",
                            "- Missing production audit excerpt for delegated-admin impersonation sessions.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_pack_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "evidence_source_inventory",
                                "evidence_coverage_matrix",
                                "evidence_findings",
                                "evidence_gap_register",
                                "evidence_pack",
                                "evidence_pack_summary",
                            ],
                            "finding_count": 3,
                            "investigation_kind": "security_remediation",
                            "key_findings": [
                                "Admin impersonation checks diverge between the API handler and the shared role-enforcement helper.",
                                "Audit logging does not capture delegated admin scope for impersonation sessions.",
                            ],
                            "ready_for_downstream_assessment": True,
                            "source_count": 3,
                            "unresolved_gap_count": 1,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                ),
                "assembled evidence pack\n",
            )[6],
            lambda request: (
                request.artifacts.exploit_summary.write_text(
                    "\n".join(
                        (
                            "# Exploit Summary",
                            "",
                            "Exploitability: confirmed for delegated-admin impersonation requests.",
                            "Evidence: the pentest report and authorization-path inspection identify the same bypass.",
                            "Uncertainty: production audit excerpts are still missing, so the full blast radius remains partially bounded.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.affected_surface.write_text(
                    "\n".join(
                        (
                            "# Affected Surface",
                            "",
                            "- Delegated-admin impersonation entry points in the API handler.",
                            "- Shared authorization helper behavior for impersonation sessions.",
                            "- Audit-log traceability for delegated-admin scope.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.root_cause_analysis.write_text(
                    "\n".join(
                        (
                            "# Root Cause Analysis",
                            "",
                            "- The API handler performs an authorization check that diverges from the shared helper.",
                            "- The shared helper does not require delegated-admin scope to be recorded in audit fields.",
                            "- This combination permits impersonation without durable delegated-admin trace evidence.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.remediation_options.write_text(
                    "\n".join(
                        (
                            "# Remediation Options",
                            "",
                            "1. Unify impersonation authorization in the shared policy helper and require delegated-admin audit fields.",
                            "2. Add compensating checks in the API handler only.",
                            "",
                            "Option 1 is preferred because it closes the divergence at the shared control point and strengthens auditability in one path.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.assessment_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "exploit_summary",
                                "affected_surface",
                                "root_cause_analysis",
                                "remediation_options",
                                "assessment_summary",
                            ],
                            "exploitability": "confirmed",
                            "preferred_remediation_option": "Unify impersonation authorization in the shared policy helper and require delegated-admin audit fields.",
                            "summary": "The evidence-backed security assessment confirms the exploit and points to a shared-helper remediation.",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                ),
                "assessed finding\n",
            )[5],
            lambda request: (
                request.artifacts.selected_remediation_plan.write_text(
                    "\n".join(
                        (
                            "# Selected Remediation Plan",
                            "",
                            "Chosen remediation: unify impersonation authorization in the shared policy helper and require delegated-admin audit fields.",
                            "Why: it removes the API/helper divergence and hardens auditability in the same change.",
                            "Implementation shape: update the shared helper, remove divergent handler checks, and add delegated-admin audit-field enforcement.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.verification_plan.write_text(
                    "\n".join(
                        (
                            "# Verification Plan",
                            "",
                            "- Add regression tests for delegated-admin impersonation authorization.",
                            "- Add a negative test that rejects impersonation without delegated-admin scope.",
                            "- Verify audit entries include delegated-admin scope after rollout.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.rollout_plan.write_text(
                    "\n".join(
                        (
                            "# Rollout Plan",
                            "",
                            "- Ship the helper and audit-field changes behind a short-lived feature flag if needed.",
                            "- Roll out during a staffed window to preserve emergency admin access.",
                            "- Validate delegated-admin audit output before removing temporary guardrails.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.rollback_safety_plan.write_text(
                    "\n".join(
                        (
                            "# Rollback Safety Plan",
                            "",
                            "- Keep the prior authorization path available behind a fast rollback toggle.",
                            "- Monitor impersonation denial rates and audit-write failures during rollout.",
                            "- If delegated-admin access fails unexpectedly, revert the shared-helper enforcement and retain the audit logging patch for analysis.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.remediation_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "selected_remediation_plan",
                                "verification_plan",
                                "rollout_plan",
                                "rollback_safety_plan",
                                "remediation_summary",
                            ],
                            "rollout_ready": True,
                            "selected_remediation": "Unify impersonation authorization in the shared policy helper and require delegated-admin audit fields.",
                            "summary": "The shared helper remediation is implementable, verifiable, and safe to roll out with a guarded migration.",
                            "verification_ready": True,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                ),
                "planned remediation\n",
            )[5],
            lambda request: (
                request.artifacts.security_remediation_package.write_text(
                    "\n".join(
                        (
                            "# Security Remediation Package",
                            "",
                            "Finding: delegated-admin impersonation privilege escalation.",
                            "Selected remediation: unify authorization in the shared helper and require delegated-admin audit fields.",
                            "Verification: tests plus audit-log validation before final closure.",
                            "Residual risk: production blast radius stays partially bounded until audit proof is collected.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.stakeholder_communication_draft.write_text(
                    "\n".join(
                        (
                            "# Stakeholder Communication Draft",
                            "",
                            "We confirmed the impersonation authorization gap and prepared a shared-helper remediation.",
                            "Closure will require regression proof and delegated-admin audit validation before the finding is marked closed.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.closure_evidence_requirements.write_text(
                    "\n".join(
                        (
                            "# Closure Evidence Requirements",
                            "",
                            "- Passing regression tests for delegated-admin impersonation authorization.",
                            "- Proof that delegated-admin scope is present in audit records after rollout.",
                            "- AppSec sign-off that the shared-helper change closes the original bypass.",
                            "",
                        )
                    )
                    + "\n",
                ),
                "prepared closure package\n",
            )[3],
        ],
        verifier_turns=[
            Outcome(
                raw_output="framed investigation\n",
                tag="investigation_framed",
                payload={
                    "summary": "The security investigation boundary and evidence intake plan are explicit.",
                    "authoritative_artifacts": [
                        "investigation_scope_brief",
                        "investigation_objectives",
                        "evidence_intake_register",
                    ],
                    "evidence_focus": [
                        "impersonation authorization path",
                        "delegated-admin audit coverage",
                    ],
                },
            ),
            Outcome(
                raw_output="evidence pack ready\n",
                tag="evidence_pack_ready",
                payload={
                    "summary": "The evidence pack is source-traced, gap-aware, and ready for downstream security assessment.",
                    "evidence_artifacts": [
                        "evidence_source_inventory",
                        "evidence_coverage_matrix",
                        "evidence_findings",
                        "evidence_gap_register",
                        "evidence_pack",
                        "evidence_pack_summary",
                    ],
                    "source_count": 3,
                    "unresolved_gaps": [
                        "Missing production audit excerpt for delegated-admin impersonation sessions.",
                    ],
                    "key_findings": [
                        "Admin impersonation checks diverge between the API handler and the role-enforcement helper.",
                        "Audit logging does not capture delegated admin scope for impersonation sessions.",
                    ],
                    "ready_for_downstream_assessment": True,
                },
            ),
            Outcome(
                raw_output="finding assessed\n",
                tag="finding_assessed",
                payload={
                    "summary": "The exploit, affected surface, and remediation options are explicit enough for remediation planning.",
                    "assessment_artifacts": [
                        "exploit_summary",
                        "affected_surface",
                        "root_cause_analysis",
                        "remediation_options",
                        "assessment_summary",
                    ],
                    "preferred_remediation_option": "Unify impersonation authorization in the shared policy helper and require delegated-admin audit fields.",
                    "exploitability": "confirmed",
                },
            ),
            Outcome(
                raw_output="planned remediation\n",
                tag="remediation_planned",
                payload={
                    "summary": "The selected remediation and its verification and rollout plans are explicit and credible.",
                    "remediation_artifacts": [
                        "selected_remediation_plan",
                        "verification_plan",
                        "rollout_plan",
                        "rollback_safety_plan",
                        "remediation_summary",
                    ],
                    "selected_remediation": "Unify impersonation authorization in the shared policy helper and require delegated-admin audit fields.",
                    "verification_ready": True,
                    "rollout_ready": True,
                },
            ),
            Outcome(
                raw_output="prepared closure package\n",
                tag="closure_package_ready",
                payload={
                    "summary": "The final package and communication draft align to the remediation plan and closure proof obligations.",
                    "package_artifacts": [
                        "security_remediation_package",
                        "stakeholder_communication_draft",
                        "closure_evidence_requirements",
                    ],
                    "communication_ready": True,
                    "closure_ready": True,
                },
            ),
        ],
    )


def _child_question_provider() -> ScriptedLLMProvider:
    return ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.investigation_scope_brief.write_text("# Investigation Scope Brief\n"),
                request.artifacts.investigation_objectives.write_text("# Investigation Objectives\n"),
                request.artifacts.evidence_intake_register.write_text("# Evidence Intake Register\n"),
                "framed investigation\n",
            )[3]
        ],
        verifier_turns=[
            Outcome(
                raw_output="need environment\n",
                tag="question",
                question="Which production environment should bound the blast radius?",
                payload={
                    "summary": "The current security finding needs an explicit production environment boundary before framing can continue.",
                    "authoritative_artifacts": [
                        "investigation_scope_brief",
                        "investigation_objectives",
                        "evidence_intake_register",
                    ],
                    "evidence_focus": ["production environment boundary"],
                },
            )
        ],
    )


def _child_not_ready_provider() -> ScriptedLLMProvider:
    return ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.investigation_scope_brief.write_text(
                    "\n".join(
                        (
                            "# Investigation Scope Brief",
                            "",
                            "Scope the delegated-admin impersonation finding and publish the current evidence with gaps intact.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.investigation_objectives.write_text(
                    "\n".join(
                        (
                            "# Investigation Objectives",
                            "",
                            "- Bound what is already proven from the repository and pentest evidence.",
                            "- Surface remaining gaps without overstating readiness for downstream assessment.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_intake_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Intake Register",
                            "",
                            "- pentest/findings/admin-impersonation.md",
                            "- src/auth/impersonation.py",
                            "- Missing: production audit excerpt for delegated-admin impersonation sessions.",
                            "",
                        )
                    )
                    + "\n",
                ),
                "framed investigation\n",
            )[3],
            lambda request: (
                request.artifacts.evidence_source_inventory.write_text(
                    "\n".join(
                        (
                            "# Evidence Source Inventory",
                            "",
                            "- `pentest/findings/admin-impersonation.md`",
                            "- `src/auth/impersonation.py`",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_coverage_matrix.write_text(
                    "\n".join(
                        (
                            "# Evidence Coverage Matrix",
                            "",
                            "| Objective | Supporting evidence | Gaps |",
                            "| --- | --- | --- |",
                            "| Bound exploitability | pentest finding and impersonation code path | production audit excerpt missing |",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_findings.write_text(
                    "\n".join(
                        (
                            "# Evidence Findings",
                            "",
                            "1. The delegated-admin impersonation bypass is reproduced by the pentest and code path.",
                            "2. Production audit proof is still missing, so downstream assessment is not yet ready.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_gap_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Gap Register",
                            "",
                            "- Missing production audit excerpt for delegated-admin impersonation sessions.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_pack.write_text(
                    "\n".join(
                        (
                            "# Evidence Pack",
                            "",
                            "The current evidence confirms the bypass but leaves production audit coverage unresolved.",
                            "",
                        )
                    )
                    + "\n",
                ),
                request.artifacts.evidence_pack_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "evidence_source_inventory",
                                "evidence_coverage_matrix",
                                "evidence_findings",
                                "evidence_gap_register",
                                "evidence_pack",
                                "evidence_pack_summary",
                            ],
                            "finding_count": 2,
                            "investigation_kind": "security_remediation",
                            "key_findings": [
                                "The delegated-admin impersonation bypass is reproduced by the pentest and code path.",
                                "Production audit proof is still missing.",
                            ],
                            "ready_for_downstream_assessment": False,
                            "source_count": 2,
                            "unresolved_gap_count": 1,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                ),
                "assembled evidence pack\n",
            )[6],
        ],
        verifier_turns=[
            Outcome(
                raw_output="framed investigation\n",
                tag="investigation_framed",
                payload={
                    "summary": "The security investigation boundary and intake are explicit.",
                    "authoritative_artifacts": [
                        "investigation_scope_brief",
                        "investigation_objectives",
                        "evidence_intake_register",
                    ],
                    "evidence_focus": [
                        "impersonation authorization path",
                        "missing production audit proof",
                    ],
                },
            ),
            Outcome(
                raw_output="evidence pack ready but not downstream ready\n",
                tag="evidence_pack_ready",
                payload={
                    "summary": "The evidence pack is publishable but not ready for downstream assessment.",
                    "evidence_artifacts": [
                        "evidence_source_inventory",
                        "evidence_coverage_matrix",
                        "evidence_findings",
                        "evidence_gap_register",
                        "evidence_pack",
                        "evidence_pack_summary",
                    ],
                    "source_count": 2,
                    "unresolved_gaps": [
                        "Missing production audit excerpt for delegated-admin impersonation sessions.",
                    ],
                    "key_findings": [
                        "The delegated-admin impersonation bypass is reproduced by the pentest and code path.",
                        "Production audit proof is still missing.",
                    ],
                    "ready_for_downstream_assessment": False,
                },
            ),
        ],
    )


def _install_repo_security_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    shutil.copytree(
        REPO_ROOT / "autoloop" / "workflows" / "security_finding_to_verified_remediation",
        workflows_root / "security_finding_to_verified_remediation",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        REPO_ROOT / "autoloop" / "workflows" / "investigation_request_to_evidence_pack",
        workflows_root / "investigation_request_to_evidence_pack",
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
