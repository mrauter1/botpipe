from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from autoloop.core.compiler import compile_workflow
from autoloop.core.context import Context
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.stores import InMemorySessionStore
from autoloop.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from autoloop.runtime.loader import (
    WorkflowDiscoveryError,
    WorkflowParameterError,
    coerce_workflow_parameter_mapping,
    discover_workflow_packages,
    resolve_workflow_reference,
)
from autoloop.runtime.runner import RunnerOptions, run_workflow_package
from autoloop_optimizer.adaptation import write_selected_workflow_capability_snapshot
from autoloop.core.primitives import Outcome
from tests.runtime.workflow_contract_helpers import invoke_after_verifier_hook, invoke_python_step


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
        if name == "workflows" or name.startswith("workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def test_repo_workflows_namespace_discovers_candidate_workflow_to_adapted_execution_plan_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "candidate_workflow_to_adapted_execution_plan" in discovered
    package = discovered["candidate_workflow_to_adapted_execution_plan"]
    assert package.package_name == "candidate_workflow_to_adapted_execution_plan"
    assert "adapted-execution-plan" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "workflows" / "candidate_workflow_to_adapted_execution_plan" / "workflow.toml"
    )


def test_candidate_workflow_to_adapted_execution_plan_package_compiles_with_explicit_control_contracts(
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.candidate_workflow_to_adapted_execution_plan")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "capture_selected_workflow_contract",
        "frame_adaptation_request",
        "analyze_adaptation_surface",
        "package_adapted_execution_plan",
        "publish_adapted_execution_plan",
    )

    frame_step = compiled.steps["frame_adaptation_request"]
    assert frame_step.available_routes == (
        "adaptation_request_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(compiled.route("frame_adaptation_request", "adaptation_request_framed").required_writes) == [
        "frame_adaptation_request.adaptation_request_brief",
        "frame_adaptation_request.adaptation_success_criteria",
    ]
    assert frame_step.expected_output_schema is not None

    analysis_step = compiled.steps["analyze_adaptation_surface"]
    assert list(compiled.route("analyze_adaptation_surface", "adaptation_surface_analyzed").required_writes) == [
        "analyze_adaptation_surface.workflow_fit_assessment",
        "analyze_adaptation_surface.step_adaptation_matrix",
    ]
    assert analysis_step.expected_output_schema is not None

    package_step = compiled.steps["package_adapted_execution_plan"]
    assert list(compiled.route("package_adapted_execution_plan", "adapted_execution_plan_ready").required_writes) == [
        "package_adapted_execution_plan.adapted_execution_plan",
        "package_adapted_execution_plan.proposed_workflow_parameters",
        "package_adapted_execution_plan.adapted_execution_summary",
        "package_adapted_execution_plan.adapted_execution_next_action",
    ]
    assert package_step.expected_output_schema is not None
    assert set(package_step.expected_output_schema["required"]) >= {
        "summary",
        "selected_workflow_name",
        "selected_workflow_entry_step",
        "selected_workflow_parameters_supported",
        "proposed_parameter_keys",
        "expected_downstream_artifacts",
        "authoritative_artifacts",
        "next_action",
        "ready_for_execution",
    }

    publish_step = compiled.steps["publish_adapted_execution_plan"]
    assert publish_step.requires == (
        "capture_selected_workflow_contract.selected_workflow_capability",
        "analyze_adaptation_surface.workflow_fit_assessment",
        "analyze_adaptation_surface.step_adaptation_matrix",
        "package_adapted_execution_plan.adapted_execution_plan",
        "package_adapted_execution_plan.proposed_workflow_parameters",
        "package_adapted_execution_plan.adapted_execution_summary",
        "package_adapted_execution_plan.adapted_execution_next_action",
    )


def test_candidate_workflow_to_adapted_execution_plan_package_docs_capture_decision_records() -> None:
    text = (
        REPO_ROOT / "docs" / "workflows" / "candidate_workflow_to_adapted_execution_plan.md"
    ).read_text(encoding="utf-8")

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py",
    ):
        assert required in text


def test_candidate_workflow_to_adapted_execution_plan_prompt_readme_uses_shared_contract_sections() -> None:
    text = (
        REPO_ROOT
        / "workflows"
        / "candidate_workflow_to_adapted_execution_plan"
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
        "`adaptation_request_framed`",
        "`adaptation_surface_analyzed`",
        "`adapted_execution_plan_ready`",
        "`needs_rework`",
        "`needs_replan`",
        "`frame_producer.md` / `frame_verifier.md`",
        "AdaptedExecutionPlanPayload",
        "compact human-readable step contract",
        "Provider raw output is runtime telemetry",
    ):
        assert required in text


