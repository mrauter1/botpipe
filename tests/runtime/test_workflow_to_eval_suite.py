from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.compiler import compile_workflow
from core.context import Context
from core.providers.fake import ScriptedLLMProvider
from core.stores import InMemorySessionStore
from runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from runtime.loader import (
    WorkflowDiscoveryError,
    WorkflowParameterError,
    coerce_workflow_parameter_mapping,
    discover_workflow_packages,
    resolve_workflow_reference,
)
from runtime.runner import RunnerOptions, run_workflow_package
from autoloop_optimizer.adaptation import write_selected_workflow_capability_snapshot
from core.primitives import Outcome


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


def test_repo_workflows_namespace_discovers_workflow_to_eval_suite_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "workflow_to_eval_suite" in discovered
    package = discovered["workflow_to_eval_suite"]
    assert package.package_name == "workflow_to_eval_suite"
    assert "workflow-eval-suite" in package.aliases
    assert package.manifest_path == (REPO_ROOT / "workflows" / "workflow_to_eval_suite" / "workflow.toml")


def test_workflow_to_eval_suite_package_compiles_with_explicit_control_contracts(
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_to_eval_suite")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.WorkflowToEvalSuite)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "capture_selected_workflow_contract",
        "frame_evaluation_target",
        "design_eval_cases",
        "package_workflow_eval_suite",
        "publish_workflow_eval_suite",
    )

    frame_step = compiled.steps["frame_evaluation_target"]
    assert frame_step.available_routes == (
        "evaluation_target_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(compiled.route("frame_evaluation_target", "evaluation_target_framed").required_writes) == [
        "frame_evaluation_target.evaluation_request_brief",
        "frame_evaluation_target.evaluation_dimensions",
    ]
    assert frame_step.expected_output_schema is not None

    design_step = compiled.steps["design_eval_cases"]
    assert list(compiled.route("design_eval_cases", "eval_cases_designed").required_writes) == [
        "design_eval_cases.benchmark_case_matrix",
        "design_eval_cases.edge_case_matrix",
        "design_eval_cases.adversarial_case_matrix",
        "design_eval_cases.eval_case_manifest",
        "design_eval_cases.eval_rubric",
    ]
    assert design_step.expected_output_schema is not None

    package_step = compiled.steps["package_workflow_eval_suite"]
    assert list(compiled.route("package_workflow_eval_suite", "workflow_eval_suite_ready").required_writes) == [
        "package_workflow_eval_suite.workflow_eval_suite",
        "package_workflow_eval_suite.workflow_eval_suite_summary",
        "package_workflow_eval_suite.workflow_eval_next_action",
    ]
    assert package_step.expected_output_schema is not None
    assert set(package_step.expected_output_schema["required"]) >= {
        "summary",
        "selected_workflow_name",
        "selected_workflow_entry_step",
        "selected_workflow_parameters_supported",
        "case_count",
        "case_ids",
        "case_kinds",
        "covered_expected_artifacts",
        "authoritative_artifacts",
        "next_action",
        "ready_for_publication",
    }

    publish_step = compiled.steps["publish_workflow_eval_suite"]
    assert publish_step.requires == (
        "capture_selected_workflow_contract.selected_workflow_capability",
        "design_eval_cases.benchmark_case_matrix",
        "design_eval_cases.edge_case_matrix",
        "design_eval_cases.adversarial_case_matrix",
        "design_eval_cases.eval_case_manifest",
        "design_eval_cases.eval_rubric",
        "package_workflow_eval_suite.workflow_eval_suite",
        "package_workflow_eval_suite.workflow_eval_suite_summary",
        "package_workflow_eval_suite.workflow_eval_next_action",
    )


def test_workflow_to_eval_suite_package_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "workflow_to_eval_suite.md").read_text(encoding="utf-8")

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_workflow_to_eval_suite.py",
    ):
        assert required in text


def test_workflow_to_eval_suite_prompt_readme_uses_shared_contract_sections() -> None:
    text = (REPO_ROOT / "workflows" / "workflow_to_eval_suite" / "prompts" / "README.md").read_text(
        encoding="utf-8"
    )

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
        "`evaluation_target_framed`",
        "`eval_cases_designed`",
        "`workflow_eval_suite_ready`",
        "`needs_rework`",
        "`needs_replan`",
        "`frame_producer.md` / `frame_verifier.md`",
        "WorkflowEvalSuitePayload",
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
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "## Evidence",
                "Route guidance for the verifier",
                "Forbidden",
                "`evaluation_request_brief`",
                "`evaluation_dimensions`",
                "`evaluation_target_framed`",
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
                "Do not overwrite `evaluation_request_brief` or `evaluation_dimensions` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`evaluation_target_framed`",
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
                "`benchmark_case_matrix`",
                "`edge_case_matrix`",
                "`adversarial_case_matrix`",
                "`eval_case_manifest`",
                "`eval_rubric`",
                "`eval_cases_designed`",
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
                "Do not overwrite the case-matrix artifacts, `eval_case_manifest`, or `eval_rubric` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`eval_cases_designed`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
        (
            "package_producer.md",
            (
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "## Evidence",
                "Route guidance for the verifier",
                "Forbidden",
                "`workflow_eval_suite`",
                "`workflow_eval_suite_summary`",
                "`workflow_eval_next_action`",
                "`validated_eval_case_manifest.json`",
                "`eval_rubric.md`",
                "`workflow_eval_suite_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "Reserved routes are only",
            ),
        ),
        (
            "package_verifier.md",
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
                "Do not overwrite `workflow_eval_suite`, `workflow_eval_suite_summary`, or `workflow_eval_next_action` during verification.",
                "Do not create `validated_eval_case_manifest.json` or `workflow_eval_suite_receipt.json` in this step.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`workflow_eval_suite_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`validated_eval_case_manifest.json`",
                "`eval_rubric.md`",
                "Use reserved routes only",
            ),
        ),
    ),
)
def test_workflow_to_eval_suite_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (REPO_ROOT / "workflows" / "workflow_to_eval_suite" / "prompts" / prompt_name).read_text(
        encoding="utf-8"
    )

    for marker in required_markers:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"


