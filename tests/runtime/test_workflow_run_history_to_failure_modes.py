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
from autoloop_v3.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from autoloop_v3.runtime.loader import (
    WorkflowParameterError,
    coerce_workflow_parameter_mapping,
    discover_workflow_packages,
    resolve_workflow_reference,
)
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow_package
from autoloop_v3.autoloop_optimizer.adaptation import write_selected_workflow_capability_snapshot
from autoloop_v3.autoloop_optimizer.diagnostics import write_selected_workflow_run_history_snapshot
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


def test_repo_workflows_namespace_discovers_workflow_run_history_to_failure_modes_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "workflow_run_history_to_failure_modes" in discovered
    package = discovered["workflow_run_history_to_failure_modes"]
    assert package.package_name == "workflow_run_history_to_failure_modes"
    assert "workflow-failure-modes" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "workflows" / "workflow_run_history_to_failure_modes" / "workflow.toml"
    )


def test_workflow_run_history_to_failure_modes_package_compiles_with_explicit_control_contracts(
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_run_history_to_failure_modes")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.WorkflowRunHistoryToFailureModes)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "capture_run_history_context",
        "frame_diagnostic_scope",
        "map_failure_modes",
        "package_improvement_pressure",
        "publish_failure_mode_package",
    )

    frame_step = compiled.steps["frame_diagnostic_scope"]
    assert frame_step.available_routes == (
        "diagnostic_scope_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(compiled.route("frame_diagnostic_scope", "diagnostic_scope_framed").required_writes) == [
        "frame_diagnostic_scope.diagnostic_scope_brief",
        "frame_diagnostic_scope.run_history_scope",
    ]
    assert frame_step.expected_output_schema is not None

    analysis_step = compiled.steps["map_failure_modes"]
    assert list(compiled.route("map_failure_modes", "failure_modes_mapped").required_writes) == [
        "map_failure_modes.failure_mode_map",
        "map_failure_modes.failure_mode_manifest",
        "map_failure_modes.recurring_weak_points",
    ]
    assert analysis_step.expected_output_schema is not None

    package_step = compiled.steps["package_improvement_pressure"]
    assert list(compiled.route("package_improvement_pressure", "improvement_pressure_packaged").required_writes) == [
        "package_improvement_pressure.improvement_opportunities",
        "package_improvement_pressure.improvement_opportunities_summary",
        "package_improvement_pressure.diagnostic_next_actions",
    ]
    assert package_step.expected_output_schema is not None
    assert set(package_step.expected_output_schema["required"]) >= {
        "summary",
        "selected_workflow_name",
        "evidence_run_ids",
        "failure_mode_ids",
        "ranked_opportunity_ids",
        "authoritative_artifacts",
        "next_action",
        "publication_boundary",
        "ready_for_publication",
    }

    publish_step = compiled.steps["publish_failure_mode_package"]
    assert publish_step.requires == (
        "capture_run_history_context.selected_workflow_capability",
        "capture_run_history_context.selected_workflow_run_history",
        "frame_diagnostic_scope.diagnostic_scope_brief",
        "frame_diagnostic_scope.run_history_scope",
        "map_failure_modes.failure_mode_map",
        "map_failure_modes.failure_mode_manifest",
        "map_failure_modes.recurring_weak_points",
        "package_improvement_pressure.improvement_opportunities",
        "package_improvement_pressure.improvement_opportunities_summary",
        "package_improvement_pressure.diagnostic_next_actions",
    )


def test_workflow_run_history_to_failure_modes_package_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "workflow_run_history_to_failure_modes.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_workflow_run_history_to_failure_modes.py",
    ):
        assert required in text


def test_workflow_run_history_to_failure_modes_prompt_readme_uses_shared_contract_sections() -> None:
    text = (
        REPO_ROOT / "workflows" / "workflow_run_history_to_failure_modes" / "prompts" / "README.md"
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
        "`diagnostic_scope_framed`",
        "`failure_modes_mapped`",
        "`improvement_pressure_packaged`",
        "`needs_rework`",
        "`needs_replan`",
        "`frame_producer.md` / `frame_verifier.md`",
        "ImprovementPressurePayload",
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
                "`selected_workflow_run_history`",
                "`diagnostic_scope_brief`",
                "`run_history_scope`",
                "`diagnostic_scope_framed`",
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
                "Do not overwrite `diagnostic_scope_brief` or `run_history_scope` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`diagnostic_scope_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
        (
            "analyze_producer.md",
            (
                "## Step Contract",
                "## Artifact Contract",
                "| Artifact | Direction | Notes |",
                "## Output Requirements",
                "## Evidence",
                "Route guidance for the verifier",
                "Forbidden",
                "`failure_mode_map`",
                "`failure_mode_manifest`",
                "`recurring_weak_points`",
                "`failure_modes_mapped`",
                "`needs_rework`",
                "`needs_replan`",
                "Reserved routes are only",
            ),
        ),
        (
            "analyze_verifier.md",
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
                "Do not overwrite `failure_mode_map`, `failure_mode_manifest`, or `recurring_weak_points` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`failure_modes_mapped`",
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
                "`improvement_opportunities`",
                "`improvement_opportunities_summary`",
                "`diagnostic_next_actions`",
                "`failure_mode_diagnostic_receipt.json`",
                "`improvement_pressure_packaged`",
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
                "Do not overwrite `improvement_opportunities`, `improvement_opportunities_summary`, or `diagnostic_next_actions` during verification.",
                "Do not create `failure_mode_diagnostic_receipt.json` in this step.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`improvement_pressure_packaged`",
                "`needs_rework`",
                "`needs_replan`",
                "`diagnostic_publication_only`",
                "Use reserved routes only",
            ),
        ),
    ),
)
def test_workflow_run_history_to_failure_modes_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (
        REPO_ROOT / "workflows" / "workflow_run_history_to_failure_modes" / "prompts" / prompt_name
    ).read_text(encoding="utf-8")

    for marker in required_markers:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"


def test_workflow_run_history_to_failure_modes_package_rejects_blank_selected_workflow(tmp_path: Path) -> None:
    _install_repo_workflow_run_history_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "workflow_run_history_to_failure_modes").parameters_cls

    with pytest.raises(WorkflowParameterError, match="value must be non-empty"):
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "selected_workflow": "   ",
                "task_title": "Release workflow failure-mode diagnosis",
            },
        )


def test_workflow_run_history_to_failure_modes_package_normalizes_repeatable_inputs(tmp_path: Path) -> None:
    _install_repo_workflow_run_history_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "workflow_run_history_to_failure_modes").parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "selected_workflow": " release_candidate_to_go_no_go ",
            "task_title": " Release workflow failure-mode diagnosis ",
            "statuses": [
                " failed ",
                "",
                "paused",
                "blocked",
                "paused",
            ],
            "max_runs": 12,
            "sponsor_role": " Workflow Platform ",
            "desired_outcome": " ",
            "constraints": [
                " keep runtime control narrow ",
                "",
                "keep runtime control narrow",
                "Stop at diagnostic publication.",
            ],
        },
    )

    assert normalized == {
        "constraints": [
            "keep runtime control narrow",
            "Stop at diagnostic publication.",
        ],
        "desired_outcome": None,
        "max_runs": 12,
        "selected_workflow": "release_candidate_to_go_no_go",
        "sponsor_role": "Workflow Platform",
        "statuses": ["blocked", "failed", "paused"],
        "task_title": "Release workflow failure-mode diagnosis",
    }


