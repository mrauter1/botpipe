from __future__ import annotations

import importlib
import json
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.context import Context
from autoloop_v3.core.providers.fake import ScriptedLLMProvider
from autoloop_v3.core.stores import InMemorySessionStore
from autoloop_v3.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from autoloop_v3.runtime.loader import (
    WorkflowParameterError,
    coerce_workflow_parameter_mapping,
    discover_workflow_packages,
    resolve_workflow_reference,
)
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow_package
from workflow.primitives import Outcome


REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "workflow-refinement-task"
PROMPT_RELATIVE_PATH = "workflows/release_candidate_to_go_no_go/prompts/assessment_producer.md"
DOC_RELATIVE_PATH = "docs/workflows/release_candidate_to_go_no_go.md"
TARGET_TEST_COMMAND = "pytest -q tests/runtime/test_release_candidate_to_go_no_go.py"


def _clear_workflow_modules() -> None:
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def test_repo_workflows_namespace_discovers_workflow_and_eval_to_refined_workflow_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "workflow_and_eval_to_refined_workflow_package" in discovered
    package = discovered["workflow_and_eval_to_refined_workflow_package"]
    assert package.package_name == "workflow_and_eval_to_refined_workflow_package"
    assert "workflow-refinement-package" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT
        / "workflows"
        / "workflow_and_eval_to_refined_workflow_package"
        / "workflow.toml"
    )


def test_workflow_and_eval_to_refined_workflow_package_compiles_with_explicit_control_contracts(
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_and_eval_to_refined_workflow_package")
    resolved = resolve_workflow_reference(
        REPO_ROOT,
        workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage,
    )
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "capture_refinement_context",
        "frame_refinement_request",
        "design_refinement_plan",
        "implement_refined_workflow",
        "evaluate_refined_workflow",
        "publish_refined_workflow",
    )

    frame_step = compiled.steps["frame_refinement_request"]
    assert frame_step.available_routes == (
        "refinement_request_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert frame_step.route_contracts["refinement_request_framed"]["required_artifacts"] == [
        "refinement_request_brief",
        "refinement_acceptance_criteria",
    ]
    assert frame_step.expected_output_schema is not None

    design_step = compiled.steps["design_refinement_plan"]
    assert design_step.route_contracts["refinement_plan_designed"]["required_artifacts"] == [
        "refinement_strategy",
        "workflow_change_plan",
        "regression_guardrails",
    ]
    assert design_step.expected_output_schema is not None

    implement_step = compiled.steps["implement_refined_workflow"]
    assert implement_step.route_contracts["workflow_refinement_applied"]["required_artifacts"] == [
        "candidate_workflow_surface",
        "refinement_build_report",
        "candidate_diff_summary",
    ]
    assert implement_step.expected_output_schema is not None
    assert set(implement_step.expected_output_schema["required"]) >= {
        "summary",
        "selected_workflow_name",
        "candidate_file_count",
        "changed_relative_paths",
    }

    evaluate_step = compiled.steps["evaluate_refined_workflow"]
    assert evaluate_step.route_contracts["workflow_refinement_evaluated"]["required_artifacts"] == [
        "refinement_verification_report",
        "evaluation_delta_report",
        "promotion_record",
        "rollback_plan",
    ]
    assert evaluate_step.expected_output_schema is not None
    assert set(evaluate_step.expected_output_schema["required"]) >= {
        "summary",
        "selected_workflow_name",
        "candidate_file_count",
        "validated_overlay_command",
        "authoritative_artifacts",
        "next_action",
        "ready_for_publication",
    }

    publish_step = compiled.steps["publish_refined_workflow"]
    assert publish_step.requires == (
        "selected_workflow_capability",
        "selected_workflow_authoring_surface",
        "baseline_workflow_manifest",
        "baseline_evaluation_summary",
        "baseline_evaluation_findings",
        "baseline_failure_modes",
        "baseline_refinement_evidence",
        "baseline_refinement_evidence_summary",
        "candidate_workflow_manifest",
        "refinement_verification_report",
        "evaluation_delta_report",
        "promotion_record",
        "rollback_plan",
    )


def test_workflow_and_eval_to_refined_workflow_package_docs_capture_decision_records() -> None:
    text = (
        REPO_ROOT / "docs" / "workflows" / "workflow_and_eval_to_refined_workflow_package.md"
    ).read_text(encoding="utf-8")

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py",
    ):
        assert required in text


def test_workflow_and_eval_to_refined_workflow_package_prompt_readme_uses_shared_contract_sections() -> None:
    text = (
        REPO_ROOT
        / "workflows"
        / "workflow_and_eval_to_refined_workflow_package"
        / "prompts"
        / "README.md"
    ).read_text(encoding="utf-8")

    for required in (
        "## Shared README Boundary",
        "## Keep In Each Prompt",
        "## Step Surface",
        "## Route Surface",
        "## Verifier Payloads",
        "Reserved routes:",
        "`question`",
        "`blocked`",
        "`failed`",
        "Application routes:",
        "`refinement_request_framed`",
        "`refinement_plan_designed`",
        "`workflow_refinement_applied`",
        "`workflow_refinement_evaluated`",
        "`needs_rework`",
        "`needs_replan`",
        "`frame_producer.md` / `frame_verifier.md`",
        "WorkflowRefinementEvaluationPayload",
        "compact human-readable step contract",
        "Provider raw output is runtime telemetry",
        "baseline_refinement_evidence.md",
        "candidate-only input rather than proof of improvement",
        "`adversarial_case_candidates` should usually feed `workflow_to_eval_suite`",
    ):
        assert required in text