def test_workflow_to_eval_suite_package_rejects_blank_selected_workflow(tmp_path: Path) -> None:
    _install_repo_workflow_to_eval_suite_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "workflow_to_eval_suite").parameters_cls

    with pytest.raises(WorkflowParameterError, match="value must be non-empty"):
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "selected_workflow": "   ",
                "task_title": "Release readiness evaluation suite",
            },
        )


def test_workflow_to_eval_suite_package_normalizes_repeatable_inputs(tmp_path: Path) -> None:
    _install_repo_workflow_to_eval_suite_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "workflow_to_eval_suite").parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "selected_workflow": " release_candidate_to_go_no_go ",
            "task_title": " Release readiness evaluation suite ",
            "sponsor_role": " Engineering Productivity ",
            "desired_outcome": " ",
            "constraints": [
                " keep runtime control narrow ",
                "",
                "keep runtime control narrow",
                "Stop at suite publication.",
            ],
            "evidence_expectations": [
                " publish a validated manifest ",
                "",
                "publish a validated manifest",
                "Cover benchmark, edge, and adversarial pressure.",
            ],
        },
    )

    assert normalized == {
        "constraints": [
            "keep runtime control narrow",
            "Stop at suite publication.",
        ],
        "desired_outcome": None,
        "evidence_expectations": [
            "publish a validated manifest",
            "Cover benchmark, edge, and adversarial pressure.",
        ],
        "selected_workflow": "release_candidate_to_go_no_go",
        "sponsor_role": "Engineering Productivity",
        "task_title": "Release readiness evaluation suite",
    }


def test_workflow_to_eval_suite_bootstrap_reads_typed_ctx_params(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_to_eval_suite")
    parameters_cls = resolve_workflow_reference(REPO_ROOT, "workflow_to_eval_suite").parameters_cls
    assert parameters_cls is not None
    typed_params = parameters_cls.model_validate(
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "selected_workflow": " release_candidate_to_go_no_go ",
                "task_title": " Release readiness evaluation suite ",
                "sponsor_role": " Engineering Productivity ",
                "desired_outcome": " ",
                "constraints": [
                    " keep runtime control narrow ",
                    "",
                    "keep runtime control narrow",
                    "Stop at suite publication.",
                ],
                "evidence_expectations": [
                    " publish a validated manifest ",
                    "",
                    "publish a validated manifest",
                    "Cover benchmark, edge, and adversarial pressure.",
                ],
            },
        )
    )

    task_folder = tmp_path / ".autoloop" / "tasks" / "typed-bootstrap-task"
    workflow_folder = task_folder / "wf_workflow_to_eval_suite"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Typed bootstrap request.\n", encoding="utf-8")

    ctx = Context(
        task_id="typed-bootstrap-task",
        run_id="run-1",
        workflow_name="workflow_to_eval_suite",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "workflow_to_eval_suite",
        state=workflow_pkg.WorkflowToEvalSuite.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={},
    )

    next_state, event = workflow_pkg.WorkflowToEvalSuite.on_bootstrap(
        workflow_pkg.WorkflowToEvalSuite.State(),
        ctx,
    )

    assert event.tag == "inputs_prepared"
    assert next_state.selected_workflow_reference == "release_candidate_to_go_no_go"
    assert next_state.task_title == "Release readiness evaluation suite"
    assert next_state.sponsor_role == "Engineering Productivity"
    assert next_state.desired_outcome is None
    assert next_state.constraints == [
        "keep runtime control narrow",
        "Stop at suite publication.",
    ]
    assert next_state.evidence_expectations == [
        "publish a validated manifest",
        "Cover benchmark, edge, and adversarial pressure.",
    ]

    invocation_contract = json.loads((workflow_folder / "invocation_contract.json").read_text(encoding="utf-8"))
    assert invocation_contract["selected_workflow_reference"] == "release_candidate_to_go_no_go"
    assert invocation_contract["task_title"] == "Release readiness evaluation suite"
    assert invocation_contract["desired_outcome"] is None
    assert invocation_contract["constraints"] == next_state.constraints
    assert invocation_contract["evidence_expectations"] == next_state.evidence_expectations