@pytest.mark.parametrize(
    ("prompt_name", "required_markers"),
    (
        (
            "frame_producer.md",
            (
                "`adaptation_request_brief`",
                "`adaptation_success_criteria`",
                "`adaptation_request_framed`",
                "`needs_rework`",
                "`needs_replan`",
            ),
        ),
        (
            "frame_verifier.md",
            (
                "Payload requirements",
                "`adaptation_request_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "`selected_workflow_name`",
            ),
        ),
        (
            "analyze_producer.md",
            (
                "`workflow_fit_assessment`",
                "`step_adaptation_matrix`",
                "`adaptation_surface_analyzed`",
                "`needs_rework`",
                "`needs_replan`",
            ),
        ),
        (
            "analyze_verifier.md",
            (
                "Payload requirements",
                "`adaptation_surface_analyzed`",
                "`needs_rework`",
                "`needs_replan`",
                "`proposed_parameter_keys`",
            ),
        ),
        (
            "package_producer.md",
            (
                "`adapted_execution_plan`",
                "`proposed_workflow_parameters`",
                "`adapted_execution_summary`",
                "`adapted_execution_next_action`",
                "`adapted_execution_plan_ready`",
            ),
        ),
        (
            "package_verifier.md",
            (
                "Payload requirements",
                "`adapted_execution_plan_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`validated_workflow_parameters.json`",
            ),
        ),
    ),
)
def test_candidate_workflow_to_adapted_execution_plan_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (
        REPO_ROOT / "workflows" / "candidate_workflow_to_adapted_execution_plan" / "prompts" / prompt_name
    ).read_text(encoding="utf-8")

    _assert_compact_prompt_contract(prompt_name, text, required_markers)


def test_candidate_workflow_to_adapted_execution_plan_package_rejects_blank_selected_workflow(tmp_path: Path) -> None:
    _install_repo_candidate_workflow_to_adapted_execution_plan_package(tmp_path)
    parameters_cls = resolve_workflow_reference(
        tmp_path,
        "candidate_workflow_to_adapted_execution_plan",
    ).parameters_cls

    with pytest.raises(WorkflowParameterError, match="value must be non-empty"):
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "selected_workflow": "   ",
                "task_title": "Admin impersonation privilege escalation response",
            },
        )


def test_candidate_workflow_to_adapted_execution_plan_package_normalizes_repeatable_inputs(tmp_path: Path) -> None:
    _install_repo_candidate_workflow_to_adapted_execution_plan_package(tmp_path)
    parameters_cls = resolve_workflow_reference(
        tmp_path,
        "candidate_workflow_to_adapted_execution_plan",
    ).parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "selected_workflow": " security_finding_to_verified_remediation ",
            "task_title": " Admin impersonation privilege escalation response ",
            "sponsor_role": " Security Engineering ",
            "desired_outcome": " ",
            "constraints": [
                " preserve the workflow boundary ",
                "",
                "preserve the workflow boundary",
                "Prefer validated workflow parameters over workflow edits.",
            ],
            "evidence_expectations": [
                " publish a validated adapted plan ",
                "",
                "publish a validated adapted plan",
                "Keep the selected workflow package unchanged.",
            ],
        },
    )

    assert normalized == {
        "constraints": [
            "preserve the workflow boundary",
            "Prefer validated workflow parameters over workflow edits.",
        ],
        "desired_outcome": None,
        "evidence_expectations": [
            "publish a validated adapted plan",
            "Keep the selected workflow package unchanged.",
        ],
        "selected_workflow": "security_finding_to_verified_remediation",
        "sponsor_role": "Security Engineering",
        "task_title": "Admin impersonation privilege escalation response",
    }


def test_candidate_workflow_to_adapted_execution_plan_bootstrap_reads_typed_ctx_params(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.candidate_workflow_to_adapted_execution_plan")
    parameters_cls = resolve_workflow_reference(REPO_ROOT, "candidate_workflow_to_adapted_execution_plan").parameters_cls
    assert parameters_cls is not None
    typed_params = parameters_cls.model_validate(
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "selected_workflow": " security_finding_to_verified_remediation ",
                "task_title": " Admin impersonation privilege escalation response ",
                "sponsor_role": " Security Engineering ",
                "desired_outcome": " ",
                "constraints": [
                    " preserve the workflow boundary ",
                    "",
                    "preserve the workflow boundary",
                    "Prefer validated workflow parameters over workflow edits.",
                ],
                "evidence_expectations": [
                    " publish a validated adapted plan ",
                    "",
                    "publish a validated adapted plan",
                    "Keep the selected workflow package unchanged.",
                ],
            },
        )
    )

    task_folder = tmp_path / ".autoloop" / "tasks" / "typed-bootstrap-task"
    workflow_folder = task_folder / "wf_candidate_workflow_to_adapted_execution_plan"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Typed bootstrap request.\n", encoding="utf-8")

    ctx = Context(
        task_id="typed-bootstrap-task",
        run_id="run-1",
        workflow_name="candidate_workflow_to_adapted_execution_plan",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "candidate_workflow_to_adapted_execution_plan",
        state=workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={},
    )

    event = invoke_python_step(
        workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan,
        "bootstrap",
        ctx,
    )

    assert event.tag == "inputs_prepared"
    assert ctx.state.selected_workflow_reference == "security_finding_to_verified_remediation"
    assert ctx.state.task_title == "Admin impersonation privilege escalation response"
    assert ctx.state.sponsor_role == "Security Engineering"
    assert ctx.state.desired_outcome is None
    assert ctx.state.constraints == [
        "preserve the workflow boundary",
        "Prefer validated workflow parameters over workflow edits.",
    ]
    assert ctx.state.evidence_expectations == [
        "publish a validated adapted plan",
        "Keep the selected workflow package unchanged.",
    ]

    invocation_contract = json.loads((workflow_folder / "invocation_contract.json").read_text(encoding="utf-8"))
    assert invocation_contract["selected_workflow_reference"] == "security_finding_to_verified_remediation"
    assert invocation_contract["task_title"] == "Admin impersonation privilege escalation response"
    assert invocation_contract["desired_outcome"] is None
    assert invocation_contract["constraints"] == ctx.state.constraints
    assert invocation_contract["evidence_expectations"] == ctx.state.evidence_expectations