def test_workflow_run_history_to_failure_modes_bootstrap_reads_typed_ctx_params(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_run_history_to_failure_modes")
    parameters_cls = resolve_workflow_reference(REPO_ROOT, "workflow_run_history_to_failure_modes").parameters_cls
    assert parameters_cls is not None
    typed_params = parameters_cls.model_validate(
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "selected_workflow": " release_candidate_to_go_no_go ",
                "task_title": " Release workflow failure-mode diagnosis ",
                "statuses": [" failed ", "", "paused", "blocked", "paused"],
                "max_runs": 12,
                "sponsor_role": " Workflow Platform ",
                "desired_outcome": " ",
                "constraints": [
                    " keep runtime control narrow ",
                    "",
                    "keep runtime control narrow",
                    "Stop at diagnostic publication.",
                ],
            },
        )
    )

    task_folder = tmp_path / ".autoloop" / "tasks" / "typed-bootstrap-task"
    workflow_folder = task_folder / "wf_workflow_run_history_to_failure_modes"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Typed bootstrap request.\n", encoding="utf-8")

    ctx = Context(
        task_id="typed-bootstrap-task",
        run_id="run-1",
        workflow_name="workflow_run_history_to_failure_modes",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "workflow_run_history_to_failure_modes",
        state=workflow_pkg.WorkflowRunHistoryToFailureModes.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={},
    )

    next_state, event = workflow_pkg.WorkflowRunHistoryToFailureModes.on_bootstrap(
        workflow_pkg.WorkflowRunHistoryToFailureModes.State(),
        ctx,
    )

    assert event.tag == "inputs_prepared"
    assert next_state.selected_workflow_reference == "release_candidate_to_go_no_go"
    assert next_state.task_title == "Release workflow failure-mode diagnosis"
    assert next_state.statuses == ["blocked", "failed", "paused"]
    assert next_state.max_runs == 12
    assert next_state.sponsor_role == "Workflow Platform"
    assert next_state.desired_outcome is None
    assert next_state.constraints == [
        "keep runtime control narrow",
        "Stop at diagnostic publication.",
    ]
    assert ctx.get_session("frame_session") is not None
    assert ctx.get_session("analysis_session") is not None
    assert ctx.get_session("package_session") is not None

    invocation_contract = json.loads((workflow_folder / "invocation_contract.json").read_text(encoding="utf-8"))
    assert invocation_contract["selected_workflow_reference"] == "release_candidate_to_go_no_go"
    assert invocation_contract["task_title"] == "Release workflow failure-mode diagnosis"
    assert invocation_contract["statuses"] == ["blocked", "failed", "paused"]
    assert invocation_contract["max_runs"] == 12
    assert invocation_contract["desired_outcome"] is None
    assert invocation_contract["constraints"] == next_state.constraints