def test_workflow_to_eval_suite_package_runs_and_publishes_terminal_eval_artifacts(
    tmp_path: Path,
) -> None:
    _install_repo_workflow_to_eval_suite_package(tmp_path)

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.evaluation_request_brief.write_text(
                    "\n".join(
                        (
                            "# Evaluation Request Brief",
                            "",
                            "Selected workflow: `release_candidate_to_go_no_go`.",
                            "Task: publish a reusable eval suite for release-readiness reviews without executing the selected workflow.",
                            "Sponsor: engineering productivity.",
                            "Terminal outcome: publish the suite package, summary, validated manifest, and receipt.",
                            "Why this building block matters: the release workflow already exists, but its evaluation pressure should survive handoff as durable artifacts.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.evaluation_dimensions.write_text(
                    "\n".join(
                        (
                            "# Evaluation Dimensions",
                            "",
                            "- Benchmark cases should confirm the workflow can package a routine release decision cleanly.",
                            "- Edge cases should pressure incomplete release context and ensure blocker handling stays explicit.",
                            "- Adversarial cases should pressure rollback and operational-risk handling.",
                            "- The suite must exercise selected-workflow artifacts such as `decision_summary`, `release_decision_package`, `blocking_issues`, `risk_register`, and `rollback_readiness`.",
                            "- Publication must stop before any downstream selected-workflow execution.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "framed evaluation target\n",
            )[2],
            lambda request: (
                request.artifacts.benchmark_case_matrix.write_text(
                    "\n".join(
                        (
                            "# Benchmark Case Matrix",
                            "",
                            "| Case ID | Pressure | Expected Artifacts | Why It Matters |",
                            "| --- | --- | --- | --- |",
                            "| `baseline_release_gate` | Routine release with complete evidence | `decision_summary`, `release_decision_package` | Confirms the workflow can publish a normal release decision package cleanly. |",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.edge_case_matrix.write_text(
                    "\n".join(
                        (
                            "# Edge Case Matrix",
                            "",
                            "| Case ID | Pressure | Expected Artifacts | Why It Matters |",
                            "| --- | --- | --- | --- |",
                            "| `edge_missing_owner` | Release context is complete except release ownership is unclear | `blocking_issues`, `risk_register` | Confirms ownership ambiguity is surfaced as a blocker rather than ignored. |",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.adversarial_case_matrix.write_text(
                    "\n".join(
                        (
                            "# Adversarial Case Matrix",
                            "",
                            "| Case ID | Pressure | Expected Artifacts | Why It Matters |",
                            "| --- | --- | --- | --- |",
                            "| `adversarial_rollback_gap` | Rollback evidence is weak while pressure to ship is high | `release_decision_package`, `rollback_readiness` | Confirms rollback gaps stay visible under pressure. |",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.eval_case_manifest.write_text(
                    json.dumps(
                        {
                            "cases": [
                                {
                                    "case_id": "baseline_release_gate",
                                    "case_kind": "benchmark",
                                    "expected_artifacts": [
                                        "release_decision_package",
                                        "decision_summary",
                                    ],
                                    "prompt": "Assess a routine release candidate with complete evidence and publish the release decision package.",
                                    "workflow_parameters": {"release_name": "2026.04"},
                                },
                                {
                                    "case_id": "edge_missing_owner",
                                    "case_kind": "edge",
                                    "expected_artifacts": ["risk_register", "blocking_issues"],
                                    "prompt": "Assess a release candidate where ownership is unclear but the team still wants a decision.",
                                    "workflow_parameters": {"release_name": "2026.04-edge"},
                                },
                                {
                                    "case_id": "adversarial_rollback_gap",
                                    "case_kind": "adversarial",
                                    "expected_artifacts": [
                                        "release_decision_package",
                                        "rollback_readiness",
                                    ],
                                    "prompt": "Assess a release candidate where rollback evidence is weak and shipping pressure is high.",
                                    "workflow_parameters": {"release_name": "2026.04-adversarial"},
                                },
                            ]
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                request.artifacts.eval_rubric.write_text(
                    "\n".join(
                        (
                            "# Eval Rubric",
                            "",
                            "- Pass when the workflow produces the expected artifacts, keeps blockers explicit, and preserves rollback reasoning.",
                            "- Fail when expected artifacts are missing, blockers are hidden, or rollback risk is glossed over.",
                            "- Treat missing artifact publication or unsupported workflow-parameter assumptions as hard failures.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "designed eval cases\n",
            )[5],
            lambda request: (
                request.artifacts.workflow_eval_suite.write_text(
                    "\n".join(
                        (
                            "# Workflow Eval Suite",
                            "",
                            "Selected workflow: `release_candidate_to_go_no_go`.",
                            "Selected workflow entry step: `bootstrap`.",
                            "This suite covers benchmark, edge, and adversarial release-readiness cases.",
                            "Authoritative artifacts after publication: `workflow_eval_suite.md`, `workflow_eval_suite_summary.json`, `workflow_eval_next_action.md`, `validated_eval_case_manifest.json`, and `eval_rubric.md`.",
                            "Use `validated_eval_case_manifest.json` as the authoritative manifest once publication completes.",
                            "Use `eval_rubric.md` to score downstream evaluation runs.",
                            "This run stops at suite publication and does not execute `release_candidate_to_go_no_go`.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.workflow_eval_suite_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "workflow_eval_suite",
                                "workflow_eval_suite_summary",
                                "workflow_eval_next_action",
                                "validated_eval_case_manifest",
                                "eval_rubric",
                            ],
                            "case_count": 3,
                            "case_ids": [
                                "baseline_release_gate",
                                "edge_missing_owner",
                                "adversarial_rollback_gap",
                            ],
                            "case_kinds": ["benchmark", "edge", "adversarial"],
                            "covered_expected_artifacts": [
                                "blocking_issues",
                                "decision_summary",
                                "release_decision_package",
                                "risk_register",
                                "rollback_readiness",
                            ],
                            "next_action": "Run the evaluation harness against release_candidate_to_go_no_go using validated_eval_case_manifest.json and eval_rubric.md; keep this published suite attached to the downstream evaluation run.",
                            "ready_for_publication": True,
                            "selected_workflow_entry_step": "bootstrap",
                            "selected_workflow_name": "release_candidate_to_go_no_go",
                            "selected_workflow_parameters_supported": True,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                request.artifacts.workflow_eval_next_action.write_text(
                    "\n".join(
                        (
                            "# Workflow Eval Next Action",
                            "",
                            "1. Run the evaluation harness against `release_candidate_to_go_no_go`.",
                            "2. Use `validated_eval_case_manifest.json` as the authoritative case manifest.",
                            "3. Score the downstream run with `eval_rubric.md` and keep this published suite attached to the evaluation evidence package.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "packaged eval suite\n",
            )[3],
        ],
        verifier_turns=[
            Outcome(
                raw_output="evaluation target framed\n",
                tag="evaluation_target_framed",
                payload={
                    "summary": "The selected workflow and evaluation dimensions are explicit enough for case design.",
                    "authoritative_artifacts": [
                        "evaluation_request_brief",
                        "evaluation_dimensions",
                    ],
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "evaluation_axes": [
                        "artifact completeness",
                        "blocker handling",
                        "rollback safety",
                    ],
                },
            ),
            Outcome(
                raw_output="eval cases designed\n",
                tag="eval_cases_designed",
                payload={
                    "summary": "The suite covers benchmark, edge, and adversarial release-readiness pressure.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "case_ids": [
                        "baseline_release_gate",
                        "edge_missing_owner",
                        "adversarial_rollback_gap",
                    ],
                    "case_kinds": ["benchmark", "edge", "adversarial"],
                    "covered_expected_artifacts": [
                        "blocking_issues",
                        "decision_summary",
                        "release_decision_package",
                        "risk_register",
                        "rollback_readiness",
                    ],
                },
            ),
            Outcome(
                raw_output="workflow eval suite ready\n",
                tag="workflow_eval_suite_ready",
                payload={
                    "summary": "The terminal suite package, summary, and next action are aligned for publication.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "selected_workflow_entry_step": "bootstrap",
                    "selected_workflow_parameters_supported": True,
                    "case_count": 3,
                    "case_ids": [
                        "baseline_release_gate",
                        "edge_missing_owner",
                        "adversarial_rollback_gap",
                    ],
                    "case_kinds": ["benchmark", "edge", "adversarial"],
                    "covered_expected_artifacts": [
                        "blocking_issues",
                        "decision_summary",
                        "release_decision_package",
                        "risk_register",
                        "rollback_readiness",
                    ],
                    "authoritative_artifacts": [
                        "workflow_eval_suite",
                        "workflow_eval_suite_summary",
                        "workflow_eval_next_action",
                        "validated_eval_case_manifest",
                        "eval_rubric",
                    ],
                    "next_action": "Run the evaluation harness against release_candidate_to_go_no_go using validated_eval_case_manifest.json and eval_rubric.md; keep this published suite attached to the downstream evaluation run.",
                    "ready_for_publication": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "workflow_to_eval_suite",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="workflow-eval-suite-task",
            message="Author an evaluation suite for the release go/no-go workflow.",
            workflow_params={
                "selected_workflow": "release_candidate_to_go_no_go",
                "task_title": "Release readiness evaluation suite",
                "sponsor_role": "engineering productivity",
                "desired_outcome": "Publish a reusable eval suite for workflow quality gating.",
                "constraints": [
                    "Keep runtime control narrow.",
                    "Stop at suite publication.",
                ],
                "evidence_expectations": [
                    "Need benchmark, edge, and adversarial coverage.",
                    "Need a validated manifest and downstream next action.",
                ],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "workflow-eval-suite-task"
    workflow_dir = task_dir / "wf_workflow_to_eval_suite"
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    selected_capability = json.loads((workflow_dir / "selected_workflow_capability.json").read_text(encoding="utf-8"))
    suite_summary = json.loads((workflow_dir / "workflow_eval_suite_summary.json").read_text(encoding="utf-8"))
    validated_manifest = json.loads((workflow_dir / "validated_eval_case_manifest.json").read_text(encoding="utf-8"))
    suite_receipt = json.loads((workflow_dir / "workflow_eval_suite_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert (workflow_dir / "selected_workflow_capability.json").exists()
    assert (workflow_dir / "evaluation_request_brief.md").exists()
    assert (workflow_dir / "evaluation_dimensions.md").exists()
    assert (workflow_dir / "benchmark_case_matrix.md").exists()
    assert (workflow_dir / "edge_case_matrix.md").exists()
    assert (workflow_dir / "adversarial_case_matrix.md").exists()
    assert (workflow_dir / "eval_case_manifest.json").exists()
    assert (workflow_dir / "eval_rubric.md").exists()
    assert (workflow_dir / "workflow_eval_suite.md").exists()
    assert (workflow_dir / "workflow_eval_suite_summary.json").exists()
    assert (workflow_dir / "workflow_eval_next_action.md").exists()
    assert (workflow_dir / "validated_eval_case_manifest.json").exists()
    assert (workflow_dir / "workflow_eval_suite_receipt.json").exists()
    assert not (task_dir / "wf_release_candidate_to_go_no_go").exists()
    assert invocation_contract == {
        "constraints": [
            "Keep runtime control narrow.",
            "Stop at suite publication.",
        ],
        "desired_outcome": "Publish a reusable eval suite for workflow quality gating.",
        "evidence_expectations": [
            "Need benchmark, edge, and adversarial coverage.",
            "Need a validated manifest and downstream next action.",
        ],
        "message": "Author an evaluation suite for the release go/no-go workflow.\n",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "selected_workflow_reference": "release_candidate_to_go_no_go",
        "sponsor_role": "engineering productivity",
        "task_id": "workflow-eval-suite-task",
        "task_title": "Release readiness evaluation suite",
        "workflow_name": "workflow_to_eval_suite",
    }
    assert selected_capability["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert (
        selected_capability["selected_workflow_capability"]["workflow_name"]
        == validated_manifest["selected_workflow_name"]
    )
    assert selected_capability["selected_workflow_capability"]["entry_step_name"] == "bootstrap"
    assert selected_capability["selected_workflow_capability"]["parameters_supported"] is True
    assert {
        entry["name"] for entry in selected_capability["selected_workflow_capability"]["parameters"]
    } >= {"release_name", "deployment_environment", "release_owner"}
    assert suite_summary == {
        "authoritative_artifacts": [
            "workflow_eval_suite",
            "workflow_eval_suite_summary",
            "workflow_eval_next_action",
            "validated_eval_case_manifest",
            "eval_rubric",
        ],
        "case_count": 3,
        "case_ids": [
            "baseline_release_gate",
            "edge_missing_owner",
            "adversarial_rollback_gap",
        ],
        "case_kinds": ["benchmark", "edge", "adversarial"],
        "covered_expected_artifacts": [
            "blocking_issues",
            "decision_summary",
            "release_decision_package",
            "risk_register",
            "rollback_readiness",
        ],
        "next_action": "Run the evaluation harness against release_candidate_to_go_no_go using validated_eval_case_manifest.json and eval_rubric.md; keep this published suite attached to the downstream evaluation run.",
        "ready_for_publication": True,
        "selected_workflow_entry_step": "bootstrap",
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "selected_workflow_parameters_supported": True,
    }
    assert validated_manifest == {
        "case_count": 3,
        "case_ids": [
            "baseline_release_gate",
            "edge_missing_owner",
            "adversarial_rollback_gap",
        ],
        "case_kinds": ["benchmark", "edge", "adversarial"],
        "repo_root": str(tmp_path.resolve()),
        "run_id": run_dir.name,
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "task_id": "workflow-eval-suite-task",
        "validated_cases": [
            {
                "case_id": "baseline_release_gate",
                "case_kind": "benchmark",
                "expected_artifacts": [
                    "decision_summary",
                    "release_decision_package",
                ],
                "prompt": "Assess a routine release candidate with complete evidence and publish the release decision package.",
                "workflow_parameters": {
                    "deployment_environment": "production",
                    "evidence_paths": [],
                    "release_name": "2026.04",
                    "release_owner": None,
                    "target_date": None,
                },
            },
            {
                "case_id": "edge_missing_owner",
                "case_kind": "edge",
                "expected_artifacts": [
                    "blocking_issues",
                    "risk_register",
                ],
                "prompt": "Assess a release candidate where ownership is unclear but the team still wants a decision.",
                "workflow_parameters": {
                    "deployment_environment": "production",
                    "evidence_paths": [],
                    "release_name": "2026.04-edge",
                    "release_owner": None,
                    "target_date": None,
                },
            },
            {
                "case_id": "adversarial_rollback_gap",
                "case_kind": "adversarial",
                "expected_artifacts": [
                    "release_decision_package",
                    "rollback_readiness",
                ],
                "prompt": "Assess a release candidate where rollback evidence is weak and shipping pressure is high.",
                "workflow_parameters": {
                    "deployment_environment": "production",
                    "evidence_paths": [],
                    "release_name": "2026.04-adversarial",
                    "release_owner": None,
                    "target_date": None,
                },
            },
        ],
        "workflow_name": "workflow_to_eval_suite",
    }
    assert suite_receipt == {
        "adversarial_case_matrix": str(workflow_dir / "adversarial_case_matrix.md"),
        "authoritative_artifacts": [
            "workflow_eval_suite",
            "workflow_eval_suite_summary",
            "workflow_eval_next_action",
            "validated_eval_case_manifest",
            "eval_rubric",
        ],
        "benchmark_case_matrix": str(workflow_dir / "benchmark_case_matrix.md"),
        "case_count": 3,
        "case_ids": [
            "baseline_release_gate",
            "edge_missing_owner",
            "adversarial_rollback_gap",
        ],
        "case_kinds": ["benchmark", "edge", "adversarial"],
        "covered_expected_artifacts": [
            "blocking_issues",
            "decision_summary",
            "release_decision_package",
            "risk_register",
            "rollback_readiness",
        ],
        "desired_outcome": "Publish a reusable eval suite for workflow quality gating.",
        "edge_case_matrix": str(workflow_dir / "edge_case_matrix.md"),
        "eval_case_manifest": str(workflow_dir / "eval_case_manifest.json"),
        "eval_rubric": str(workflow_dir / "eval_rubric.md"),
        "next_action": "Run the evaluation harness against release_candidate_to_go_no_go using validated_eval_case_manifest.json and eval_rubric.md; keep this published suite attached to the downstream evaluation run.",
        "published": True,
        "selected_workflow_capability": str(workflow_dir / "selected_workflow_capability.json"),
        "selected_workflow_entry_step": "bootstrap",
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "selected_workflow_parameters_supported": True,
        "selected_workflow_reference": "release_candidate_to_go_no_go",
        "sponsor_role": "engineering productivity",
        "task_title": "Release readiness evaluation suite",
        "validated_eval_case_manifest": str(workflow_dir / "validated_eval_case_manifest.json"),
        "workflow_eval_next_action": str(workflow_dir / "workflow_eval_next_action.md"),
        "workflow_eval_suite": str(workflow_dir / "workflow_eval_suite.md"),
        "workflow_eval_suite_summary": str(workflow_dir / "workflow_eval_suite_summary.json"),
        "workflow_name": "workflow_to_eval_suite",
    }
    assert "validated_eval_case_manifest.json" in (workflow_dir / "workflow_eval_suite.md").read_text(encoding="utf-8")
    assert "eval_rubric.md" in (workflow_dir / "workflow_eval_suite.md").read_text(encoding="utf-8")
    assert "validated_eval_case_manifest.json" in (workflow_dir / "workflow_eval_next_action.md").read_text(
        encoding="utf-8"
    )
    assert "eval_rubric.md" in (workflow_dir / "workflow_eval_next_action.md").read_text(encoding="utf-8")
    assert [call.step_name for call in provider.calls] == [
        "frame_evaluation_target",
        "frame_evaluation_target",
        "design_eval_cases",
        "design_eval_cases",
        "package_workflow_eval_suite",
        "package_workflow_eval_suite",
    ]
    assert list(provider.calls[1].route_required_writes["evaluation_target_framed"]) == [
        "frame_evaluation_target.evaluation_request_brief",
        "frame_evaluation_target.evaluation_dimensions",
    ]
    assert provider.calls[3].available_routes == (
        "eval_cases_designed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(provider.calls[5].route_required_writes["workflow_eval_suite_ready"]) == [
        "package_workflow_eval_suite.workflow_eval_suite",
        "package_workflow_eval_suite.workflow_eval_suite_summary",
        "package_workflow_eval_suite.workflow_eval_next_action",
    ]


def test_workflow_to_eval_suite_package_needs_rework_payload_updates_state(
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_to_eval_suite")
    state = workflow_pkg.WorkflowToEvalSuite.State(
        selected_workflow_reference="release_candidate_to_go_no_go",
        selected_workflow_name="release_candidate_to_go_no_go",
        task_title="Release readiness evaluation suite",
    )

    next_state = workflow_pkg.WorkflowToEvalSuite.on_package_workflow_eval_suite(
        state,
        Outcome(
            raw_output="package needs local repair\n",
            tag="needs_rework",
            payload={
                "summary": "The suite boundary still holds, but the package artifacts need local repair.",
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "selected_workflow_entry_step": "bootstrap",
                "selected_workflow_parameters_supported": True,
                "case_count": 3,
                "case_ids": [
                    "baseline_release_gate",
                    "edge_missing_owner",
                    "adversarial_rollback_gap",
                ],
                "case_kinds": ["benchmark", "edge", "adversarial"],
                "covered_expected_artifacts": [
                    "blocking_issues",
                    "decision_summary",
                    "release_decision_package",
                    "risk_register",
                    "rollback_readiness",
                ],
                "authoritative_artifacts": [
                    "workflow_eval_suite",
                    "workflow_eval_suite_summary",
                    "workflow_eval_next_action",
                    "validated_eval_case_manifest",
                    "eval_rubric",
                ],
                "next_action": "Repair the package artifacts and rerun packaging.",
                "ready_for_publication": False,
            },
        ),
        None,
    )

    assert next_state.packaging_status == "needs_rework"
    assert next_state.selected_workflow_name == "release_candidate_to_go_no_go"
    assert next_state.case_ids == [
        "baseline_release_gate",
        "edge_missing_owner",
        "adversarial_rollback_gap",
    ]
    assert next_state.case_kinds == ["benchmark", "edge", "adversarial"]


@pytest.mark.parametrize(
    "missing_field",
    (
        "selected_workflow_parameters_supported",
        "case_count",
        "ready_for_publication",
    ),
)
def test_workflow_to_eval_suite_package_validator_rejects_missing_required_package_fields(
    monkeypatch,
    missing_field: str,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_to_eval_suite")
    compiled = compile_workflow(workflow_pkg.WorkflowToEvalSuite)
    package_step = compiled.steps["package_workflow_eval_suite"]
    payload = {
        "summary": "The suite package is aligned and ready for publication.",
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "selected_workflow_entry_step": "bootstrap",
        "selected_workflow_parameters_supported": True,
        "case_count": 3,
        "case_ids": [
            "baseline_release_gate",
            "edge_missing_owner",
            "adversarial_rollback_gap",
        ],
        "case_kinds": ["benchmark", "edge", "adversarial"],
        "covered_expected_artifacts": [
            "blocking_issues",
            "decision_summary",
            "release_decision_package",
            "risk_register",
            "rollback_readiness",
        ],
        "authoritative_artifacts": [
            "workflow_eval_suite",
            "workflow_eval_suite_summary",
            "workflow_eval_next_action",
            "validated_eval_case_manifest",
            "eval_rubric",
        ],
        "next_action": "Run the evaluation harness with the published suite.",
        "ready_for_publication": True,
    }
    payload.pop(missing_field)

    with pytest.raises(ValidationError, match=missing_field):
        package_step.expected_output_validator(payload)


def test_workflow_to_eval_suite_publish_rejects_invalid_selected_workflow_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_eval_suite_test_context(
        tmp_path,
        monkeypatch,
        selected_workflow_reference="unknown_workflow",
    )

    with pytest.raises(WorkflowDiscoveryError, match="unknown workflow"):
        workflow_pkg.WorkflowToEvalSuite.on_publish_workflow_eval_suite(state, ctx)


def test_workflow_to_eval_suite_publish_rejects_validated_manifest_missing_typed_required_field(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_eval_suite_test_context(tmp_path, monkeypatch)
    workflow_module = importlib.import_module("workflows.workflow_to_eval_suite.workflow")

    def _write_invalid_validated_manifest(*_args, **_kwargs):
        path = ctx.workflow_folder / "validated_eval_case_manifest.json"
        path.write_text(
            json.dumps(
                {
                    "repo_root": str(REPO_ROOT),
                    "run_id": ctx.run_id,
                    "selected_workflow_name": state.selected_workflow_name,
                    "task_id": ctx.task_id,
                    "workflow_name": ctx.workflow_name,
                    "case_count": 3,
                    "case_kinds": ["benchmark", "edge", "adversarial"],
                    "validated_cases": [
                        {
                            "case_id": "baseline_release_gate",
                            "case_kind": "benchmark",
                            "expected_artifacts": [
                                "release_decision_package",
                                "decision_summary",
                            ],
                            "prompt": "Assess a routine release candidate with complete evidence and publish the release decision package.",
                            "workflow_parameters": {"release_name": "2026.04"},
                        }
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    monkeypatch.setattr(
        workflow_module,
        "write_validated_eval_case_manifest",
        _write_invalid_validated_manifest,
    )

    with pytest.raises(ValidationError, match="case_ids"):
        workflow_pkg.WorkflowToEvalSuite.on_publish_workflow_eval_suite(state, ctx)


def test_workflow_to_eval_suite_publish_rejects_summary_selected_workflow_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_eval_suite_test_context(
        tmp_path,
        monkeypatch,
        summary_overrides={"selected_workflow_name": "incident_to_hardening_program"},
    )

    with pytest.raises(
        ValueError,
        match="workflow_eval_suite_summary.json selected_workflow_name must match selected_workflow_capability.json",
    ):
        workflow_pkg.WorkflowToEvalSuite.on_publish_workflow_eval_suite(state, ctx)


def test_workflow_to_eval_suite_publish_rejects_summary_missing_typed_required_field(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_eval_suite_test_context(
        tmp_path,
        monkeypatch,
        summary_overrides={"case_ids": []},
    )
    payload = json.loads((ctx.workflow_folder / "workflow_eval_suite_summary.json").read_text(encoding="utf-8"))
    payload.pop("case_ids")
    (ctx.workflow_folder / "workflow_eval_suite_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="case_ids"):
        workflow_pkg.WorkflowToEvalSuite.on_publish_workflow_eval_suite(state, ctx)


def test_workflow_to_eval_suite_publish_rejects_malformed_case_kind(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_eval_suite_test_context(
        tmp_path,
        monkeypatch,
        manifest_overrides={
            "cases": [
                {
                    "case_id": "baseline_release_gate",
                    "case_kind": "smoke",
                    "expected_artifacts": [
                        "release_decision_package",
                        "decision_summary",
                    ],
                    "prompt": "Assess a routine release candidate with complete evidence and publish the release decision package.",
                    "workflow_parameters": {"release_name": "2026.04"},
                },
                {
                    "case_id": "edge_missing_owner",
                    "case_kind": "edge",
                    "expected_artifacts": ["risk_register", "blocking_issues"],
                    "prompt": "Assess a release candidate where ownership is unclear but the team still wants a decision.",
                    "workflow_parameters": {"release_name": "2026.04-edge"},
                },
                {
                    "case_id": "adversarial_rollback_gap",
                    "case_kind": "adversarial",
                    "expected_artifacts": [
                        "release_decision_package",
                        "rollback_readiness",
                    ],
                    "prompt": "Assess a release candidate where rollback evidence is weak and shipping pressure is high.",
                    "workflow_parameters": {"release_name": "2026.04-adversarial"},
                },
            ]
        },
    )

    with pytest.raises(ValueError, match="unsupported case_kind"):
        workflow_pkg.WorkflowToEvalSuite.on_publish_workflow_eval_suite(state, ctx)


def test_workflow_to_eval_suite_publish_rejects_missing_required_case_kind(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_eval_suite_test_context(
        tmp_path,
        monkeypatch,
        manifest_overrides={
            "cases": [
                {
                    "case_id": "baseline_release_gate",
                    "case_kind": "benchmark",
                    "expected_artifacts": [
                        "release_decision_package",
                        "decision_summary",
                    ],
                    "prompt": "Assess a routine release candidate with complete evidence and publish the release decision package.",
                    "workflow_parameters": {"release_name": "2026.04"},
                },
                {
                    "case_id": "edge_missing_owner",
                    "case_kind": "edge",
                    "expected_artifacts": ["risk_register", "blocking_issues"],
                    "prompt": "Assess a release candidate where ownership is unclear but the team still wants a decision.",
                    "workflow_parameters": {"release_name": "2026.04-edge"},
                },
            ]
        },
    )

    with pytest.raises(
        ValueError,
        match="validated_eval_case_manifest.json case_kinds must include benchmark, edge, and adversarial",
    ):
        workflow_pkg.WorkflowToEvalSuite.on_publish_workflow_eval_suite(state, ctx)


def test_workflow_to_eval_suite_publish_rejects_duplicate_case_ids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_eval_suite_test_context(
        tmp_path,
        monkeypatch,
        manifest_overrides={
            "cases": [
                {
                    "case_id": "duplicate_case",
                    "case_kind": "benchmark",
                    "expected_artifacts": [
                        "release_decision_package",
                        "decision_summary",
                    ],
                    "prompt": "Assess a routine release candidate with complete evidence and publish the release decision package.",
                    "workflow_parameters": {"release_name": "2026.04"},
                },
                {
                    "case_id": "duplicate_case",
                    "case_kind": "edge",
                    "expected_artifacts": ["risk_register", "blocking_issues"],
                    "prompt": "Assess a release candidate where ownership is unclear but the team still wants a decision.",
                    "workflow_parameters": {"release_name": "2026.04-edge"},
                },
                {
                    "case_id": "adversarial_rollback_gap",
                    "case_kind": "adversarial",
                    "expected_artifacts": [
                        "release_decision_package",
                        "rollback_readiness",
                    ],
                    "prompt": "Assess a release candidate where rollback evidence is weak and shipping pressure is high.",
                    "workflow_parameters": {"release_name": "2026.04-adversarial"},
                },
            ]
        },
    )

    with pytest.raises(ValueError, match="repeats case_id 'duplicate_case'"):
        workflow_pkg.WorkflowToEvalSuite.on_publish_workflow_eval_suite(state, ctx)


def test_workflow_to_eval_suite_publish_rejects_invalid_case_parameters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_eval_suite_test_context(
        tmp_path,
        monkeypatch,
        manifest_overrides={
            "cases": [
                {
                    "case_id": "baseline_release_gate",
                    "case_kind": "benchmark",
                    "expected_artifacts": [
                        "release_decision_package",
                        "decision_summary",
                    ],
                    "prompt": "Assess a routine release candidate with complete evidence and publish the release decision package.",
                    "workflow_parameters": {
                        "release_name": "2026.04",
                        "unexpected": "value",
                    },
                },
                {
                    "case_id": "edge_missing_owner",
                    "case_kind": "edge",
                    "expected_artifacts": ["risk_register", "blocking_issues"],
                    "prompt": "Assess a release candidate where ownership is unclear but the team still wants a decision.",
                    "workflow_parameters": {"release_name": "2026.04-edge"},
                },
                {
                    "case_id": "adversarial_rollback_gap",
                    "case_kind": "adversarial",
                    "expected_artifacts": [
                        "release_decision_package",
                        "rollback_readiness",
                    ],
                    "prompt": "Assess a release candidate where rollback evidence is weak and shipping pressure is high.",
                    "workflow_parameters": {"release_name": "2026.04-adversarial"},
                },
            ]
        },
    )

    with pytest.raises(WorkflowParameterError, match=r"unknown workflow parameter 'unexpected'"):
        workflow_pkg.WorkflowToEvalSuite.on_publish_workflow_eval_suite(state, ctx)


def test_workflow_to_eval_suite_publish_rejects_unknown_expected_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_eval_suite_test_context(
        tmp_path,
        monkeypatch,
        manifest_overrides={
            "cases": [
                {
                    "case_id": "baseline_release_gate",
                    "case_kind": "benchmark",
                    "expected_artifacts": ["not_declared"],
                    "prompt": "Assess a routine release candidate with complete evidence and publish the release decision package.",
                    "workflow_parameters": {"release_name": "2026.04"},
                },
                {
                    "case_id": "edge_missing_owner",
                    "case_kind": "edge",
                    "expected_artifacts": ["risk_register", "blocking_issues"],
                    "prompt": "Assess a release candidate where ownership is unclear but the team still wants a decision.",
                    "workflow_parameters": {"release_name": "2026.04-edge"},
                },
                {
                    "case_id": "adversarial_rollback_gap",
                    "case_kind": "adversarial",
                    "expected_artifacts": [
                        "release_decision_package",
                        "rollback_readiness",
                    ],
                    "prompt": "Assess a release candidate where rollback evidence is weak and shipping pressure is high.",
                    "workflow_parameters": {"release_name": "2026.04-adversarial"},
                },
            ]
        },
    )

    with pytest.raises(ValueError, match="unknown artifact 'not_declared'"):
        workflow_pkg.WorkflowToEvalSuite.on_publish_workflow_eval_suite(state, ctx)


def test_workflow_to_eval_suite_publish_rejects_summary_drift_from_validated_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_eval_suite_test_context(
        tmp_path,
        monkeypatch,
        summary_overrides={
            "case_ids": [
                "baseline_release_gate",
                "edge_missing_owner",
                "unexpected_case",
            ]
        },
    )

    with pytest.raises(ValueError, match="case_ids must match validated_eval_case_manifest.json"):
        workflow_pkg.WorkflowToEvalSuite.on_publish_workflow_eval_suite(state, ctx)


def test_workflow_to_eval_suite_capture_step_normalizes_alias_without_revalidating_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_repo_workflow_to_eval_suite_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_to_eval_suite")
    workflow_module = importlib.import_module("workflows.workflow_to_eval_suite.workflow")

    def _unexpected_validate(*args, **kwargs):
        raise AssertionError("capture step should not revalidate the capability snapshot to recover the workflow name")

    monkeypatch.setattr(workflow_module, "validate_selected_workflow_capability_snapshot", _unexpected_validate)

    task_folder = tmp_path / ".autoloop" / "tasks" / "eval-capture-task"
    workflow_folder = task_folder / "wf_workflow_to_eval_suite"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    state = workflow_pkg.WorkflowToEvalSuite.State(
        selected_workflow_reference="release-readiness",
        task_title="Release readiness evaluation suite",
    )
    ctx = Context(
        task_id="eval-capture-task",
        run_id="run-1",
        workflow_name="workflow_to_eval_suite",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=tmp_path / "workflows" / "workflow_to_eval_suite",
        state=state,
        session_store=InMemorySessionStore(),
        workflow_params={"selected_workflow": "release-readiness", "task_title": state.task_title},
    )

    next_state, event = workflow_pkg.WorkflowToEvalSuite.on_capture_selected_workflow_contract(state, ctx)

    snapshot = json.loads((workflow_folder / "selected_workflow_capability.json").read_text(encoding="utf-8"))

    assert event.tag == "selected_workflow_contract_captured"
    assert next_state.selected_workflow_name == "release_candidate_to_go_no_go"
    assert snapshot["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert snapshot["selected_workflow_capability"]["workflow_name"] == "release_candidate_to_go_no_go"


def _make_publish_eval_suite_test_context(
    tmp_path: Path,
    monkeypatch,
    *,
    selected_workflow_reference: str = "release_candidate_to_go_no_go",
    snapshot_workflow_name: str = "release_candidate_to_go_no_go",
    manifest_overrides: dict[str, object] | None = None,
    summary_overrides: dict[str, object] | None = None,
) -> tuple[object, object, Context]:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_to_eval_suite")
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_workflow_to_eval_suite"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)

    state = workflow_pkg.WorkflowToEvalSuite.State(
        selected_workflow_reference=selected_workflow_reference,
        selected_workflow_name=snapshot_workflow_name,
        task_title="Release readiness evaluation suite",
        sponsor_role="engineering productivity",
        desired_outcome="Publish a reusable eval suite for workflow quality gating.",
        case_ids=[
            "baseline_release_gate",
            "edge_missing_owner",
            "adversarial_rollback_gap",
        ],
        case_kinds=["benchmark", "edge", "adversarial"],
        covered_expected_artifacts=[
            "blocking_issues",
            "decision_summary",
            "release_decision_package",
            "risk_register",
            "rollback_readiness",
        ],
    )
    ctx = Context(
        task_id="workflow-eval-suite-task",
        run_id="run-1",
        workflow_name="workflow_to_eval_suite",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "workflow_to_eval_suite",
        state=state,
        session_store=InMemorySessionStore(),
        workflow_params={
            "selected_workflow": selected_workflow_reference,
            "task_title": state.task_title,
        },
    )

    write_selected_workflow_capability_snapshot(ctx, snapshot_workflow_name)
    for name in (
        "benchmark_case_matrix.md",
        "edge_case_matrix.md",
        "adversarial_case_matrix.md",
        "eval_rubric.md",
    ):
        (workflow_folder / name).write_text("# Placeholder\n", encoding="utf-8")
    (workflow_folder / "workflow_eval_suite.md").write_text(
        "\n".join(
            (
                "# Workflow Eval Suite",
                "",
                "Selected workflow: `release_candidate_to_go_no_go`.",
                "Use `validated_eval_case_manifest.json` as the authoritative manifest after publication.",
                "Use `eval_rubric.md` during downstream evaluation execution.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "workflow_eval_next_action.md").write_text(
        "\n".join(
            (
                "# Workflow Eval Next Action",
                "",
                "1. Use `validated_eval_case_manifest.json` as the authoritative manifest.",
                "2. Score the downstream run with `eval_rubric.md`.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_payload = {
        "cases": [
            {
                "case_id": "baseline_release_gate",
                "case_kind": "benchmark",
                "expected_artifacts": [
                    "release_decision_package",
                    "decision_summary",
                ],
                "prompt": "Assess a routine release candidate with complete evidence and publish the release decision package.",
                "workflow_parameters": {"release_name": "2026.04"},
            },
            {
                "case_id": "edge_missing_owner",
                "case_kind": "edge",
                "expected_artifacts": ["risk_register", "blocking_issues"],
                "prompt": "Assess a release candidate where ownership is unclear but the team still wants a decision.",
                "workflow_parameters": {"release_name": "2026.04-edge"},
            },
            {
                "case_id": "adversarial_rollback_gap",
                "case_kind": "adversarial",
                "expected_artifacts": [
                    "release_decision_package",
                    "rollback_readiness",
                ],
                "prompt": "Assess a release candidate where rollback evidence is weak and shipping pressure is high.",
                "workflow_parameters": {"release_name": "2026.04-adversarial"},
            },
        ]
    }
    if manifest_overrides:
        manifest_payload.update(manifest_overrides)
    (workflow_folder / "eval_case_manifest.json").write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary_payload = {
        "authoritative_artifacts": [
            "workflow_eval_suite",
            "workflow_eval_suite_summary",
            "workflow_eval_next_action",
            "validated_eval_case_manifest",
            "eval_rubric",
        ],
        "case_count": 3,
        "case_ids": list(state.case_ids),
        "case_kinds": list(state.case_kinds),
        "covered_expected_artifacts": list(state.covered_expected_artifacts),
        "next_action": "Run the evaluation harness against release_candidate_to_go_no_go using validated_eval_case_manifest.json and eval_rubric.md; keep this published suite attached to the downstream evaluation run.",
        "ready_for_publication": True,
        "selected_workflow_entry_step": "bootstrap",
        "selected_workflow_name": snapshot_workflow_name,
        "selected_workflow_parameters_supported": True,
    }
    if summary_overrides:
        summary_payload.update(summary_overrides)
    (workflow_folder / "workflow_eval_suite_summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return workflow_pkg, state, ctx


def _install_repo_workflow_to_eval_suite_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
        "workflow_to_eval_suite",
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