def test_candidate_workflow_to_adapted_execution_plan_package_runs_and_publishes_terminal_adaptation_artifacts(
    tmp_path: Path,
) -> None:
    _install_repo_candidate_workflow_to_adapted_execution_plan_package(tmp_path)

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.adaptation_request_brief.write_text(
                    "\n".join(
                        (
                            "# Adaptation Request Brief",
                            "",
                            "Selected workflow: `security_finding_to_verified_remediation`.",
                            "Task: adapt the existing security-remediation workflow for the admin impersonation privilege-escalation finding.",
                            "Sponsor: security engineering.",
                            "Terminal outcome: publish a validated adapted execution package without auto-running the workflow.",
                            "Why this building block matters: the workflow is close, but the task-specific parameter mapping and execution notes need a durable handoff.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.adaptation_success_criteria.write_text(
                    "\n".join(
                        (
                            "# Adaptation Success Criteria",
                            "",
                            "- Keep `security_finding_to_verified_remediation` as the selected workflow boundary.",
                            "- Produce a valid parameter mapping for the selected workflow rather than editing the workflow package.",
                            "- Call out the expected downstream artifacts and the evidence paths that should be carried into the adapted run.",
                            "- Stop at plan publication and do not auto-run the selected workflow.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "framed adaptation request\n",
            )[2],
            lambda request: (
                request.artifacts.workflow_fit_assessment.write_text(
                    "\n".join(
                        (
                            "# Workflow Fit Assessment",
                            "",
                            "- `security_finding_to_verified_remediation` already closes the selected finding to a remediation and closure package.",
                            "- The main adaptation pressure is task-specific parameterization plus explicit evidence-path carry-forward.",
                            "- The workflow boundary stays intact; the operator needs a validated workflow-parameter artifact and step-by-step execution notes.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.step_adaptation_matrix.write_text(
                    "\n".join(
                        (
                            "# Step Adaptation Matrix",
                            "",
                            "| Step | Keep fixed | Task-specific adaptation notes |",
                            "| --- | --- | --- |",
                            "| `bootstrap` | Invocation contract bootstrapping | Carry the selected finding title and sponsor role into the downstream run. |",
                            "| `compose_evidence_pack` | Evidence-pack child composition | Preserve the pentest evidence paths and note the affected admin-impersonation surface. |",
                            "| `assess_security_finding` | Security assessment workflow | Confirm the exploit path and affected systems from the pentest report. |",
                            "| `plan_verified_remediation` | Remediation planning | Keep rollout and rollback notes tied to admin impersonation. |",
                            "| `prepare_closure_package` | Closure packaging | Preserve the customer-safe communication and closure evidence surface. |",
                            "",
                        )
                    )
                    + "\n"
                ),
                "analyzed adaptation surface\n",
            )[2],
            lambda request: (
                request.artifacts.adapted_execution_plan.write_text(
                    "\n".join(
                        (
                            "# Adapted Execution Plan",
                            "",
                            "Selected workflow: `security_finding_to_verified_remediation`.",
                            "Selected workflow entry step: `bootstrap`.",
                            "Why it still fits: the workflow already closes the finding to remediation and closure packaging; this plan only adapts the task-specific inputs and execution notes.",
                            "Validated workflow parameters should provide the finding title, source, severity, affected system, sponsor role, evidence paths, and deployment constraints.",
                            "Carry forward in the downstream message: the pentest trigger, the affected admin-impersonation surface, and the expectation that the workflow should stop at publication of the remediation package.",
                            "Expected downstream artifacts: `selected_remediation_plan`, `remediation_summary`, and `security_remediation_package`.",
                            "No downstream execution has occurred in this run; publication of this package is the terminal result.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.proposed_workflow_parameters.write_text(
                    json.dumps(
                        {
                            "affected_system": "admin impersonation",
                            "deployment_constraints": [
                                "Preserve emergency rollback readiness.",
                                "Coordinate with the admin support rotation before rollout.",
                            ],
                            "evidence_paths": [
                                "evidence/pentest/admin-impersonation-report.md",
                                "evidence/logs/admin-impersonation-trace.txt",
                            ],
                            "finding_source": "pentest",
                            "finding_title": "Admin impersonation privilege escalation",
                            "severity": "high",
                            "sponsor_role": "security engineering",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                request.artifacts.adapted_execution_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "adapted_execution_plan",
                                "adapted_execution_summary",
                                "adapted_execution_next_action",
                                "validated_workflow_parameters",
                            ],
                            "expected_downstream_artifacts": [
                                "selected_remediation_plan",
                                "remediation_summary",
                                "security_remediation_package",
                            ],
                            "next_action": "Run security_finding_to_verified_remediation with the validated workflow parameters and keep this adapted-execution package attached to the downstream run.",
                            "proposed_parameter_keys": [
                                "affected_system",
                                "deployment_constraints",
                                "evidence_paths",
                                "finding_source",
                                "finding_title",
                                "severity",
                                "sponsor_role",
                            ],
                            "ready_for_execution": True,
                            "selected_workflow_entry_step": "bootstrap",
                            "selected_workflow_name": "security_finding_to_verified_remediation",
                            "selected_workflow_parameters_supported": True,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                request.artifacts.adapted_execution_next_action.write_text(
                    "\n".join(
                        (
                            "# Adapted Execution Next Action",
                            "",
                            "1. Run `security_finding_to_verified_remediation`.",
                            "2. Load `validated_workflow_parameters.json` as the authoritative parameter artifact for the downstream run.",
                            "3. Keep this adapted execution plan attached so the operator preserves the expected downstream artifacts and execution notes.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "packaged adapted execution plan\n",
            )[4],
        ],
        verifier_turns=[
            Outcome(
                raw_output="adaptation request framed\n",
                tag="adaptation_request_framed",
                payload={
                    "summary": "The selected workflow, task trigger, and adaptation criteria are explicit.",
                    "authoritative_artifacts": [
                        "adaptation_request_brief",
                        "adaptation_success_criteria",
                    ],
                    "selected_workflow_name": "security_finding_to_verified_remediation",
                    "decision_axes": ["workflow fit", "parameterization", "execution evidence"],
                },
            ),
            Outcome(
                raw_output="adaptation surface analyzed\n",
                tag="adaptation_surface_analyzed",
                payload={
                    "summary": "The selected workflow still fits and the parameterization surface is explicit.",
                    "selected_workflow_name": "security_finding_to_verified_remediation",
                    "expected_downstream_artifacts": [
                        "selected_remediation_plan",
                        "remediation_summary",
                        "security_remediation_package",
                    ],
                    "proposed_parameter_keys": [
                        "affected_system",
                        "deployment_constraints",
                        "evidence_paths",
                        "finding_source",
                        "finding_title",
                        "severity",
                        "sponsor_role",
                    ],
                },
            ),
            Outcome(
                raw_output="adapted execution plan ready\n",
                tag="adapted_execution_plan_ready",
                payload={
                    "summary": "The adapted execution plan, proposed parameters, summary, and next action are aligned.",
                    "selected_workflow_name": "security_finding_to_verified_remediation",
                    "selected_workflow_entry_step": "bootstrap",
                    "selected_workflow_parameters_supported": True,
                    "proposed_parameter_keys": [
                        "affected_system",
                        "deployment_constraints",
                        "evidence_paths",
                        "finding_source",
                        "finding_title",
                        "severity",
                        "sponsor_role",
                    ],
                    "expected_downstream_artifacts": [
                        "selected_remediation_plan",
                        "remediation_summary",
                        "security_remediation_package",
                    ],
                    "authoritative_artifacts": [
                        "adapted_execution_plan",
                        "adapted_execution_summary",
                        "adapted_execution_next_action",
                        "validated_workflow_parameters",
                    ],
                    "next_action": "Run security_finding_to_verified_remediation with the validated workflow parameters and keep this adapted-execution package attached to the downstream run.",
                    "ready_for_execution": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "candidate_workflow_to_adapted_execution_plan",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="candidate-adaptation-task",
            message="Adapt the security remediation workflow for an admin impersonation privilege-escalation finding.",
            workflow_params={
                "selected_workflow": "security_finding_to_verified_remediation",
                "task_title": "Admin impersonation privilege escalation response",
                "sponsor_role": "security engineering",
                "desired_outcome": "Publish an execution-ready adapted remediation plan.",
                "constraints": [
                    "Preserve the existing workflow boundary.",
                    "Prefer validated workflow parameters over workflow edits.",
                ],
                "evidence_expectations": [
                    "Need a validated run plan and concrete next action.",
                    "Keep the selected workflow package unchanged.",
                ],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "candidate-adaptation-task"
    workflow_dir = task_dir / "wf_candidate_workflow_to_adapted_execution_plan"
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    selected_capability = json.loads((workflow_dir / "selected_workflow_capability.json").read_text(encoding="utf-8"))
    adapted_summary = json.loads((workflow_dir / "adapted_execution_summary.json").read_text(encoding="utf-8"))
    validated_parameters = json.loads((workflow_dir / "validated_workflow_parameters.json").read_text(encoding="utf-8"))
    adapted_receipt = json.loads((workflow_dir / "adapted_execution_plan_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert (workflow_dir / "selected_workflow_capability.json").exists()
    assert (workflow_dir / "adaptation_request_brief.md").exists()
    assert (workflow_dir / "adaptation_success_criteria.md").exists()
    assert (workflow_dir / "workflow_fit_assessment.md").exists()
    assert (workflow_dir / "step_adaptation_matrix.md").exists()
    assert (workflow_dir / "adapted_execution_plan.md").exists()
    assert (workflow_dir / "proposed_workflow_parameters.json").exists()
    assert (workflow_dir / "adapted_execution_summary.json").exists()
    assert (workflow_dir / "adapted_execution_next_action.md").exists()
    assert (workflow_dir / "validated_workflow_parameters.json").exists()
    assert (workflow_dir / "adapted_execution_plan_receipt.json").exists()
    assert not (task_dir / "wf_security_finding_to_verified_remediation").exists()
    assert invocation_contract == {
        "constraints": [
            "Preserve the existing workflow boundary.",
            "Prefer validated workflow parameters over workflow edits.",
        ],
        "desired_outcome": "Publish an execution-ready adapted remediation plan.",
        "evidence_expectations": [
            "Need a validated run plan and concrete next action.",
            "Keep the selected workflow package unchanged.",
        ],
        "message": "Adapt the security remediation workflow for an admin impersonation privilege-escalation finding.\n",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "selected_workflow_reference": "security_finding_to_verified_remediation",
        "sponsor_role": "security engineering",
        "task_id": "candidate-adaptation-task",
        "task_title": "Admin impersonation privilege escalation response",
        "workflow_name": "candidate_workflow_to_adapted_execution_plan",
    }
    assert selected_capability["selected_workflow_name"] == "security_finding_to_verified_remediation"
    assert selected_capability["selected_workflow_capability"]["entry_step_name"] == "bootstrap"
    assert selected_capability["selected_workflow_capability"]["parameters_supported"] is True
    assert {
        entry["name"] for entry in selected_capability["selected_workflow_capability"]["parameters"]
    } >= {"finding_title", "finding_source", "severity"}
    assert adapted_summary == {
        "authoritative_artifacts": [
            "adapted_execution_plan",
            "adapted_execution_summary",
            "adapted_execution_next_action",
            "validated_workflow_parameters",
        ],
        "expected_downstream_artifacts": [
            "selected_remediation_plan",
            "remediation_summary",
            "security_remediation_package",
        ],
        "next_action": "Run security_finding_to_verified_remediation with the validated workflow parameters and keep this adapted-execution package attached to the downstream run.",
        "proposed_parameter_keys": [
            "affected_system",
            "deployment_constraints",
            "evidence_paths",
            "finding_source",
            "finding_title",
            "severity",
            "sponsor_role",
        ],
        "ready_for_execution": True,
        "selected_workflow_entry_step": "bootstrap",
        "selected_workflow_name": "security_finding_to_verified_remediation",
        "selected_workflow_parameters_supported": True,
    }
    assert validated_parameters == {
        "repo_root": str(tmp_path.resolve()),
        "run_id": run_dir.name,
        "selected_workflow_name": "security_finding_to_verified_remediation",
        "task_id": "candidate-adaptation-task",
        "validated_parameters": {
            "affected_system": "admin impersonation",
            "deployment_constraints": [
                "Preserve emergency rollback readiness.",
                "Coordinate with the admin support rotation before rollout.",
            ],
            "evidence_paths": [
                "evidence/pentest/admin-impersonation-report.md",
                "evidence/logs/admin-impersonation-trace.txt",
            ],
            "finding_source": "pentest",
            "finding_title": "Admin impersonation privilege escalation",
            "severity": "high",
            "sponsor_role": "security engineering",
        },
        "workflow_name": "candidate_workflow_to_adapted_execution_plan",
    }
    assert adapted_receipt == {
        "adapted_execution_next_action": str(workflow_dir / "adapted_execution_next_action.md"),
        "adapted_execution_plan": str(workflow_dir / "adapted_execution_plan.md"),
        "adapted_execution_summary": str(workflow_dir / "adapted_execution_summary.json"),
        "authoritative_artifacts": [
            "adapted_execution_plan",
            "adapted_execution_summary",
            "adapted_execution_next_action",
            "validated_workflow_parameters",
        ],
        "desired_outcome": "Publish an execution-ready adapted remediation plan.",
        "expected_downstream_artifacts": [
            "selected_remediation_plan",
            "remediation_summary",
            "security_remediation_package",
        ],
        "next_action": "Run security_finding_to_verified_remediation with the validated workflow parameters and keep this adapted-execution package attached to the downstream run.",
        "proposed_parameter_keys": [
            "affected_system",
            "deployment_constraints",
            "evidence_paths",
            "finding_source",
            "finding_title",
            "severity",
            "sponsor_role",
        ],
        "proposed_workflow_parameters": str(workflow_dir / "proposed_workflow_parameters.json"),
        "published": True,
        "selected_workflow_capability": str(workflow_dir / "selected_workflow_capability.json"),
        "selected_workflow_entry_step": "bootstrap",
        "selected_workflow_name": "security_finding_to_verified_remediation",
        "selected_workflow_reference": "security_finding_to_verified_remediation",
        "sponsor_role": "security engineering",
        "step_adaptation_matrix": str(workflow_dir / "step_adaptation_matrix.md"),
        "task_title": "Admin impersonation privilege escalation response",
        "validated_workflow_parameters": str(workflow_dir / "validated_workflow_parameters.json"),
        "workflow_fit_assessment": str(workflow_dir / "workflow_fit_assessment.md"),
        "workflow_name": "candidate_workflow_to_adapted_execution_plan",
    }
    assert [call.step_name for call in provider.calls] == [
        "frame_adaptation_request",
        "frame_adaptation_request",
        "analyze_adaptation_surface",
        "analyze_adaptation_surface",
        "package_adapted_execution_plan",
        "package_adapted_execution_plan",
    ]
    assert list(provider.calls[1].route_required_writes["adaptation_request_framed"]) == [
        "frame_adaptation_request.adaptation_request_brief",
        "frame_adaptation_request.adaptation_success_criteria",
    ]
    assert provider.calls[3].available_routes == (
        "adaptation_surface_analyzed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(provider.calls[5].route_required_writes["adapted_execution_plan_ready"]) == [
        "package_adapted_execution_plan.adapted_execution_plan",
        "package_adapted_execution_plan.proposed_workflow_parameters",
        "package_adapted_execution_plan.adapted_execution_summary",
        "package_adapted_execution_plan.adapted_execution_next_action",
    ]


def test_candidate_workflow_to_adapted_execution_plan_package_needs_rework_payload_updates_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.candidate_workflow_to_adapted_execution_plan")
    state = workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan.State(
        selected_workflow_reference="security_finding_to_verified_remediation",
        selected_workflow_name="security_finding_to_verified_remediation",
        task_title="Admin impersonation privilege escalation response",
    )
    task_folder = tmp_path / ".autoloop" / "tasks" / "adapted-execution-task"
    workflow_folder = task_folder / "wf_candidate_workflow_to_adapted_execution_plan"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    ctx = Context(
        task_id="adapted-execution-task",
        run_id="run-1",
        workflow_name="candidate_workflow_to_adapted_execution_plan",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "candidate_workflow_to_adapted_execution_plan",
        state=state,
        session_store=InMemorySessionStore(),
        workflow_params={},
    )

    invoke_after_verifier_hook(
        workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan,
        "package_adapted_execution_plan",
        ctx,
        outcome=Outcome(
            raw_output="package needs local repair\n",
            tag="needs_rework",
            payload={
                "summary": "The package boundary still holds, but the artifacts need local repair.",
                "selected_workflow_name": "security_finding_to_verified_remediation",
                "selected_workflow_entry_step": "bootstrap",
                "selected_workflow_parameters_supported": True,
                "proposed_parameter_keys": [
                    "affected_system",
                    "finding_source",
                    "finding_title",
                    "severity",
                    "sponsor_role",
                ],
                "expected_downstream_artifacts": [
                    "selected_remediation_plan",
                    "remediation_summary",
                    "security_remediation_package",
                ],
                "authoritative_artifacts": [
                    "adapted_execution_plan",
                    "adapted_execution_summary",
                    "adapted_execution_next_action",
                    "validated_workflow_parameters",
                ],
                "next_action": "Repair the package artifacts and rerun packaging.",
                "ready_for_execution": False,
            },
        ),
    )

    assert ctx.state.packaging_status == "needs_rework"
    assert ctx.state.selected_workflow_name == "security_finding_to_verified_remediation"
    assert ctx.state.proposed_parameter_keys == [
        "affected_system",
        "finding_source",
        "finding_title",
        "severity",
        "sponsor_role",
    ]


@pytest.mark.parametrize(
    "missing_field",
    (
        "selected_workflow_parameters_supported",
        "proposed_parameter_keys",
        "ready_for_execution",
    ),
)
def test_candidate_workflow_to_adapted_execution_plan_package_validator_rejects_missing_required_package_fields(
    monkeypatch,
    missing_field: str,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.candidate_workflow_to_adapted_execution_plan")
    compiled = compile_workflow(workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan)
    package_step = compiled.steps["package_adapted_execution_plan"]
    payload = {
        "summary": "The package boundary still holds, but the artifacts need local repair.",
        "selected_workflow_name": "security_finding_to_verified_remediation",
        "selected_workflow_entry_step": "bootstrap",
        "selected_workflow_parameters_supported": True,
        "proposed_parameter_keys": [
            "affected_system",
            "finding_source",
            "finding_title",
            "severity",
            "sponsor_role",
        ],
        "expected_downstream_artifacts": [
            "selected_remediation_plan",
            "remediation_summary",
            "security_remediation_package",
        ],
        "authoritative_artifacts": [
            "adapted_execution_plan",
            "adapted_execution_summary",
            "adapted_execution_next_action",
            "validated_workflow_parameters",
        ],
        "next_action": "Repair the package artifacts and rerun packaging.",
        "ready_for_execution": False,
    }
    payload.pop(missing_field)

    with pytest.raises(ValidationError, match=missing_field):
        package_step.expected_output_validator(payload)


def test_candidate_workflow_to_adapted_execution_plan_publish_rejects_invalid_selected_workflow_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_adaptation_test_context(
        tmp_path,
        monkeypatch,
        selected_workflow_reference="unknown_workflow",
    )

    with pytest.raises(WorkflowDiscoveryError, match="unknown workflow"):
        invoke_python_step(workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan, "publish_adapted_execution_plan", ctx)


def test_candidate_workflow_to_adapted_execution_plan_publish_rejects_summary_missing_typed_required_field(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_adaptation_test_context(
        tmp_path,
        monkeypatch,
        summary_overrides={"selected_workflow_entry_step": None},
    )
    payload = json.loads((ctx.workflow_folder / "adapted_execution_summary.json").read_text(encoding="utf-8"))
    payload.pop("selected_workflow_entry_step")
    (ctx.workflow_folder / "adapted_execution_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="selected_workflow_entry_step"):
        invoke_python_step(workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan, "publish_adapted_execution_plan", ctx)


def test_candidate_workflow_to_adapted_execution_plan_publish_rejects_invalid_proposed_parameter_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_adaptation_test_context(
        tmp_path,
        monkeypatch,
        proposed_parameters={
            "finding_title": "Admin impersonation privilege escalation",
            "severity": "high",
        },
    )

    with pytest.raises(WorkflowParameterError, match="finding_source"):
        invoke_python_step(workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan, "publish_adapted_execution_plan", ctx)


def test_candidate_workflow_to_adapted_execution_plan_publish_rejects_missing_authoritative_artifact_declaration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_adaptation_test_context(
        tmp_path,
        monkeypatch,
        summary_overrides={
            "authoritative_artifacts": [
                "adapted_execution_plan",
                "adapted_execution_summary",
                "adapted_execution_next_action",
            ]
        },
    )

    with pytest.raises(ValueError, match="authoritative_artifacts must include"):
        invoke_python_step(workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan, "publish_adapted_execution_plan", ctx)


def test_candidate_workflow_to_adapted_execution_plan_publish_rejects_summary_drift_from_validated_parameters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_adaptation_test_context(
        tmp_path,
        monkeypatch,
        summary_overrides={"proposed_parameter_keys": ["finding_title", "finding_source", "unexpected"]},
    )

    with pytest.raises(ValueError, match="proposed_parameter_keys must match validated_workflow_parameters.json"):
        invoke_python_step(workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan, "publish_adapted_execution_plan", ctx)


def test_candidate_workflow_to_adapted_execution_plan_publish_rejects_summary_selected_workflow_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_adaptation_test_context(
        tmp_path,
        monkeypatch,
        summary_overrides={"selected_workflow_name": "incident_to_hardening_program"},
    )

    with pytest.raises(
        ValueError,
        match="adapted_execution_summary.json selected_workflow_name must match selected_workflow_capability.json",
    ):
        invoke_python_step(workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan, "publish_adapted_execution_plan", ctx)


def test_candidate_workflow_capture_step_normalizes_alias_without_revalidating_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_repo_candidate_workflow_to_adapted_execution_plan_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.candidate_workflow_to_adapted_execution_plan")
    workflow_module = importlib.import_module("workflows.candidate_workflow_to_adapted_execution_plan.workflow")

    def _unexpected_validate(*args, **kwargs):
        raise AssertionError("capture step should not revalidate the capability snapshot to recover the workflow name")

    monkeypatch.setattr(workflow_module, "validate_selected_workflow_capability_snapshot", _unexpected_validate)

    task_folder = tmp_path / ".autoloop" / "tasks" / "candidate-capture-task"
    workflow_folder = task_folder / "wf_candidate_workflow_to_adapted_execution_plan"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    state = workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan.State(
        selected_workflow_reference="security-remediation",
        task_title="Admin impersonation privilege escalation response",
    )
    ctx = Context(
        task_id="candidate-capture-task",
        run_id="run-1",
        workflow_name="candidate_workflow_to_adapted_execution_plan",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=tmp_path / "workflows" / "candidate_workflow_to_adapted_execution_plan",
        state=state,
        session_store=InMemorySessionStore(),
        workflow_params={"selected_workflow": "security-remediation", "task_title": state.task_title},
    )

    event = invoke_python_step(
        workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan,
        "capture_selected_workflow_contract",
        ctx,
    )

    snapshot = json.loads((workflow_folder / "selected_workflow_capability.json").read_text(encoding="utf-8"))

    assert event.tag == "selected_workflow_contract_captured"
    assert ctx.state.selected_workflow_name == "security_finding_to_verified_remediation"
    assert snapshot["selected_workflow_name"] == "security_finding_to_verified_remediation"
    assert snapshot["selected_workflow_capability"]["workflow_name"] == "security_finding_to_verified_remediation"


def _make_publish_adaptation_test_context(
    tmp_path: Path,
    monkeypatch,
    *,
    selected_workflow_reference: str = "security_finding_to_verified_remediation",
    snapshot_workflow_name: str = "security_finding_to_verified_remediation",
    proposed_parameters: object | None = None,
    summary_overrides: dict[str, object] | None = None,
) -> tuple[object, object, Context]:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.candidate_workflow_to_adapted_execution_plan")
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_candidate_workflow_to_adapted_execution_plan"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)

    state = workflow_pkg.CandidateWorkflowToAdaptedExecutionPlan.State(
        selected_workflow_reference=selected_workflow_reference,
        selected_workflow_name=snapshot_workflow_name,
        task_title="Admin impersonation privilege escalation response",
        sponsor_role="security engineering",
        desired_outcome="Publish an execution-ready adapted remediation plan.",
        proposed_parameter_keys=[
            "affected_system",
            "deployment_constraints",
            "evidence_paths",
            "finding_source",
            "finding_title",
            "severity",
            "sponsor_role",
        ],
    )
    ctx = Context(
        task_id="candidate-adaptation-task",
        run_id="run-1",
        workflow_name="candidate_workflow_to_adapted_execution_plan",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "candidate_workflow_to_adapted_execution_plan",
        state=state,
        session_store=InMemorySessionStore(),
        workflow_params={
            "selected_workflow": selected_workflow_reference,
            "task_title": state.task_title,
        },
    )

    write_selected_workflow_capability_snapshot(ctx, snapshot_workflow_name)
    for name in (
        "workflow_fit_assessment.md",
        "step_adaptation_matrix.md",
        "adapted_execution_plan.md",
        "adapted_execution_next_action.md",
    ):
        (workflow_folder / name).write_text("# Placeholder\n", encoding="utf-8")

    proposed_payload = (
        proposed_parameters
        if proposed_parameters is not None
        else {
            "affected_system": "admin impersonation",
            "deployment_constraints": [
                "Preserve emergency rollback readiness.",
                "Coordinate with the admin support rotation before rollout.",
            ],
            "evidence_paths": [
                "evidence/pentest/admin-impersonation-report.md",
                "evidence/logs/admin-impersonation-trace.txt",
            ],
            "finding_source": "pentest",
            "finding_title": "Admin impersonation privilege escalation",
            "severity": "high",
            "sponsor_role": "security engineering",
        }
    )
    (workflow_folder / "proposed_workflow_parameters.json").write_text(
        json.dumps(proposed_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary_payload = {
        "authoritative_artifacts": [
            "adapted_execution_plan",
            "adapted_execution_summary",
            "adapted_execution_next_action",
            "validated_workflow_parameters",
        ],
        "expected_downstream_artifacts": [
            "selected_remediation_plan",
            "remediation_summary",
            "security_remediation_package",
        ],
        "next_action": "Run security_finding_to_verified_remediation with the validated workflow parameters and keep this adapted-execution package attached to the downstream run.",
        "proposed_parameter_keys": list(state.proposed_parameter_keys),
        "ready_for_execution": True,
        "selected_workflow_entry_step": "bootstrap",
        "selected_workflow_name": snapshot_workflow_name,
        "selected_workflow_parameters_supported": True,
    }
    if summary_overrides:
        summary_payload.update(summary_overrides)
    (workflow_folder / "adapted_execution_summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return workflow_pkg, state, ctx


def _install_repo_candidate_workflow_to_adapted_execution_plan_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
        "candidate_workflow_to_adapted_execution_plan",
        "security_finding_to_verified_remediation",
        "investigation_request_to_evidence_pack",
    ):
        shutil.copytree(
            REPO_ROOT / "workflows" / package_name,
            workflows_root / package_name,
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