@pytest.mark.parametrize(
    ("prompt_name", "required_markers"),
    (
        (
            "frame_producer.md",
            (
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "## Evidence",
                "Route guidance for the verifier",
                "Forbidden",
                "`baseline_refinement_evidence_summary`",
                "`refinement_request_brief`",
                "`refinement_acceptance_criteria`",
                "`refinement_request_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "Reserved routes are only",
            ),
        ),
        (
            "frame_verifier.md",
            (
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "Artifact checks",
                "## Evidence",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "`baseline_refinement_evidence_summary`",
                "Do not overwrite `refinement_request_brief` or `refinement_acceptance_criteria` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`refinement_request_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
        (
            "design_producer.md",
            (
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "## Evidence",
                "Route guidance for the verifier",
                "Forbidden",
                "`baseline_refinement_evidence_summary`",
                "`refinement_strategy`",
                "`workflow_change_plan`",
                "`regression_guardrails`",
                "`refinement_plan_designed`",
                "`needs_rework`",
                "`needs_replan`",
                "Reserved routes are only",
            ),
        ),
        (
            "design_verifier.md",
            (
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "Artifact checks",
                "## Evidence",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "`baseline_refinement_evidence_summary`",
                "Do not overwrite `refinement_strategy`, `workflow_change_plan`, or `regression_guardrails` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`refinement_plan_designed`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
        (
            "implement_producer.md",
            (
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "## Evidence",
                "Route guidance for the verifier",
                "Forbidden",
                "`candidate_workflow_surface`",
                "`candidate_workflow_manifest.json`",
                "`refinement_build_report`",
                "`candidate_diff_summary`",
                "`workflow_refinement_applied`",
                "`needs_rework`",
                "`needs_replan`",
                "Reserved routes are only",
            ),
        ),
        (
            "implement_verifier.md",
            (
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "Artifact checks",
                "## Evidence",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "Do not overwrite `candidate_workflow_surface`, `refinement_build_report`, or `candidate_diff_summary` during verification.",
                "Do not hand-write `candidate_workflow_manifest.json` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`workflow_refinement_applied`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
        (
            "evaluate_producer.md",
            (
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "## Evidence",
                "Route guidance for the verifier",
                "Forbidden",
                "`baseline_refinement_evidence_summary`",
                "`refinement_verification_report`",
                "`evaluation_delta_report`",
                "`promotion_record`",
                "`rollback_plan`",
                "`workflow_refinement_evaluated`",
                "`needs_rework`",
                "`needs_replan`",
                "`workflow_refinement_receipt.json`",
                "Reserved routes are only",
            ),
        ),
        (
            "evaluate_verifier.md",
            (
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "Artifact checks",
                "## Evidence",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "`baseline_refinement_evidence_summary`",
                "Do not overwrite `refinement_verification_report`, `evaluation_delta_report`, `promotion_record`, or `rollback_plan` during verification.",
                "Do not create `workflow_refinement_receipt.json` in this step.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`workflow_refinement_evaluated`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
    ),
)
def test_workflow_and_eval_to_refined_workflow_package_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (
        REPO_ROOT
        / "workflows"
        / "workflow_and_eval_to_refined_workflow_package"
        / "prompts"
        / prompt_name
    ).read_text(encoding="utf-8")

    for marker in required_markers:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"


def test_workflow_and_eval_to_refined_workflow_package_rejects_blank_selected_workflow(tmp_path: Path) -> None:
    _install_repo_workflow_and_eval_to_refined_workflow_package(tmp_path)
    parameters_cls = resolve_workflow_reference(
        tmp_path,
        "workflow_and_eval_to_refined_workflow_package",
    ).parameters_cls

    with pytest.raises(WorkflowParameterError, match="value must be non-empty"):
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "selected_workflow": "   ",
                "task_title": "Release workflow refinement",
                "evaluation_summary_path": ".autoloop/evals/summary.json",
                "evaluation_findings_path": ".autoloop/evals/findings.md",
            },
        )


def test_workflow_and_eval_to_refined_workflow_package_normalizes_repeatable_inputs(tmp_path: Path) -> None:
    _install_repo_workflow_and_eval_to_refined_workflow_package(tmp_path)
    parameters_cls = resolve_workflow_reference(
        tmp_path,
        "workflow_and_eval_to_refined_workflow_package",
    ).parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "selected_workflow": " release_candidate_to_go_no_go ",
            "task_title": " Release workflow refinement ",
            "evaluation_summary_path": " .autoloop/evals/summary.json ",
            "evaluation_findings_path": " .autoloop/evals/findings.md ",
            "failure_modes_path": " ",
            "refinement_evidence_path": " ",
            "sponsor_role": " Engineering Productivity ",
            "desired_outcome": " ",
            "constraints": [
                " keep candidate publication explicit ",
                "",
                "keep candidate publication explicit",
                "Do not mutate the authoritative workflow package.",
            ],
            "target_test_command": f" {TARGET_TEST_COMMAND} ",
        },
    )

    assert normalized == {
        "constraints": [
            "keep candidate publication explicit",
            "Do not mutate the authoritative workflow package.",
        ],
        "desired_outcome": None,
        "evaluation_findings_path": ".autoloop/evals/findings.md",
        "evaluation_summary_path": ".autoloop/evals/summary.json",
        "failure_modes_path": None,
        "refinement_evidence_path": None,
        "selected_workflow": "release_candidate_to_go_no_go",
        "sponsor_role": "Engineering Productivity",
        "target_test_command": TARGET_TEST_COMMAND,
        "task_title": "Release workflow refinement",
    }


def test_workflow_and_eval_to_refined_workflow_package_bootstrap_reads_typed_ctx_params(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_and_eval_to_refined_workflow_package")
    parameters_cls = resolve_workflow_reference(REPO_ROOT, "workflow_and_eval_to_refined_workflow_package").parameters_cls
    assert parameters_cls is not None
    typed_params = parameters_cls.model_validate(
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "selected_workflow": " release_candidate_to_go_no_go ",
                "task_title": " Release workflow refinement ",
                "evaluation_summary_path": " .autoloop/evals/summary.json ",
                "evaluation_findings_path": " .autoloop/evals/findings.md ",
                "failure_modes_path": " ",
                "refinement_evidence_path": " ",
                "sponsor_role": " Engineering Productivity ",
                "desired_outcome": " ",
                "constraints": [
                    " keep candidate publication explicit ",
                    "",
                    "keep candidate publication explicit",
                    "Do not mutate the authoritative workflow package.",
                ],
                "target_test_command": f" {TARGET_TEST_COMMAND} ",
            },
        )
    )

    task_folder = tmp_path / ".autoloop" / "tasks" / "typed-bootstrap-task"
    workflow_folder = task_folder / "wf_workflow_and_eval_to_refined_workflow_package"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Typed bootstrap request.\n", encoding="utf-8")

    ctx = Context(
        task_id="typed-bootstrap-task",
        run_id="run-1",
        workflow_name="workflow_and_eval_to_refined_workflow_package",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "workflow_and_eval_to_refined_workflow_package",
        state=workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={},
    )

    next_state, event = workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.on_bootstrap(
        workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.State(),
        ctx,
    )

    assert event.tag == "inputs_prepared"
    assert next_state.selected_workflow_reference == "release_candidate_to_go_no_go"
    assert next_state.task_title == "Release workflow refinement"
    assert next_state.evaluation_summary_path == ".autoloop/evals/summary.json"
    assert next_state.evaluation_findings_path == ".autoloop/evals/findings.md"
    assert next_state.failure_modes_path is None
    assert next_state.refinement_evidence_path is None
    assert next_state.sponsor_role == "Engineering Productivity"
    assert next_state.desired_outcome is None
    assert next_state.constraints == [
        "keep candidate publication explicit",
        "Do not mutate the authoritative workflow package.",
    ]
    assert next_state.target_test_command == TARGET_TEST_COMMAND
    assert ctx.get_session("frame_session") is not None
    assert ctx.get_session("design_session") is not None
    assert ctx.get_session("build_session") is not None
    assert ctx.get_session("evaluate_session") is not None

    invocation_contract = json.loads((workflow_folder / "invocation_contract.json").read_text(encoding="utf-8"))
    assert invocation_contract["selected_workflow_reference"] == "release_candidate_to_go_no_go"
    assert invocation_contract["task_title"] == "Release workflow refinement"
    assert invocation_contract["evaluation_summary_path"] == ".autoloop/evals/summary.json"
    assert invocation_contract["evaluation_findings_path"] == ".autoloop/evals/findings.md"
    assert invocation_contract["failure_modes_path"] is None
    assert invocation_contract["refinement_evidence_path"] is None
    assert invocation_contract["desired_outcome"] is None
    assert invocation_contract["constraints"] == next_state.constraints
    assert invocation_contract["target_test_command"] == TARGET_TEST_COMMAND


def test_workflow_and_eval_to_refined_workflow_package_runs_and_publishes_candidate_refinement_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_refinement_workflow(tmp_path, monkeypatch)

    invocation_contract = json.loads((run.workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    selected_capability = json.loads((run.workflow_dir / "selected_workflow_capability.json").read_text(encoding="utf-8"))
    selected_authoring_surface = json.loads(
        (run.workflow_dir / "selected_workflow_authoring_surface.json").read_text(encoding="utf-8")
    )
    baseline_manifest = json.loads((run.workflow_dir / "baseline_workflow_manifest.json").read_text(encoding="utf-8"))
    candidate_manifest = json.loads((run.workflow_dir / "candidate_workflow_manifest.json").read_text(encoding="utf-8"))
    refinement_receipt = json.loads((run.workflow_dir / "workflow_refinement_receipt.json").read_text(encoding="utf-8"))

    assert run.result.terminal == "SUCCESS"
    assert (run.workflow_dir / "selected_workflow_capability.json").exists()
    assert (run.workflow_dir / "selected_workflow_authoring_surface.json").exists()
    assert (run.workflow_dir / "baseline_workflow_surface").exists()
    assert (run.workflow_dir / "baseline_workflow_manifest.json").exists()
    assert (run.workflow_dir / "baseline_evaluation_summary.json").exists()
    assert (run.workflow_dir / "baseline_evaluation_findings.md").exists()
    assert (run.workflow_dir / "baseline_failure_modes.md").exists()
    assert (run.workflow_dir / "baseline_refinement_evidence.json").exists()
    assert (run.workflow_dir / "baseline_refinement_evidence.md").exists()
    assert (run.workflow_dir / "refinement_request_brief.md").exists()
    assert (run.workflow_dir / "refinement_acceptance_criteria.md").exists()
    assert (run.workflow_dir / "refinement_strategy.md").exists()
    assert (run.workflow_dir / "workflow_change_plan.md").exists()
    assert (run.workflow_dir / "regression_guardrails.md").exists()
    assert (run.workflow_dir / "candidate_workflow_surface").exists()
    assert (run.workflow_dir / "candidate_workflow_manifest.json").exists()
    assert (run.workflow_dir / "refinement_build_report.md").exists()
    assert (run.workflow_dir / "candidate_diff_summary.md").exists()
    assert (run.workflow_dir / "refinement_verification_report.md").exists()
    assert (run.workflow_dir / "evaluation_delta_report.md").exists()
    assert (run.workflow_dir / "promotion_record.md").exists()
    assert (run.workflow_dir / "rollback_plan.md").exists()
    assert (run.workflow_dir / "workflow_refinement_receipt.json").exists()
    assert not (run.task_dir / "wf_release_candidate_to_go_no_go").exists()

    assert invocation_contract == {
        "constraints": [
            "Keep runtime control narrow.",
            "Stop at candidate publication before promotion.",
        ],
        "desired_outcome": "Publish a verified refinement candidate package for the selected workflow.",
        "evaluation_findings_path": ".autoloop/evals/release_go_no_go_eval_findings.md",
        "evaluation_summary_path": ".autoloop/evals/release_go_no_go_eval_summary.json",
        "failure_modes_path": ".autoloop/evals/release_go_no_go_failure_modes.md",
        "refinement_evidence_path": None,
        "message": "Refine the release go/no-go workflow from the latest evaluation evidence.\n",
        "request_file": str(run.run_dir / "request.md"),
        "run_id": run.run_dir.name,
        "selected_workflow_reference": "release_candidate_to_go_no_go",
        "sponsor_role": "engineering productivity",
        "target_test_command": TARGET_TEST_COMMAND,
        "task_id": TASK_ID,
        "task_title": "Release go/no-go refinement from evaluation evidence",
        "workflow_name": "workflow_and_eval_to_refined_workflow_package",
    }
    assert selected_capability["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert selected_capability["selected_workflow_capability"]["entry_step_name"] == "bootstrap"
    assert selected_authoring_surface["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert PROMPT_RELATIVE_PATH in baseline_manifest["relative_paths"]
    assert DOC_RELATIVE_PATH in baseline_manifest["relative_paths"]
    assert "tests/runtime/test_release_candidate_to_go_no_go.py" in baseline_manifest["relative_paths"]
    assert candidate_manifest["surface_kind"] == "candidate"
    assert candidate_manifest["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert candidate_manifest["file_count"] == baseline_manifest["file_count"]
    assert candidate_manifest["changed_relative_paths"] == sorted(
        [DOC_RELATIVE_PATH, PROMPT_RELATIVE_PATH]
    )
    assert candidate_manifest["added_relative_paths"] == []
    assert refinement_receipt["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert refinement_receipt["target_test_command"] == TARGET_TEST_COMMAND
    assert refinement_receipt["changed_relative_paths"] == sorted(
        [DOC_RELATIVE_PATH, PROMPT_RELATIVE_PATH]
    )
    assert refinement_receipt["overlay_validation"] == {
        "compiled_workflow_name": "release_candidate_to_go_no_go",
        "test_command": TARGET_TEST_COMMAND,
        "test_returncode": 0,
    }
    assert refinement_receipt["published"] is True
    assert refinement_receipt["candidate_workflow_manifest"] == str(
        run.workflow_dir / "candidate_workflow_manifest.json"
    )
    assert refinement_receipt["baseline_workflow_manifest"] == str(run.workflow_dir / "baseline_workflow_manifest.json")

    assert (run.workflow_dir / "baseline_workflow_surface" / PROMPT_RELATIVE_PATH).read_text(
        encoding="utf-8"
    ) == run.source_snapshot[PROMPT_RELATIVE_PATH]
    assert (run.workflow_dir / "candidate_workflow_surface" / PROMPT_RELATIVE_PATH).read_text(
        encoding="utf-8"
    ) != run.source_snapshot[PROMPT_RELATIVE_PATH]
    assert (run.workflow_dir / "candidate_workflow_surface" / DOC_RELATIVE_PATH).read_text(
        encoding="utf-8"
    ) != run.source_snapshot[DOC_RELATIVE_PATH]
    assert (tmp_path / PROMPT_RELATIVE_PATH).read_text(encoding="utf-8") == run.source_snapshot[PROMPT_RELATIVE_PATH]
    assert (tmp_path / DOC_RELATIVE_PATH).read_text(encoding="utf-8") == run.source_snapshot[DOC_RELATIVE_PATH]
    baseline_refinement_evidence = json.loads(
        (run.workflow_dir / "baseline_refinement_evidence.json").read_text(encoding="utf-8")
    )
    baseline_refinement_evidence_summary = (run.workflow_dir / "baseline_refinement_evidence.md").read_text(
        encoding="utf-8"
    )
    assert baseline_refinement_evidence == {
        "schema": "autoloop.workflow_refinement_evidence/v1",
        "source_path": None,
        "target_workflow_id": "release_candidate_to_go_no_go",
        "evidence_entries": [],
    }
    assert "No additional optimization refinement evidence was supplied for this run." in baseline_refinement_evidence_summary

    assert [call.step_name for call in run.provider.calls] == [
        "frame_refinement_request",
        "frame_refinement_request",
        "design_refinement_plan",
        "design_refinement_plan",
        "implement_refined_workflow",
        "implement_refined_workflow",
        "evaluate_refined_workflow",
        "evaluate_refined_workflow",
    ]
    assert run.provider.calls[1].route_contracts["refinement_request_framed"]["required_artifacts"] == [
        "refinement_request_brief",
        "refinement_acceptance_criteria",
    ]
    assert run.provider.calls[5].available_routes == (
        "workflow_refinement_applied",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert run.provider.calls[7].route_contracts["workflow_refinement_evaluated"]["required_artifacts"] == [
        "refinement_verification_report",
        "evaluation_delta_report",
        "promotion_record",
        "rollback_plan",
    ]


def test_workflow_and_eval_to_refined_workflow_package_publish_rejects_missing_baseline_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_refinement_workflow(tmp_path, monkeypatch)
    (run.workflow_dir / "baseline_evaluation_findings.md").unlink()

    with pytest.raises(FileNotFoundError, match="baseline_evaluation_findings.md"):
        run.workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.on_publish_refined_workflow(
            run.result.state,
            run.publish_context,
        )


def test_workflow_and_eval_to_refined_workflow_package_rejects_source_evaluation_summary_workflow_mismatch(
    tmp_path: Path,
) -> None:
    _install_repo_workflow_and_eval_to_refined_workflow_package(tmp_path)
    evidence_paths = _write_refinement_evidence(tmp_path)
    summary_path = tmp_path / evidence_paths["evaluation_summary_path"]
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["selected_workflow_name"] = "incident_to_hardening_program"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    provider = ScriptedLLMProvider(producer_turns=[], verifier_turns=[])

    with pytest.raises(
        ValueError,
        match="baseline_evaluation_summary.json selected_workflow_name must match selected workflow",
    ):
        run_workflow_package(
            "workflow_and_eval_to_refined_workflow_package",
            provider=provider,
            options=RunnerOptions(
                root=tmp_path,
                task_id=TASK_ID,
                message="Refine the release go/no-go workflow from the latest evaluation evidence.",
                workflow_params={
                    "selected_workflow": "release_candidate_to_go_no_go",
                    "task_title": "Release go/no-go refinement from evaluation evidence",
                    "evaluation_summary_path": evidence_paths["evaluation_summary_path"],
                    "evaluation_findings_path": evidence_paths["evaluation_findings_path"],
                    "failure_modes_path": evidence_paths["failure_modes_path"],
                    "sponsor_role": "engineering productivity",
                    "desired_outcome": "Publish a verified refinement candidate package for the selected workflow.",
                    "constraints": [
                        "Keep runtime control narrow.",
                        "Stop at candidate publication before promotion.",
                    ],
                    "target_test_command": TARGET_TEST_COMMAND,
                },
                runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
            ),
        )


def test_workflow_and_eval_to_refined_workflow_package_publish_rejects_evaluation_summary_workflow_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_refinement_workflow(tmp_path, monkeypatch)
    summary_path = run.workflow_dir / "baseline_evaluation_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["selected_workflow_name"] = "incident_to_hardening_program"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="baseline_evaluation_summary.json selected_workflow_name must match selected workflow",
    ):
        run.workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.on_publish_refined_workflow(
            run.result.state,
            run.publish_context,
        )


def test_refinement_accepts_optimization_refinement_evidence_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    optimization_evidence_path = _write_optimization_refinement_evidence(tmp_path)
    run = _run_successful_refinement_workflow(
        tmp_path,
        monkeypatch,
        refinement_evidence_path=optimization_evidence_path,
    )

    invocation_contract = json.loads((run.workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    baseline_refinement_evidence = json.loads(
        (run.workflow_dir / "baseline_refinement_evidence.json").read_text(encoding="utf-8")
    )
    baseline_refinement_evidence_summary = (run.workflow_dir / "baseline_refinement_evidence.md").read_text(
        encoding="utf-8"
    )

    assert invocation_contract["refinement_evidence_path"] == optimization_evidence_path
    assert baseline_refinement_evidence["schema"] == "autoloop.workflow_refinement_evidence/v1"
    assert baseline_refinement_evidence["target_workflow_id"] == "release_candidate_to_go_no_go"
    assert [entry["kind"] for entry in baseline_refinement_evidence["evidence_entries"]] == [
        "step_optimization_priority_report",
        "token_optimization_candidates",
        "adversarial_case_candidates",
        "workflow_optimization_scorecard",
    ]
    assert "candidate-only input and remain unproven" in baseline_refinement_evidence_summary
    assert "`adversarial_case_candidates` should usually feed `workflow_to_eval_suite`" in baseline_refinement_evidence_summary


def test_refinement_treats_candidate_without_ablation_as_unproven(
    tmp_path: Path,
    monkeypatch,
) -> None:
    optimization_evidence_path = _write_optimization_refinement_evidence(tmp_path)
    run = _run_successful_refinement_workflow(
        tmp_path,
        monkeypatch,
        refinement_evidence_path=optimization_evidence_path,
    )

    baseline_refinement_evidence_summary = (run.workflow_dir / "baseline_refinement_evidence.md").read_text(
        encoding="utf-8"
    )

    assert "remain unproven until separate ablation or rerun evidence exists" in baseline_refinement_evidence_summary
    assert "`optimization_ablation_results`, when present, are stronger evidence than candidate estimates." in (
        baseline_refinement_evidence_summary
    )


def test_refinement_does_not_materialize_adversarial_cases_automatically(
    tmp_path: Path,
    monkeypatch,
) -> None:
    optimization_evidence_path = _write_optimization_refinement_evidence(tmp_path)
    run = _run_successful_refinement_workflow(
        tmp_path,
        monkeypatch,
        refinement_evidence_path=optimization_evidence_path,
    )

    assert not (run.task_dir / "wf_workflow_to_eval_suite").exists()
    assert not (run.workflow_dir / "validated_eval_case_manifest.json").exists()
    assert not (run.workflow_dir / "adversarial_case_matrix.md").exists()


def test_workflow_and_eval_to_refined_workflow_package_publish_rejects_authoring_surface_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_refinement_workflow(tmp_path, monkeypatch)
    authoring_surface_path = run.workflow_dir / "selected_workflow_authoring_surface.json"
    payload = json.loads(authoring_surface_path.read_text(encoding="utf-8"))
    payload["selected_workflow_authoring_surface"]["workflow_path"] = str(
        tmp_path / "workflows" / "release_candidate_to_go_no_go" / "workflow_drift.py"
    )
    authoring_surface_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="selected_workflow_authoring_surface.json workflow_path must match selected_workflow_capability.json",
    ):
        run.workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.on_publish_refined_workflow(
            run.result.state,
            run.publish_context,
        )


def test_workflow_and_eval_to_refined_workflow_package_publish_rejects_baseline_manifest_boundary_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_refinement_workflow(tmp_path, monkeypatch)
    baseline_manifest_path = run.workflow_dir / "baseline_workflow_manifest.json"
    payload = json.loads(baseline_manifest_path.read_text(encoding="utf-8"))
    payload["package_root_relative_path"] = "workflows/incident_to_hardening_program"
    baseline_manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="baseline_workflow_manifest.json package_root_relative_path must match the expected workflow boundary",
    ):
        run.workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.on_publish_refined_workflow(
            run.result.state,
            run.publish_context,
        )


def test_workflow_and_eval_to_refined_workflow_package_publish_rejects_candidate_manifest_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_refinement_workflow(tmp_path, monkeypatch)
    candidate_manifest_path = run.workflow_dir / "candidate_workflow_manifest.json"
    payload = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
    payload["baseline_relative_paths"] = payload["baseline_relative_paths"][1:]
    candidate_manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="candidate_workflow_manifest.json baseline_relative_paths must match baseline_workflow_manifest.json",
    ):
        run.workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.on_publish_refined_workflow(
            run.result.state,
            run.publish_context,
        )


def test_workflow_and_eval_to_refined_workflow_package_publish_rejects_candidate_manifest_boundary_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_refinement_workflow(tmp_path, monkeypatch)
    candidate_manifest_path = run.workflow_dir / "candidate_workflow_manifest.json"
    payload = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
    payload["package_root_relative_path"] = "workflows/incident_to_hardening_program"
    candidate_manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="candidate_workflow_manifest.json package_root_relative_path must match the expected workflow boundary",
    ):
        run.workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.on_publish_refined_workflow(
            run.result.state,
            run.publish_context,
        )


def test_workflow_and_eval_to_refined_workflow_package_publish_rejects_authoritative_source_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_refinement_workflow(tmp_path, monkeypatch)
    authoritative_prompt = tmp_path / PROMPT_RELATIVE_PATH
    authoritative_prompt.write_text(authoritative_prompt.read_text(encoding="utf-8") + "\nDrift.\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "authoritative selected workflow file changed during refinement publication: "
            f"{re.escape(PROMPT_RELATIVE_PATH)}"
        ),
    ):
        run.workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.on_publish_refined_workflow(
            run.result.state,
            run.publish_context,
        )


def test_workflow_and_eval_to_refined_workflow_package_publish_rejects_candidate_files_outside_selected_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_refinement_workflow(tmp_path, monkeypatch)
    extra_file = run.workflow_dir / "candidate_workflow_surface" / "docs" / "workflows" / "unrelated.md"
    extra_file.parent.mkdir(parents=True, exist_ok=True)
    extra_file.write_text("# Unrelated\n", encoding="utf-8")
    baseline_manifest = json.loads((run.workflow_dir / "baseline_workflow_manifest.json").read_text(encoding="utf-8"))
    run.workflow_pkg._write_candidate_workflow_manifest(
        run.workflow_dir,
        baseline_manifest,
        "release_candidate_to_go_no_go",
    )

    with pytest.raises(
        ValueError,
        match="candidate_workflow_manifest.json must stay scoped to the selected workflow boundary",
    ):
        run.workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.on_publish_refined_workflow(
            run.result.state,
            run.publish_context,
        )


def test_workflow_and_eval_to_refined_workflow_package_publish_rejects_selected_workflow_state_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_refinement_workflow(tmp_path, monkeypatch)
    mismatched_state = run.result.state.model_copy(update={"selected_workflow_name": "incident_to_hardening_program"})

    with pytest.raises(ValueError, match="selected_workflow snapshots must match workflow state"):
        run.workflow_pkg.WorkflowAndEvalToRefinedWorkflowPackage.on_publish_refined_workflow(
            mismatched_state,
            run.publish_context,
        )


def _run_successful_refinement_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    refinement_evidence_path: str | None = None,
) -> SimpleNamespace:
    _install_repo_workflow_and_eval_to_refined_workflow_package(tmp_path)
    evidence_paths = _write_refinement_evidence(tmp_path)
    source_snapshot = {
        PROMPT_RELATIVE_PATH: (tmp_path / PROMPT_RELATIVE_PATH).read_text(encoding="utf-8"),
        DOC_RELATIVE_PATH: (tmp_path / DOC_RELATIVE_PATH).read_text(encoding="utf-8"),
    }

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.refinement_request_brief.write_text(
                    "\n".join(
                        (
                            "# Refinement Request Brief",
                            "",
                            "Selected workflow: `release_candidate_to_go_no_go`.",
                            "Sponsor: engineering productivity.",
                            "Trigger: recent evaluation evidence shows the release assessment prompt needs stronger rollback-gap handling.",
                            "Terminal outcome: publish a candidate refinement package, not an in-place promotion.",
                            "Why the boundary stays fixed: the release go/no-go workflow is still the right workflow; the gap is in prompt and package clarity, not workflow selection.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.refinement_acceptance_criteria.write_text(
                    "\n".join(
                        (
                            "# Refinement Acceptance Criteria",
                            "",
                            "- Keep `release_candidate_to_go_no_go` as the fixed workflow boundary.",
                            "- Address rollback-gap handling in the candidate prompt and workflow docs.",
                            "- Keep the authoritative workflow package unchanged before promotion.",
                            "- Publish explicit promotion and rollback guidance tied to the baseline and candidate manifests.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "framed refinement request\n",
            )[2],
            lambda request: (
                request.artifacts.refinement_strategy.write_text(
                    "\n".join(
                        (
                            "# Refinement Strategy",
                            "",
                            "- Prioritize rollback-gap guidance in the release assessment prompt.",
                            "- Update the workflow doc so later operators understand the intended improvement and candidate-only publication boundary.",
                            "- Keep runtime behavior unchanged and prove the candidate through the existing release runtime test.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.workflow_change_plan.write_text(
                    "\n".join(
                        (
                            "# Workflow Change Plan",
                            "",
                            f"- Update `{PROMPT_RELATIVE_PATH}` in the candidate surface to make rollback gaps explicit before recommending go.",
                            f"- Update `{DOC_RELATIVE_PATH}` in the candidate surface to document the refined emphasis and candidate publication boundary.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.regression_guardrails.write_text(
                    "\n".join(
                        (
                            "# Regression Guardrails",
                            "",
                            f"- Validate the candidate with `{TARGET_TEST_COMMAND}` against an isolated overlay.",
                            "- Keep every baseline file present in the candidate surface.",
                            "- Do not modify the authoritative selected workflow package before promotion.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "designed refinement plan\n",
            )[3],
            lambda request: _write_candidate_surface(request),
            lambda request: (
                request.artifacts.refinement_verification_report.write_text(
                    "\n".join(
                        (
                            "# Refinement Verification Report",
                            "",
                            f"- Candidate overlay should be validated with `{TARGET_TEST_COMMAND}`.",
                            "- Candidate prompt and doc changes stay within the selected workflow boundary.",
                            "- Build artifacts and candidate manifest provide the publish-time validation surface.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.evaluation_delta_report.write_text(
                    "\n".join(
                        (
                            "# Evaluation Delta Report",
                            "",
                            "- Baseline evidence highlighted rollback-gap handling as the main weakness.",
                            "- The candidate prompt now requires explicit rollback-gap handling before a go recommendation.",
                            "- The candidate workflow doc now records the intended improvement and candidate-only publication boundary.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.promotion_record.write_text(
                    "\n".join(
                        (
                            "# Promotion Record",
                            "",
                            "- Promote only after the candidate manifest and overlay validation stay green.",
                            "- Use `baseline_workflow_manifest.json` and `candidate_workflow_manifest.json` as the promotion boundary.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.rollback_plan.write_text(
                    "\n".join(
                        (
                            "# Rollback Plan",
                            "",
                            "- Treat the authoritative selected workflow package as the rollback baseline.",
                            "- If the candidate proves unsafe, discard `candidate_workflow_surface/` and retain the baseline manifest as the authoritative package snapshot.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "evaluated refinement candidate\n",
            )[4],
        ],
        verifier_turns=[
            Outcome(
                raw_output="refinement request framed\n",
                tag="refinement_request_framed",
                payload={
                    "summary": "The selected workflow, baseline evidence, and acceptance boundary are explicit enough for planning.",
                    "authoritative_artifacts": [
                        "refinement_request_brief",
                        "refinement_acceptance_criteria",
                    ],
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "decision_axes": [
                        "rollback-gap handling",
                        "candidate-only publication boundary",
                        "baseline package immutability",
                    ],
                },
            ),
            Outcome(
                raw_output="refinement plan designed\n",
                tag="refinement_plan_designed",
                payload={
                    "summary": "The refinement strategy and file-level change plan are explicit enough for implementation.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "planned_change_paths": sorted([DOC_RELATIVE_PATH, PROMPT_RELATIVE_PATH]),
                    "verification_focus": [
                        "candidate stays within selected workflow boundary",
                        "overlay validation stays on the existing release runtime test",
                    ],
                },
            ),
            lambda request: Outcome(
                raw_output="candidate refinement applied\n",
                tag="workflow_refinement_applied",
                payload={
                    "summary": "The candidate workflow surface and build artifacts are explicit enough for evaluation.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "candidate_file_count": _candidate_file_count(request.artifacts.candidate_workflow_surface.path),
                    "changed_relative_paths": sorted([DOC_RELATIVE_PATH, PROMPT_RELATIVE_PATH]),
                },
            ),
            lambda request: Outcome(
                raw_output="candidate refinement evaluated\n",
                tag="workflow_refinement_evaluated",
                payload={
                    "summary": "The verification package is publication-ready and tied to the candidate manifest boundary.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "candidate_file_count": _candidate_file_count(request.artifacts.candidate_workflow_surface.path),
                    "validated_overlay_command": TARGET_TEST_COMMAND,
                    "authoritative_artifacts": [
                        "refinement_verification_report",
                        "evaluation_delta_report",
                        "promotion_record",
                        "rollback_plan",
                    ],
                    "next_action": "Use the published candidate package and receipt to decide whether to promote the refinement into the authoritative selected workflow package.",
                    "ready_for_publication": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "workflow_and_eval_to_refined_workflow_package",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id=TASK_ID,
            message="Refine the release go/no-go workflow from the latest evaluation evidence.",
            workflow_params={
                "selected_workflow": "release_candidate_to_go_no_go",
                "task_title": "Release go/no-go refinement from evaluation evidence",
                "evaluation_summary_path": evidence_paths["evaluation_summary_path"],
                "evaluation_findings_path": evidence_paths["evaluation_findings_path"],
                "failure_modes_path": evidence_paths["failure_modes_path"],
                "refinement_evidence_path": refinement_evidence_path,
                "sponsor_role": "engineering productivity",
                "desired_outcome": "Publish a verified refinement candidate package for the selected workflow.",
                "constraints": [
                    "Keep runtime control narrow.",
                    "Stop at candidate publication before promotion.",
                ],
                "target_test_command": TARGET_TEST_COMMAND,
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    workflow_pkg = importlib.import_module("workflows.workflow_and_eval_to_refined_workflow_package")

    task_dir = tmp_path / ".autoloop" / "tasks" / TASK_ID
    workflow_dir = task_dir / "wf_workflow_and_eval_to_refined_workflow_package"
    run_dir = next((workflow_dir / "runs").iterdir())
    publish_context = _build_publish_context(
        root=tmp_path,
        task_dir=task_dir,
        workflow_dir=workflow_dir,
        run_dir=run_dir,
        state=result.state,
    )
    return SimpleNamespace(
        provider=provider,
        result=result,
        workflow_pkg=workflow_pkg,
        task_dir=task_dir,
        workflow_dir=workflow_dir,
        run_dir=run_dir,
        publish_context=publish_context,
        source_snapshot=source_snapshot,
    )


def _install_repo_workflow_and_eval_to_refined_workflow_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
        "workflow_and_eval_to_refined_workflow_package",
        "release_candidate_to_go_no_go",
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
    runtime_tests_root = root / "tests" / "runtime"
    runtime_tests_root.mkdir(parents=True, exist_ok=True)
    (runtime_tests_root / "test_release_candidate_to_go_no_go.py").write_text(
        (REPO_ROOT / "tests" / "runtime" / "test_release_candidate_to_go_no_go.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _write_refinement_evidence(root: Path) -> dict[str, str]:
    evidence_root = root / ".autoloop" / "evals"
    evidence_root.mkdir(parents=True, exist_ok=True)
    summary_path = evidence_root / "release_go_no_go_eval_summary.json"
    findings_path = evidence_root / "release_go_no_go_eval_findings.md"
    failure_modes_path = evidence_root / "release_go_no_go_failure_modes.md"
    summary_path.write_text(
        json.dumps(
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "summary": "Rollback-gap handling stayed too implicit in the assessment prompt.",
                "dominant_failure_mode": "rollback_gap_hidden",
                "recommended_refinement_scope": [PROMPT_RELATIVE_PATH, DOC_RELATIVE_PATH],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    findings_path.write_text(
        "\n".join(
            (
                "# Evaluation Findings",
                "",
                "- The workflow packaged the release decision well, but rollback-gap handling stayed too implicit.",
                "- The strongest improvement pressure is in the assessment prompt and the workflow doc that explains the decision boundary.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    failure_modes_path.write_text(
        "\n".join(
            (
                "# Failure Modes",
                "",
                "- `rollback_gap_hidden`: rollback readiness gaps were not made explicit early enough.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "evaluation_summary_path": ".autoloop/evals/release_go_no_go_eval_summary.json",
        "evaluation_findings_path": ".autoloop/evals/release_go_no_go_eval_findings.md",
        "failure_modes_path": ".autoloop/evals/release_go_no_go_failure_modes.md",
    }


def _write_optimization_refinement_evidence(root: Path) -> str:
    evidence_root = root / ".autoloop" / "optimization"
    evidence_root.mkdir(parents=True, exist_ok=True)
    path = evidence_root / "release_go_no_go_optimization_refinement_evidence.json"
    path.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_refinement_evidence/v1",
                "source_path": None,
                "target_workflow_id": "release_candidate_to_go_no_go",
                "evidence_entries": [
                    {
                        "kind": "step_optimization_priority_report",
                        "path": "step_optimization_priority_report.json",
                        "summary": "Assessment is the highest-leverage optimization target.",
                        "handling": "Candidate only; validate before materializing workflow changes.",
                    },
                    {
                        "kind": "token_optimization_candidates",
                        "path": "token_optimization_candidates.json",
                        "summary": "Token candidates stay candidate-only until semantics are validated.",
                        "handling": "Candidate only; validate before materializing workflow changes.",
                    },
                    {
                        "kind": "adversarial_case_candidates",
                        "path": "adversarial_case_candidates.json",
                        "summary": "Adversarial cases should pressure rollback-evidence handling.",
                        "handling": "Candidate only; route through eval-suite authoring before promotion.",
                    },
                    {
                        "kind": "workflow_optimization_scorecard",
                        "path": "workflow_optimization_scorecard.json",
                        "summary": "The optimization scorecard recommends refinement as the next explicit step.",
                        "handling": "Candidate only; validate before materializing workflow changes.",
                    },
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ".autoloop/optimization/release_go_no_go_optimization_refinement_evidence.json"


def _write_candidate_surface(request) -> str:
    candidate_root = request.artifacts.candidate_workflow_surface.path
    baseline_root = request.artifacts.baseline_workflow_surface.path
    shutil.rmtree(candidate_root, ignore_errors=True)
    shutil.copytree(baseline_root, candidate_root)

    candidate_prompt = candidate_root / PROMPT_RELATIVE_PATH
    candidate_doc = candidate_root / DOC_RELATIVE_PATH
    candidate_prompt.write_text(
        candidate_prompt.read_text(encoding="utf-8").rstrip()
        + "\n- Candidate refinement: call out rollback readiness gaps before recommending go.\n",
        encoding="utf-8",
    )
    candidate_doc.write_text(
        candidate_doc.read_text(encoding="utf-8").rstrip()
        + "\n\nCandidate refinement note: the assessment prompt now emphasizes explicit rollback-gap handling before a go recommendation.\n",
        encoding="utf-8",
    )
    request.artifacts.refinement_build_report.write_text(
        "\n".join(
            (
                "# Refinement Build Report",
                "",
                f"- Updated `{PROMPT_RELATIVE_PATH}` inside `candidate_workflow_surface/`.",
                f"- Updated `{DOC_RELATIVE_PATH}` inside `candidate_workflow_surface/`.",
                "- Kept the authoritative selected workflow package unchanged.",
                "- Left candidate overlay validation to the evaluation and publish steps.",
                "",
            )
        )
        + "\n"
    )
    request.artifacts.candidate_diff_summary.write_text(
        "\n".join(
            (
                "# Candidate Diff Summary",
                "",
                f"- `{PROMPT_RELATIVE_PATH}`: make rollback readiness gaps explicit before a go recommendation.",
                f"- `{DOC_RELATIVE_PATH}`: document the refined emphasis and candidate-only publication boundary.",
                "",
            )
        )
        + "\n"
    )
    return "implemented candidate refinement\n"


def _candidate_file_count(surface_root: Path) -> int:
    return sum(1 for path in surface_root.rglob("*") if path.is_file())


def _build_publish_context(
    *,
    root: Path,
    task_dir: Path,
    workflow_dir: Path,
    run_dir: Path,
    state,
) -> Context:
    return Context(
        task_id=TASK_ID,
        run_id=run_dir.name,
        workflow_name="workflow_and_eval_to_refined_workflow_package",
        task_folder=task_dir,
        workflow_folder=workflow_dir,
        run_folder=run_dir,
        package_folder=root / "workflows" / "workflow_and_eval_to_refined_workflow_package",
        state=state,
        session_store=InMemorySessionStore(),
        workflow_params={},
        workflow_invoker=None,
        answer=None,
    )