def test_workflow_run_history_to_failure_modes_package_runs_and_publishes_terminal_diagnostic_artifacts(
    tmp_path: Path,
) -> None:
    _install_repo_workflow_run_history_package(tmp_path)
    _seed_release_run_history(tmp_path)

    provider = ScriptedLLMProvider(
        producer_turns=[
            _produce_frame_scope,
            _produce_failure_modes,
            _produce_improvement_package,
        ],
        verifier_turns=[
            Outcome(
                raw_output="diagnostic scope framed\n",
                tag="diagnostic_scope_framed",
                payload={
                    "summary": "The selected workflow, filtered runs, and diagnostic boundary are explicit enough for failure-mode clustering.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "authoritative_artifacts": [
                        "diagnostic_scope_brief",
                        "run_history_scope",
                    ],
                    "evidence_run_ids": [
                        "run-release-paused",
                        "run-release-blocked",
                        "run-release-failed",
                    ],
                    "diagnostic_axes": [
                        "clarification loops",
                        "rollback evidence quality",
                        "artifact-boundary discipline",
                    ],
                },
            ),
            Outcome(
                raw_output="failure modes mapped\n",
                tag="failure_modes_mapped",
                payload={
                    "summary": "The filtered release-workflow history now clusters into two failure modes plus recurring weak points.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "evidence_run_ids": [
                        "run-release-paused",
                        "run-release-blocked",
                        "run-release-failed",
                    ],
                    "failure_mode_ids": [
                        "clarification_loops",
                        "rollback_evidence_gaps",
                    ],
                    "recurring_weak_point_ids": [
                        "request_contract_drift",
                        "downstream_evidence_gap",
                    ],
                },
            ),
            Outcome(
                raw_output="improvement pressure packaged\n",
                tag="improvement_pressure_packaged",
                payload={
                    "summary": "The ranked improvement package is aligned and ready for deterministic diagnostic publication.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "evidence_run_ids": [
                        "run-release-paused",
                        "run-release-blocked",
                        "run-release-failed",
                    ],
                    "failure_mode_ids": [
                        "clarification_loops",
                        "rollback_evidence_gaps",
                    ],
                    "ranked_opportunity_ids": [
                        "tighten_request_contract",
                        "add_rollback_gate",
                    ],
                    "authoritative_artifacts": [
                        "improvement_opportunities",
                        "improvement_opportunities_summary",
                        "diagnostic_next_actions",
                        "failure_mode_map",
                        "failure_mode_manifest",
                        "recurring_weak_points",
                    ],
                    "next_action": "Recommend a refinement pass against release_candidate_to_go_no_go for the P1 opportunities, then rerun this diagnostic after the next evaluation cycle.",
                    "publication_boundary": "diagnostic_publication_only",
                    "ready_for_publication": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "workflow_run_history_to_failure_modes",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="workflow-failure-modes-task",
            message="Diagnose why the release workflow keeps stalling across recent runs.",
            workflow_params={
                "selected_workflow": "release_candidate_to_go_no_go",
                "task_title": "Release workflow failure-mode diagnosis",
                "statuses": ["failed", "blocked", "paused"],
                "max_runs": 3,
                "sponsor_role": "workflow platform",
                "desired_outcome": "Publish a reusable failure-mode package and ranked next actions for the selected workflow.",
                "constraints": [
                    "Keep runtime control narrow.",
                    "Stop at diagnostic publication.",
                ],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "workflow-failure-modes-task"
    workflow_dir = task_dir / "wf_workflow_run_history_to_failure_modes"
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    selected_capability = json.loads((workflow_dir / "selected_workflow_capability.json").read_text(encoding="utf-8"))
    run_history_snapshot = json.loads((workflow_dir / "selected_workflow_run_history.json").read_text(encoding="utf-8"))
    failure_mode_manifest = json.loads((workflow_dir / "failure_mode_manifest.json").read_text(encoding="utf-8"))
    improvement_summary = json.loads((workflow_dir / "improvement_opportunities.json").read_text(encoding="utf-8"))
    diagnostic_receipt = json.loads((workflow_dir / "failure_mode_diagnostic_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert (workflow_dir / "selected_workflow_capability.json").exists()
    assert (workflow_dir / "selected_workflow_run_history.json").exists()
    assert (workflow_dir / "diagnostic_scope_brief.md").exists()
    assert (workflow_dir / "run_history_scope.md").exists()
    assert (workflow_dir / "failure_mode_map.md").exists()
    assert (workflow_dir / "failure_mode_manifest.json").exists()
    assert (workflow_dir / "recurring_weak_points.md").exists()
    assert (workflow_dir / "improvement_opportunities.md").exists()
    assert (workflow_dir / "improvement_opportunities.json").exists()
    assert (workflow_dir / "diagnostic_next_actions.md").exists()
    assert (workflow_dir / "failure_mode_diagnostic_receipt.json").exists()
    assert not (task_dir / "wf_workflow_and_eval_to_refined_workflow_package").exists()
    children_file = run_dir / "children.jsonl"
    assert (not children_file.exists()) or children_file.read_text(encoding="utf-8") == ""

    assert invocation_contract == {
        "constraints": [
            "Keep runtime control narrow.",
            "Stop at diagnostic publication.",
        ],
        "desired_outcome": "Publish a reusable failure-mode package and ranked next actions for the selected workflow.",
        "max_runs": 3,
        "message": "Diagnose why the release workflow keeps stalling across recent runs.\n",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "selected_workflow_reference": "release_candidate_to_go_no_go",
        "sponsor_role": "workflow platform",
        "statuses": ["blocked", "failed", "paused"],
        "task_id": "workflow-failure-modes-task",
        "task_title": "Release workflow failure-mode diagnosis",
        "workflow_name": "workflow_run_history_to_failure_modes",
    }
    assert selected_capability["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert selected_capability["selected_workflow_capability"]["entry_step_name"] == "bootstrap"
    assert selected_capability["selected_workflow_capability"]["parameters_supported"] is True
    assert {
        entry["name"] for entry in selected_capability["selected_workflow_capability"]["parameters"]
    } >= {"release_name", "deployment_environment", "release_owner"}

    assert run_history_snapshot == {
        "repo_root": str(tmp_path.resolve()),
        "run_id": run_dir.name,
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "selected_workflow_run_history": {
            "max_runs": 3,
            "run_count": 3,
            "runs": [
                {
                    "children": [],
                    "events": [
                        {"event_type": "run_started", "seq": 1},
                        {"event_type": "step_executed", "seq": 2, "step_name": "frame_release"},
                        {"event_type": "run_finished", "seq": 3, "status": "paused"},
                    ],
                    "parent_record": {
                        "run_folder": ".autoloop/tasks/ops-program/wf_task_to_workflow_strategy/runs/run-parent",
                        "run_id": "run-parent",
                        "task_folder": ".autoloop/tasks/ops-program",
                        "task_id": "ops-program",
                        "workflow_folder": ".autoloop/tasks/ops-program/wf_task_to_workflow_strategy",
                        "workflow_name": "task_to_workflow_strategy",
                    },
                    "request_text": "Ship release 2026.07 while rollback ownership is unresolved.\n",
                    "run_metadata": {
                        "created_at": "2026-04-23T08:00:00+00:00",
                        "error": None,
                        "package_folder": "workflows/release_candidate_to_go_no_go",
                        "pending_question": "Who owns rollback approval for release 2026.07?",
                        "run_id": "run-release-paused",
                        "status": "paused",
                        "task_id": "release-gamma",
                        "terminal": "PAUSE",
                        "updated_at": "2026-04-23T08:10:00+00:00",
                        "workflow_name": "release_candidate_to_go_no_go",
                        "workflow_params": {
                            "deployment_environment": "production",
                            "release_name": "2026.07",
                        },
                    },
                    "source_paths": {
                        "checkpoint_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-gamma"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-paused"
                            / "checkpoint.json"
                        ),
                        "children_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-gamma"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-paused"
                            / "children.jsonl"
                        ),
                        "events_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-gamma"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-paused"
                            / "events.jsonl"
                        ),
                        "parent_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-gamma"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-paused"
                            / "parent.json"
                        ),
                        "raw_dir": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-gamma"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-paused"
                            / "raw"
                        ),
                        "request_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-gamma"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-paused"
                            / "request.md"
                        ),
                        "run_dir": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-gamma"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-paused"
                        ),
                        "run_meta_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-gamma"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-paused"
                            / "run.json"
                        ),
                        "task_dir": str(tmp_path / ".autoloop" / "tasks" / "release-gamma"),
                        "trace_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-gamma"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-paused"
                            / "trace.jsonl"
                        ),
                        "workflow_dir": str(
                            tmp_path / ".autoloop" / "tasks" / "release-gamma" / "wf_release_candidate_to_go_no_go"
                        ),
                    },
                },
                {
                    "children": [
                        {
                            "run_id": "child-investigation-1",
                            "status": "success",
                            "terminal": "FINISH",
                            "workflow_name": "investigation_request_to_evidence_pack",
                        }
                    ],
                    "events": [
                        {"event_type": "run_started", "seq": 1},
                        {"event_type": "step_executed", "seq": 2, "step_name": "assemble_evidence_pack"},
                        {"event_type": "run_finished", "seq": 3, "status": "blocked"},
                    ],
                    "parent_record": None,
                    "request_text": "Ship release 2026.06 while ownership and evidence are still in flux.\n",
                    "run_metadata": {
                        "created_at": "2026-04-22T09:00:00+00:00",
                        "error": None,
                        "package_folder": "workflows/release_candidate_to_go_no_go",
                        "pending_question": None,
                        "run_id": "run-release-blocked",
                        "status": "blocked",
                        "task_id": "release-beta",
                        "terminal": "PAUSE",
                        "updated_at": "2026-04-22T09:15:00+00:00",
                        "workflow_name": "release_candidate_to_go_no_go",
                        "workflow_params": {
                            "deployment_environment": "production",
                            "release_name": "2026.06",
                        },
                    },
                    "source_paths": {
                        "checkpoint_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-beta"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-blocked"
                            / "checkpoint.json"
                        ),
                        "children_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-beta"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-blocked"
                            / "children.jsonl"
                        ),
                        "events_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-beta"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-blocked"
                            / "events.jsonl"
                        ),
                        "parent_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-beta"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-blocked"
                            / "parent.json"
                        ),
                        "raw_dir": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-beta"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-blocked"
                            / "raw"
                        ),
                        "request_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-beta"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-blocked"
                            / "request.md"
                        ),
                        "run_dir": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-beta"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-blocked"
                        ),
                        "run_meta_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-beta"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-blocked"
                            / "run.json"
                        ),
                        "task_dir": str(tmp_path / ".autoloop" / "tasks" / "release-beta"),
                        "trace_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-beta"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-blocked"
                            / "trace.jsonl"
                        ),
                        "workflow_dir": str(
                            tmp_path / ".autoloop" / "tasks" / "release-beta" / "wf_release_candidate_to_go_no_go"
                        ),
                    },
                },
                {
                    "children": [
                        {
                            "run_id": "child-investigation-0",
                            "status": "FAILED",
                            "terminal": "FAIL",
                            "workflow_name": "investigation_request_to_evidence_pack",
                        }
                    ],
                    "events": [
                        {"event_type": "run_started", "seq": 1},
                        {"event_type": "step_executed", "seq": 2, "step_name": "assess_go_no_go"},
                        {"event_type": "run_finished", "seq": 3, "status": "failed"},
                    ],
                    "parent_record": None,
                    "request_text": "Ship release 2026.05 even though rollback evidence is incomplete.\n",
                    "run_metadata": {
                        "created_at": "2026-04-21T10:00:00+00:00",
                        "error": "Rollback readiness was never published.",
                        "package_folder": "workflows/release_candidate_to_go_no_go",
                        "pending_question": None,
                        "run_id": "run-release-failed",
                        "status": "failed",
                        "task_id": "release-alpha",
                        "terminal": "FAIL",
                        "updated_at": "2026-04-21T10:20:00+00:00",
                        "workflow_name": "release_candidate_to_go_no_go",
                        "workflow_params": {
                            "deployment_environment": "production",
                            "release_name": "2026.05",
                        },
                    },
                    "source_paths": {
                        "checkpoint_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-alpha"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-failed"
                            / "checkpoint.json"
                        ),
                        "children_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-alpha"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-failed"
                            / "children.jsonl"
                        ),
                        "events_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-alpha"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-failed"
                            / "events.jsonl"
                        ),
                        "parent_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-alpha"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-failed"
                            / "parent.json"
                        ),
                        "raw_dir": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-alpha"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-failed"
                            / "raw"
                        ),
                        "request_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-alpha"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-failed"
                            / "request.md"
                        ),
                        "run_dir": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-alpha"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-failed"
                        ),
                        "run_meta_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-alpha"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-failed"
                            / "run.json"
                        ),
                        "task_dir": str(tmp_path / ".autoloop" / "tasks" / "release-alpha"),
                        "trace_file": str(
                            tmp_path
                            / ".autoloop"
                            / "tasks"
                            / "release-alpha"
                            / "wf_release_candidate_to_go_no_go"
                            / "runs"
                            / "run-release-failed"
                            / "trace.jsonl"
                        ),
                        "workflow_dir": str(
                            tmp_path / ".autoloop" / "tasks" / "release-alpha" / "wf_release_candidate_to_go_no_go"
                        ),
                    },
                },
            ],
            "statuses": ["blocked", "failed", "paused"],
        },
        "task_id": "workflow-failure-modes-task",
        "workflow_name": "workflow_run_history_to_failure_modes",
    }

    assert failure_mode_manifest == {
        "evidence_run_ids": [
            "run-release-paused",
            "run-release-blocked",
            "run-release-failed",
        ],
        "failure_mode_ids": [
            "clarification_loops",
            "rollback_evidence_gaps",
        ],
        "failure_modes": [
            {
                "evidence_run_ids": [
                    "run-release-paused",
                    "run-release-blocked",
                ],
                "failure_mode_id": "clarification_loops",
                "likely_causes": [
                    "The release workflow allows unresolved ownership gaps to persist too long.",
                    "Questions stay local to one run instead of tightening the upstream request contract.",
                ],
                "severity": "high",
                "supporting_signals": [
                    "Paused and blocked runs both stop after ownership clarification pressure.",
                    "The parent strategy run delegated work before ownership was explicit.",
                ],
                "symptom_pattern": "Runs stall around unresolved release ownership and rollback approval questions.",
                "title": "Clarification loops stall decision publication",
            },
            {
                "evidence_run_ids": [
                    "run-release-blocked",
                    "run-release-failed",
                ],
                "failure_mode_id": "rollback_evidence_gaps",
                "likely_causes": [
                    "Rollback readiness is treated as downstream evidence instead of a framing-time gate.",
                    "Child evidence-gathering runs do not close the rollback contract before assessment.",
                ],
                "severity": "high",
                "supporting_signals": [
                    "Blocked and failed runs both lacked durable rollback-readiness evidence.",
                    "The failed run terminated after assessment without a published rollback artifact.",
                ],
                "symptom_pattern": "Runs progress into assessment with rollback evidence still incomplete.",
                "title": "Rollback evidence gaps survive into terminal decision work",
            },
        ],
        "recurring_weak_point_ids": [
            "request_contract_drift",
            "downstream_evidence_gap",
        ],
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "workflow_name": "workflow_run_history_to_failure_modes",
    }

    assert improvement_summary == {
        "authoritative_artifacts": [
            "improvement_opportunities",
            "improvement_opportunities_summary",
            "diagnostic_next_actions",
            "failure_mode_map",
            "failure_mode_manifest",
            "recurring_weak_points",
        ],
        "evidence_run_ids": [
            "run-release-paused",
            "run-release-blocked",
            "run-release-failed",
        ],
        "failure_mode_ids": [
            "clarification_loops",
            "rollback_evidence_gaps",
        ],
        "next_action": "Recommend a refinement pass against release_candidate_to_go_no_go for the P1 opportunities, then rerun this diagnostic after the next evaluation cycle.",
        "opportunities": [
            {
                "expected_impact": "Reduces blocked and paused runs caused by missing release ownership and rollback-approval inputs.",
                "linked_failure_mode_ids": ["clarification_loops"],
                "opportunity_id": "tighten_request_contract",
                "priority": "P1",
                "recommended_next_step": "workflow_and_eval_to_refined_workflow_package",
                "title": "Tighten the release-request framing contract before evidence assembly starts",
                "why_now": "The paused and blocked runs show that the workflow keeps paying clarification cost late in the cycle.",
            },
            {
                "expected_impact": "Prevents assessment from proceeding without explicit rollback-readiness evidence.",
                "linked_failure_mode_ids": ["rollback_evidence_gaps"],
                "opportunity_id": "add_rollback_gate",
                "priority": "P1",
                "recommended_next_step": "workflow_and_eval_to_refined_workflow_package",
                "title": "Add an explicit rollback-evidence gate before assessment and packaging",
                "why_now": "The failed run shows the release workflow can reach terminal work without a durable rollback artifact.",
            },
        ],
        "publication_boundary": "diagnostic_publication_only",
        "ranked_opportunity_ids": [
            "tighten_request_contract",
            "add_rollback_gate",
        ],
        "ready_for_publication": True,
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "workflow_name": "workflow_run_history_to_failure_modes",
    }

    assert diagnostic_receipt == {
        "authoritative_artifacts": [
            "improvement_opportunities",
            "improvement_opportunities_summary",
            "diagnostic_next_actions",
            "failure_mode_map",
            "failure_mode_manifest",
            "recurring_weak_points",
        ],
        "desired_outcome": "Publish a reusable failure-mode package and ranked next actions for the selected workflow.",
        "diagnostic_next_actions": str(workflow_dir / "diagnostic_next_actions.md"),
        "diagnostic_scope_brief": str(workflow_dir / "diagnostic_scope_brief.md"),
        "evidence_run_ids": [
            "run-release-paused",
            "run-release-blocked",
            "run-release-failed",
        ],
        "failure_mode_ids": [
            "clarification_loops",
            "rollback_evidence_gaps",
        ],
        "failure_mode_manifest": str(workflow_dir / "failure_mode_manifest.json"),
        "failure_mode_map": str(workflow_dir / "failure_mode_map.md"),
        "improvement_opportunities": str(workflow_dir / "improvement_opportunities.md"),
        "improvement_opportunities_summary": str(workflow_dir / "improvement_opportunities.json"),
        "max_runs": 3,
        "next_action": "Recommend a refinement pass against release_candidate_to_go_no_go for the P1 opportunities, then rerun this diagnostic after the next evaluation cycle.",
        "publication_boundary": "diagnostic_publication_only",
        "published": True,
        "ranked_opportunity_ids": [
            "tighten_request_contract",
            "add_rollback_gate",
        ],
        "recurring_weak_point_ids": [
            "request_contract_drift",
            "downstream_evidence_gap",
        ],
        "recurring_weak_points": str(workflow_dir / "recurring_weak_points.md"),
        "run_count": 3,
        "run_history_scope": str(workflow_dir / "run_history_scope.md"),
        "selected_workflow_capability": str(workflow_dir / "selected_workflow_capability.json"),
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "selected_workflow_reference": "release_candidate_to_go_no_go",
        "selected_workflow_run_history": str(workflow_dir / "selected_workflow_run_history.json"),
        "sponsor_role": "workflow platform",
        "statuses": ["blocked", "failed", "paused"],
        "task_title": "Release workflow failure-mode diagnosis",
        "workflow_name": "workflow_run_history_to_failure_modes",
    }
    assert "diagnostic_publication_only" in (workflow_dir / "diagnostic_next_actions.md").read_text(encoding="utf-8")
    assert "tighten_request_contract" in (workflow_dir / "improvement_opportunities.md").read_text(encoding="utf-8")
    assert "add_rollback_gate" in (workflow_dir / "improvement_opportunities.md").read_text(encoding="utf-8")
    assert [call.step_name for call in provider.calls] == [
        "frame_diagnostic_scope",
        "frame_diagnostic_scope",
        "map_failure_modes",
        "map_failure_modes",
        "package_improvement_pressure",
        "package_improvement_pressure",
    ]
    assert list(provider.calls[1].route_required_writes["diagnostic_scope_framed"]) == [
        "frame_diagnostic_scope.diagnostic_scope_brief",
        "frame_diagnostic_scope.run_history_scope",
    ]
    assert provider.calls[3].available_routes == (
        "failure_modes_mapped",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(provider.calls[5].route_required_writes["improvement_pressure_packaged"]) == [
        "package_improvement_pressure.improvement_opportunities",
        "package_improvement_pressure.improvement_opportunities_summary",
        "package_improvement_pressure.diagnostic_next_actions",
    ]


def test_workflow_run_history_to_failure_modes_package_validator_rejects_missing_required_package_fields(
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_run_history_to_failure_modes")
    compiled = compile_workflow(workflow_pkg.WorkflowRunHistoryToFailureModes)
    package_step = compiled.steps["package_improvement_pressure"]
    payload = {
        "summary": "The ranked diagnostic package is aligned and ready for publication.",
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "evidence_run_ids": [
            "run-release-paused",
            "run-release-blocked",
            "run-release-failed",
        ],
        "failure_mode_ids": [
            "clarification_loops",
            "rollback_evidence_gaps",
        ],
        "ranked_opportunity_ids": [
            "tighten_request_contract",
            "add_rollback_gate",
        ],
        "authoritative_artifacts": [
            "improvement_opportunities",
            "improvement_opportunities_summary",
            "diagnostic_next_actions",
            "failure_mode_map",
            "failure_mode_manifest",
            "recurring_weak_points",
        ],
        "next_action": "Recommend a refinement pass and rerun diagnostics later.",
        "publication_boundary": "diagnostic_publication_only",
        "ready_for_publication": True,
    }

    payload.pop("publication_boundary")

    with pytest.raises(ValidationError, match="publication_boundary"):
        package_step.expected_output_validator(payload)


def test_workflow_run_history_to_failure_modes_publish_rejects_empty_filtered_history(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_failure_modes_test_context(
        tmp_path,
        monkeypatch,
        history_mode="empty_filtered_history",
    )

    with pytest.raises(ValueError, match="selected_workflow_run_history.json must contain at least one filtered run"):
        workflow_pkg.WorkflowRunHistoryToFailureModes.on_publish_failure_mode_package(state, ctx)


def test_workflow_run_history_to_failure_modes_publish_rejects_selected_workflow_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_failure_modes_test_context(tmp_path, monkeypatch)
    snapshot_path = ctx.workflow_folder / "selected_workflow_run_history.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["selected_workflow_name"] = "security_finding_to_verified_remediation"
    snapshot_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="selected_workflow_run_history.json selected_workflow_name must match selected_workflow_capability.json",
    ):
        workflow_pkg.WorkflowRunHistoryToFailureModes.on_publish_failure_mode_package(state, ctx)


def test_workflow_run_history_to_failure_modes_publish_rejects_missing_diagnostic_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_failure_modes_test_context(tmp_path, monkeypatch)
    (ctx.workflow_folder / "failure_mode_map.md").unlink()

    with pytest.raises(FileNotFoundError, match="failure_mode_map.md"):
        workflow_pkg.WorkflowRunHistoryToFailureModes.on_publish_failure_mode_package(state, ctx)


def test_workflow_run_history_to_failure_modes_publish_rejects_hidden_downstream_execution_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_failure_modes_test_context(
        tmp_path,
        monkeypatch,
        summary_overrides={"publication_boundary": "auto_refinement"},
    )

    with pytest.raises(
        ValueError,
        match="improvement_opportunities.json publication_boundary must be diagnostic_publication_only",
    ):
        workflow_pkg.WorkflowRunHistoryToFailureModes.on_publish_failure_mode_package(state, ctx)


def test_workflow_run_history_to_failure_modes_publish_rejects_incomplete_authoritative_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_failure_modes_test_context(
        tmp_path,
        monkeypatch,
        summary_overrides={
            "authoritative_artifacts": [
                "improvement_opportunities",
                "improvement_opportunities_summary",
                "failure_mode_map",
                "failure_mode_manifest",
                "recurring_weak_points",
            ]
        },
    )

    with pytest.raises(
        ValueError,
        match="improvement_opportunities.json authoritative_artifacts must include",
    ):
        workflow_pkg.WorkflowRunHistoryToFailureModes.on_publish_failure_mode_package(state, ctx)


def test_workflow_run_history_to_failure_modes_publish_rejects_hidden_downstream_execution_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_failure_modes_test_context(tmp_path, monkeypatch)
    (ctx.workflow_folder / "diagnostic_next_actions.md").write_text(
        "\n".join(
            (
                "# Diagnostic Next Actions",
                "",
                "- Publication boundary: `diagnostic_publication_only`.",
                "- Automatically run `workflow_and_eval_to_refined_workflow_package` next.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="diagnostic_next_actions.md must not imply hidden downstream execution",
    ):
        workflow_pkg.WorkflowRunHistoryToFailureModes.on_publish_failure_mode_package(state, ctx)


def _produce_frame_scope(request) -> str:
    run_ids = _captured_run_ids(request)
    request.artifacts.diagnostic_scope_brief.write_text(
        "\n".join(
            (
                "# Diagnostic Scope Brief",
                "",
                "Selected workflow: `release_candidate_to_go_no_go`.",
                "Task: publish a reusable failure-mode package for recent release-workflow stalls.",
                "Sponsor: workflow platform.",
                "Terminal outcome: publish the diagnostic package, machine-readable summary, next actions, and receipt.",
                "This workflow stops at diagnostic publication and does not auto-run refinement or portfolio governance.",
                "Diagnostic axes: clarification loops, rollback evidence quality, and artifact-boundary discipline.",
                "",
            )
        )
        + "\n"
    )
    request.artifacts.run_history_scope.write_text(
        "\n".join(
            (
                "# Run History Scope",
                "",
                f"- Filtered run IDs: {', '.join(run_ids)}.",
                "- Use request text, event traces, child-run outcomes, and parent-run context when present.",
                "- Treat repeated stalls around ownership questions as potential clarification-loop pressure.",
                "- Treat missing rollback evidence that survives into assessment as a separate failure mode.",
                "- Replan only if the selected workflow or filtered evidence window changed materially.",
                "",
            )
        )
        + "\n"
    )
    return "framed diagnostic scope\n"


def _produce_failure_modes(request) -> str:
    run_ids = _captured_run_ids(request)
    request.artifacts.failure_mode_map.write_text(
        "\n".join(
            (
                "# Failure Mode Map",
                "",
                "## clarification_loops",
                f"- Evidence runs: `{run_ids[0]}` and `{run_ids[1]}`.",
                "- Severity: high.",
                "- Pattern: release work stalls around unresolved ownership and rollback-approval questions.",
                "",
                "## rollback_evidence_gaps",
                f"- Evidence runs: `{run_ids[1]}` and `{run_ids[2]}`.",
                "- Severity: high.",
                "- Pattern: assessment proceeds while rollback-readiness evidence remains incomplete.",
                "",
            )
        )
        + "\n"
    )
    request.artifacts.failure_mode_manifest.write_text(
        json.dumps(
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "evidence_run_ids": run_ids,
                "failure_mode_ids": [
                    "clarification_loops",
                    "rollback_evidence_gaps",
                ],
                "failure_modes": [
                    {
                        "failure_mode_id": "clarification_loops",
                        "title": "Clarification loops stall decision publication",
                        "severity": "high",
                        "evidence_run_ids": run_ids[:2],
                        "symptom_pattern": "Runs stall around unresolved release ownership and rollback approval questions.",
                        "likely_causes": [
                            "The release workflow allows unresolved ownership gaps to persist too long.",
                            "Questions stay local to one run instead of tightening the upstream request contract.",
                        ],
                        "supporting_signals": [
                            "Paused and blocked runs both stop after ownership clarification pressure.",
                            "The parent strategy run delegated work before ownership was explicit.",
                        ],
                    },
                    {
                        "failure_mode_id": "rollback_evidence_gaps",
                        "title": "Rollback evidence gaps survive into terminal decision work",
                        "severity": "high",
                        "evidence_run_ids": run_ids[1:],
                        "symptom_pattern": "Runs progress into assessment with rollback evidence still incomplete.",
                        "likely_causes": [
                            "Rollback readiness is treated as downstream evidence instead of a framing-time gate.",
                            "Child evidence-gathering runs do not close the rollback contract before assessment.",
                        ],
                        "supporting_signals": [
                            "Blocked and failed runs both lacked durable rollback-readiness evidence.",
                            "The failed run terminated after assessment without a published rollback artifact.",
                        ],
                    },
                ],
                "recurring_weak_point_ids": [
                    "request_contract_drift",
                    "downstream_evidence_gap",
                ],
                "workflow_name": "workflow_run_history_to_failure_modes",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    request.artifacts.recurring_weak_points.write_text(
        "\n".join(
            (
                "# Recurring Weak Points",
                "",
                "## request_contract_drift",
                "- The filtered runs show that release ownership and rollback approval are not locked early enough.",
                "",
                "## downstream_evidence_gap",
                "- The filtered runs show that child evidence gathering does not guarantee a published rollback artifact before assessment.",
                "",
            )
        )
        + "\n"
    )
    return "mapped failure modes\n"


def _produce_improvement_package(request) -> str:
    run_ids = _captured_run_ids(request)
    request.artifacts.improvement_opportunities.write_text(
        "\n".join(
            (
                "# Improvement Opportunities",
                "",
                "## tighten_request_contract",
                "- Priority: P1.",
                "- Linked failure mode: `clarification_loops`.",
                "- Expected impact: reduce blocked and paused runs caused by unresolved ownership inputs.",
                "",
                "## add_rollback_gate",
                "- Priority: P1.",
                "- Linked failure mode: `rollback_evidence_gaps`.",
                "- Expected impact: prevent assessment from proceeding without explicit rollback evidence.",
                "",
            )
        )
        + "\n"
    )
    request.artifacts.improvement_opportunities_summary.write_text(
        json.dumps(
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "evidence_run_ids": run_ids,
                "failure_mode_ids": [
                    "clarification_loops",
                    "rollback_evidence_gaps",
                ],
                "ranked_opportunity_ids": [
                    "tighten_request_contract",
                    "add_rollback_gate",
                ],
                "opportunities": [
                    {
                        "opportunity_id": "tighten_request_contract",
                        "title": "Tighten the release-request framing contract before evidence assembly starts",
                        "priority": "P1",
                        "linked_failure_mode_ids": ["clarification_loops"],
                        "recommended_next_step": "workflow_and_eval_to_refined_workflow_package",
                        "why_now": "The paused and blocked runs show that the workflow keeps paying clarification cost late in the cycle.",
                        "expected_impact": "Reduces blocked and paused runs caused by missing release ownership and rollback-approval inputs.",
                    },
                    {
                        "opportunity_id": "add_rollback_gate",
                        "title": "Add an explicit rollback-evidence gate before assessment and packaging",
                        "priority": "P1",
                        "linked_failure_mode_ids": ["rollback_evidence_gaps"],
                        "recommended_next_step": "workflow_and_eval_to_refined_workflow_package",
                        "why_now": "The failed run shows the release workflow can reach terminal work without a durable rollback artifact.",
                        "expected_impact": "Prevents assessment from proceeding without explicit rollback-readiness evidence.",
                    },
                ],
                "authoritative_artifacts": [
                    "improvement_opportunities",
                    "improvement_opportunities_summary",
                    "diagnostic_next_actions",
                    "failure_mode_map",
                    "failure_mode_manifest",
                    "recurring_weak_points",
                ],
                "next_action": "Recommend a refinement pass against release_candidate_to_go_no_go for the P1 opportunities, then rerun this diagnostic after the next evaluation cycle.",
                "publication_boundary": "diagnostic_publication_only",
                "ready_for_publication": True,
                "workflow_name": "workflow_run_history_to_failure_modes",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    request.artifacts.diagnostic_next_actions.write_text(
        "\n".join(
            (
                "# Diagnostic Next Actions",
                "",
                "- Publication boundary: `diagnostic_publication_only`.",
                "- Use `workflow_and_eval_to_refined_workflow_package` to address `tighten_request_contract` and `add_rollback_gate`.",
                "- Re-run this diagnostic after the next evaluation cycle to measure whether the filtered run IDs stop repeating the same failure patterns.",
                "",
            )
        )
        + "\n"
    )
    return "packaged improvement pressure\n"


def test_workflow_run_history_capture_step_normalizes_alias_and_preserves_filtered_run_ids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_repo_workflow_run_history_package(tmp_path)
    _seed_release_run_history(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_run_history_to_failure_modes")
    workflow_module = importlib.import_module("workflows.workflow_run_history_to_failure_modes.workflow")

    def _unexpected_validate(*args, **kwargs):
        raise AssertionError("capture step should not revalidate the capability snapshot to recover the workflow name")

    monkeypatch.setattr(workflow_module, "validate_selected_workflow_capability_snapshot", _unexpected_validate)

    task_folder = tmp_path / ".autoloop" / "tasks" / "failure-capture-task"
    workflow_folder = task_folder / "wf_workflow_run_history_to_failure_modes"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    state = workflow_pkg.WorkflowRunHistoryToFailureModes.State(
        selected_workflow_reference="release-readiness",
        task_title="Release workflow failure-mode diagnosis",
        statuses=["blocked", "failed", "paused"],
        max_runs=3,
    )
    ctx = Context(
        task_id="failure-capture-task",
        run_id="run-1",
        workflow_name="workflow_run_history_to_failure_modes",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=tmp_path / "workflows" / "workflow_run_history_to_failure_modes",
        state=state,
        session_store=InMemorySessionStore(),
        workflow_params={
            "selected_workflow": "release-readiness",
            "task_title": state.task_title,
            "statuses": list(state.statuses),
            "max_runs": state.max_runs,
        },
    )

    next_state, event = workflow_pkg.WorkflowRunHistoryToFailureModes.on_capture_run_history_context(state, ctx)

    capability_snapshot = json.loads((workflow_folder / "selected_workflow_capability.json").read_text(encoding="utf-8"))
    history_snapshot = json.loads((workflow_folder / "selected_workflow_run_history.json").read_text(encoding="utf-8"))
    run_ids = [
        entry["run_metadata"]["run_id"]
        for entry in history_snapshot["selected_workflow_run_history"]["runs"]
    ]

    assert event.tag == "run_history_context_captured"
    assert next_state.selected_workflow_name == "release_candidate_to_go_no_go"
    assert next_state.evidence_run_ids == run_ids
    assert capability_snapshot["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert history_snapshot["selected_workflow_name"] == "release_candidate_to_go_no_go"


def _captured_run_ids(request) -> list[str]:
    snapshot = json.loads(request.artifacts.selected_workflow_run_history.read_text())
    runs = snapshot["selected_workflow_run_history"]["runs"]
    return [entry["run_metadata"]["run_id"] for entry in runs]


def _make_publish_failure_modes_test_context(
    tmp_path: Path,
    monkeypatch,
    *,
    history_mode: str = "default",
    summary_overrides: dict[str, object] | None = None,
    manifest_overrides: dict[str, object] | None = None,
) -> tuple[object, object, Context]:
    _install_repo_workflow_run_history_package(tmp_path)
    if history_mode == "empty_filtered_history":
        _seed_release_run_history(tmp_path, include_matching_failures=False)
    else:
        _seed_release_run_history(tmp_path)

    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_run_history_to_failure_modes")
    task_folder = tmp_path / ".autoloop" / "tasks" / "workflow-failure-modes-task"
    workflow_folder = task_folder / "wf_workflow_run_history_to_failure_modes"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)

    initial_state = workflow_pkg.WorkflowRunHistoryToFailureModes.State(
        selected_workflow_reference="release_candidate_to_go_no_go",
        task_title="Release workflow failure-mode diagnosis",
        statuses=["blocked", "failed", "paused"],
        max_runs=3,
        sponsor_role="workflow platform",
        desired_outcome="Publish a reusable failure-mode package and ranked next actions for the selected workflow.",
    )
    initial_ctx = Context(
        task_id="workflow-failure-modes-task",
        run_id="run-1",
        workflow_name="workflow_run_history_to_failure_modes",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=tmp_path / "workflows" / "workflow_run_history_to_failure_modes",
        state=initial_state,
        session_store=InMemorySessionStore(),
        workflow_params={
            "selected_workflow": "release_candidate_to_go_no_go",
            "task_title": initial_state.task_title,
            "statuses": list(initial_state.statuses),
            "max_runs": initial_state.max_runs,
        },
    )

    write_selected_workflow_capability_snapshot(initial_ctx, "release_candidate_to_go_no_go")
    write_selected_workflow_run_history_snapshot(
        initial_ctx,
        "release_candidate_to_go_no_go",
        statuses=initial_state.statuses,
        max_runs=initial_state.max_runs,
    )
    snapshot = json.loads((workflow_folder / "selected_workflow_run_history.json").read_text(encoding="utf-8"))
    run_ids = [entry["run_metadata"]["run_id"] for entry in snapshot["selected_workflow_run_history"]["runs"]]

    state = initial_state.model_copy(
        update={
            "selected_workflow_name": "release_candidate_to_go_no_go",
            "evidence_run_ids": list(run_ids),
            "failure_mode_ids": [
                "clarification_loops",
                "rollback_evidence_gaps",
            ],
            "recurring_weak_point_ids": [
                "request_contract_drift",
                "downstream_evidence_gap",
            ],
            "ranked_opportunity_ids": [
                "tighten_request_contract",
                "add_rollback_gate",
            ],
        }
    )
    ctx = Context(
        task_id="workflow-failure-modes-task",
        run_id="run-1",
        workflow_name="workflow_run_history_to_failure_modes",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=tmp_path / "workflows" / "workflow_run_history_to_failure_modes",
        state=state,
        session_store=InMemorySessionStore(),
        workflow_params={
            "selected_workflow": "release_candidate_to_go_no_go",
            "task_title": state.task_title,
            "statuses": list(state.statuses),
            "max_runs": state.max_runs,
        },
    )

    (workflow_folder / "diagnostic_scope_brief.md").write_text(
        "\n".join(
            (
                "# Diagnostic Scope Brief",
                "",
                "Selected workflow: `release_candidate_to_go_no_go`.",
                "Terminal outcome: publish a reusable diagnostic package and receipt.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "run_history_scope.md").write_text(
        "\n".join(
            (
                "# Run History Scope",
                "",
                f"- Filtered run IDs: {', '.join(run_ids) if run_ids else 'none captured'}.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "failure_mode_map.md").write_text(
        "\n".join(
            (
                "# Failure Mode Map",
                "",
                "## clarification_loops",
                "- Evidence shows ownership and rollback questions stay unresolved too long.",
                "",
                "## rollback_evidence_gaps",
                "- Evidence shows rollback readiness is still missing during assessment.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "recurring_weak_points.md").write_text(
        "\n".join(
            (
                "# Recurring Weak Points",
                "",
                "## request_contract_drift",
                "- Inputs are not explicit enough early in the release workflow.",
                "",
                "## downstream_evidence_gap",
                "- Child evidence gathering does not guarantee a durable rollback artifact.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "improvement_opportunities.md").write_text(
        "\n".join(
            (
                "# Improvement Opportunities",
                "",
                "## tighten_request_contract",
                "- Priority: P1.",
                "",
                "## add_rollback_gate",
                "- Priority: P1.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "diagnostic_next_actions.md").write_text(
        "\n".join(
            (
                "# Diagnostic Next Actions",
                "",
                "- Publication boundary: `diagnostic_publication_only`.",
                "- Use refinement to address the P1 opportunities later.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_payload = {
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "evidence_run_ids": list(run_ids),
        "failure_mode_ids": [
            "clarification_loops",
            "rollback_evidence_gaps",
        ],
        "failure_modes": [
            {
                "failure_mode_id": "clarification_loops",
                "title": "Clarification loops stall decision publication",
                "severity": "high",
                "evidence_run_ids": run_ids[:2] if len(run_ids) >= 2 else list(run_ids),
                "symptom_pattern": "Runs stall around unresolved release ownership and rollback approval questions.",
                "likely_causes": [
                    "The release workflow allows unresolved ownership gaps to persist too long.",
                ],
                "supporting_signals": [
                    "Paused and blocked runs both stop after ownership clarification pressure.",
                ],
            },
            {
                "failure_mode_id": "rollback_evidence_gaps",
                "title": "Rollback evidence gaps survive into terminal decision work",
                "severity": "high",
                "evidence_run_ids": run_ids[1:] if len(run_ids) >= 2 else list(run_ids),
                "symptom_pattern": "Runs progress into assessment with rollback evidence still incomplete.",
                "likely_causes": [
                    "Rollback readiness is treated as downstream evidence instead of a framing-time gate.",
                ],
                "supporting_signals": [
                    "Blocked and failed runs both lacked durable rollback-readiness evidence.",
                ],
            },
        ],
        "recurring_weak_point_ids": [
            "request_contract_drift",
            "downstream_evidence_gap",
        ],
        "workflow_name": "workflow_run_history_to_failure_modes",
    }
    if manifest_overrides:
        manifest_payload.update(manifest_overrides)
    (workflow_folder / "failure_mode_manifest.json").write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary_payload = {
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "evidence_run_ids": list(run_ids),
        "failure_mode_ids": [
            "clarification_loops",
            "rollback_evidence_gaps",
        ],
        "ranked_opportunity_ids": [
            "tighten_request_contract",
            "add_rollback_gate",
        ],
        "opportunities": [
            {
                "opportunity_id": "tighten_request_contract",
                "title": "Tighten the release-request framing contract before evidence assembly starts",
                "priority": "P1",
                "linked_failure_mode_ids": ["clarification_loops"],
                "recommended_next_step": "workflow_and_eval_to_refined_workflow_package",
                "why_now": "The paused and blocked runs show that the workflow keeps paying clarification cost late in the cycle.",
                "expected_impact": "Reduces blocked and paused runs caused by missing release ownership and rollback-approval inputs.",
            },
            {
                "opportunity_id": "add_rollback_gate",
                "title": "Add an explicit rollback-evidence gate before assessment and packaging",
                "priority": "P1",
                "linked_failure_mode_ids": ["rollback_evidence_gaps"],
                "recommended_next_step": "workflow_and_eval_to_refined_workflow_package",
                "why_now": "The failed run shows the release workflow can reach terminal work without a durable rollback artifact.",
                "expected_impact": "Prevents assessment from proceeding without explicit rollback-readiness evidence.",
            },
        ],
        "authoritative_artifacts": [
            "improvement_opportunities",
            "improvement_opportunities_summary",
            "diagnostic_next_actions",
            "failure_mode_map",
            "failure_mode_manifest",
            "recurring_weak_points",
        ],
        "next_action": "Recommend a refinement pass and rerun this diagnostic later.",
        "publication_boundary": "diagnostic_publication_only",
        "ready_for_publication": True,
        "workflow_name": "workflow_run_history_to_failure_modes",
    }
    if summary_overrides:
        summary_payload.update(summary_overrides)
    (workflow_folder / "improvement_opportunities.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return workflow_pkg, state, ctx


def _install_repo_workflow_run_history_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
        "workflow_run_history_to_failure_modes",
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


def _seed_release_run_history(root: Path, *, include_matching_failures: bool = True) -> None:
    if include_matching_failures:
        _write_run_history_record(
            root,
            task_id="release-alpha",
            workflow_name="release_candidate_to_go_no_go",
            run_id="run-release-failed",
            status="failed",
            created_at="2026-04-21T10:00:00+00:00",
            updated_at="2026-04-21T10:20:00+00:00",
            request_text="Ship release 2026.05 even though rollback evidence is incomplete.\n",
            events=[
                {"event_type": "run_started", "seq": 1},
                {"event_type": "step_executed", "seq": 2, "step_name": "assess_go_no_go"},
                {"event_type": "run_finished", "seq": 3, "status": "failed"},
            ],
            children=[
                {
                    "workflow_name": "investigation_request_to_evidence_pack",
                    "run_id": "child-investigation-0",
                    "status": "FAILED",
                    "terminal": "FAIL",
                }
            ],
            workflow_params={"release_name": "2026.05", "deployment_environment": "production"},
            terminal="FAIL",
            error="Rollback readiness was never published.",
        )
        _write_run_history_record(
            root,
            task_id="release-beta",
            workflow_name="release_candidate_to_go_no_go",
            run_id="run-release-blocked",
            status="blocked",
            created_at="2026-04-22T09:00:00+00:00",
            updated_at="2026-04-22T09:15:00+00:00",
            request_text="Ship release 2026.06 while ownership and evidence are still in flux.\n",
            events=[
                {"event_type": "run_started", "seq": 1},
                {"event_type": "step_executed", "seq": 2, "step_name": "assemble_evidence_pack"},
                {"event_type": "run_finished", "seq": 3, "status": "blocked"},
            ],
            children=[
                {
                    "workflow_name": "investigation_request_to_evidence_pack",
                    "run_id": "child-investigation-1",
                    "status": "success",
                    "terminal": "FINISH",
                }
            ],
            workflow_params={"release_name": "2026.06", "deployment_environment": "production"},
            terminal="PAUSE",
        )
        _write_run_history_record(
            root,
            task_id="release-gamma",
            workflow_name="release_candidate_to_go_no_go",
            run_id="run-release-paused",
            status="paused",
            created_at="2026-04-23T08:00:00+00:00",
            updated_at="2026-04-23T08:10:00+00:00",
            request_text="Ship release 2026.07 while rollback ownership is unresolved.\n",
            events=[
                {"event_type": "run_started", "seq": 1},
                {"event_type": "step_executed", "seq": 2, "step_name": "frame_release"},
                {"event_type": "run_finished", "seq": 3, "status": "paused"},
            ],
            parent_record={
                "task_id": "ops-program",
                "workflow_name": "task_to_workflow_strategy",
                "run_id": "run-parent",
                "task_folder": ".autoloop/tasks/ops-program",
                "workflow_folder": ".autoloop/tasks/ops-program/wf_task_to_workflow_strategy",
                "run_folder": ".autoloop/tasks/ops-program/wf_task_to_workflow_strategy/runs/run-parent",
            },
            workflow_params={"release_name": "2026.07", "deployment_environment": "production"},
            terminal="PAUSE",
            pending_question="Who owns rollback approval for release 2026.07?",
        )
    _write_run_history_record(
        root,
        task_id="release-delta",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-release-success",
        status="success",
        created_at="2026-04-24T07:00:00+00:00",
        updated_at="2026-04-24T07:15:00+00:00",
        request_text="Ship release 2026.08 after a routine readiness review.\n",
        events=[
            {"event_type": "run_started", "seq": 1},
            {"event_type": "run_finished", "seq": 2, "status": "success"},
        ],
        workflow_params={"release_name": "2026.08", "deployment_environment": "production"},
        terminal="FINISH",
    )
    _write_run_history_record(
        root,
        task_id="security-task",
        workflow_name="security_finding_to_verified_remediation",
        run_id="run-security-failed",
        status="failed",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:05:00+00:00",
        request_text="Pentest found privilege escalation in admin impersonation.\n",
        events=[
            {"event_type": "run_started", "seq": 1},
            {"event_type": "run_finished", "seq": 2, "status": "failed"},
        ],
        workflow_params={"finding_title": "Admin impersonation privilege escalation"},
        terminal="FAIL",
    )


def _write_run_history_record(
    root: Path,
    *,
    task_id: str,
    workflow_name: str,
    run_id: str,
    status: str,
    created_at: str,
    updated_at: str,
    request_text: str,
    events: list[dict[str, object]] | None = None,
    children: list[dict[str, object]] | None = None,
    parent_record: dict[str, object] | None = None,
    workflow_params: dict[str, object] | None = None,
    terminal: str | None = None,
    error: str | None = None,
    pending_question: str | None = None,
) -> None:
    task_dir = root / ".autoloop" / "tasks" / task_id
    workflow_dir = task_dir / f"wf_{workflow_name}"
    run_dir = workflow_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "request.md").write_text(request_text, encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in (events or [])),
        encoding="utf-8",
    )
    (run_dir / "children.jsonl").write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in (children or [])),
        encoding="utf-8",
    )
    if parent_record is not None:
        (run_dir / "parent.json").write_text(
            json.dumps(parent_record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    payload = {
        "created_at": created_at,
        "package_folder": str(Path("workflows") / workflow_name),
        "request_file": str(Path(".autoloop") / "tasks" / task_id / f"wf_{workflow_name}" / "runs" / run_id / "request.md"),
        "run_folder": str(Path(".autoloop") / "tasks" / task_id / f"wf_{workflow_name}" / "runs" / run_id),
        "run_id": run_id,
        "status": status,
        "task_folder": str(Path(".autoloop") / "tasks" / task_id),
        "task_id": task_id,
        "updated_at": updated_at,
        "workflow_folder": str(Path(".autoloop") / "tasks" / task_id / f"wf_{workflow_name}"),
        "workflow_name": workflow_name,
        "workflow_params": dict(workflow_params or {}),
    }
    if terminal is not None:
        payload["terminal"] = terminal
    if error is not None:
        payload["error"] = error
    if pending_question is not None:
        payload["pending_question"] = pending_question
    (run_dir / "run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
