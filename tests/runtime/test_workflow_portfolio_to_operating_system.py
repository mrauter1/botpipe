from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.context import Context
from autoloop_v3.core.providers.fake import ScriptedLLMProvider
from autoloop_v3.core.stores import InMemorySessionStore
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


def test_repo_workflows_namespace_discovers_workflow_portfolio_to_operating_system_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "workflow_portfolio_to_operating_system" in discovered
    package = discovered["workflow_portfolio_to_operating_system"]
    assert package.package_name == "workflow_portfolio_to_operating_system"
    assert "portfolio-operating-system" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "workflows" / "workflow_portfolio_to_operating_system" / "workflow.toml"
    )


def test_workflow_portfolio_to_operating_system_compiles_with_explicit_control_contracts(
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_portfolio_to_operating_system")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.WorkflowPortfolioToOperatingSystem)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "capture_portfolio_context",
        "frame_portfolio_governance",
        "analyze_portfolio_operating_model",
        "package_portfolio_operating_system",
        "publish_portfolio_operating_system",
    )

    frame_step = compiled.steps["frame_portfolio_governance"]
    assert frame_step.available_routes == (
        "portfolio_governance_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert frame_step.route_contracts["portfolio_governance_framed"]["required_artifacts"] == [
        "portfolio_governance_brief",
        "portfolio_decision_criteria",
    ]
    assert frame_step.expected_output_schema is not None

    analysis_step = compiled.steps["analyze_portfolio_operating_model"]
    assert analysis_step.route_contracts["portfolio_operating_model_analyzed"]["required_artifacts"] == [
        "workflow_lifecycle_matrix",
        "portfolio_gap_analysis",
        "portfolio_change_candidates",
    ]
    assert analysis_step.expected_output_schema is not None

    package_step = compiled.steps["package_portfolio_operating_system"]
    assert package_step.route_contracts["portfolio_operating_system_ready"]["required_artifacts"] == [
        "workflow_portfolio_operating_system",
        "portfolio_operating_summary",
        "portfolio_next_actions",
    ]
    assert package_step.expected_output_schema is not None
    assert set(package_step.expected_output_schema["required"]) >= {
        "summary",
        "focus_workflows",
        "analyzed_workflows",
        "change_candidate_ids",
        "priority_workflows",
        "authoritative_artifacts",
        "next_action",
        "publication_boundary",
        "ready_for_publication",
    }

    publish_step = compiled.steps["publish_portfolio_operating_system"]
    assert publish_step.requires == (
        "workflow_capability_snapshot",
        "workflow_portfolio_health_snapshot",
        "workflow_lifecycle_matrix",
        "portfolio_gap_analysis",
        "portfolio_change_candidates",
        "workflow_portfolio_operating_system",
        "portfolio_operating_summary",
        "portfolio_next_actions",
    )


def test_workflow_portfolio_to_operating_system_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "workflow_portfolio_to_operating_system.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_workflow_portfolio_to_operating_system.py",
    ):
        assert required in text


def test_workflow_portfolio_to_operating_system_prompt_readme_uses_shared_contract_sections() -> None:
    text = (
        REPO_ROOT / "workflows" / "workflow_portfolio_to_operating_system" / "prompts" / "README.md"
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
        "`portfolio_governance_framed`",
        "`portfolio_operating_model_analyzed`",
        "`portfolio_operating_system_ready`",
        "`needs_rework`",
        "`needs_replan`",
        "`frame_producer.md` / `frame_verifier.md`",
        "PortfolioOperatingSystemPayload",
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
                "`workflow_portfolio_health_snapshot`",
                "`portfolio_governance_brief`",
                "`portfolio_decision_criteria`",
                "`portfolio_governance_framed`",
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
                "Do not overwrite `portfolio_governance_brief` or `portfolio_decision_criteria` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`portfolio_governance_framed`",
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
                "`workflow_lifecycle_matrix`",
                "`portfolio_gap_analysis`",
                "`portfolio_change_candidates`",
                "`portfolio_operating_model_analyzed`",
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
                "Do not overwrite `workflow_lifecycle_matrix`, `portfolio_gap_analysis`, or `portfolio_change_candidates` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`portfolio_operating_model_analyzed`",
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
                "`workflow_portfolio_operating_system`",
                "`portfolio_operating_summary`",
                "`portfolio_next_actions`",
                "`portfolio_operating_system_receipt.json`",
                "`portfolio_operating_system_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`operating_system_publication_only`",
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
                "Do not overwrite `workflow_portfolio_operating_system`, `portfolio_operating_summary`, or `portfolio_next_actions` during verification.",
                "Do not create `portfolio_operating_system_receipt.json` in this step.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`portfolio_operating_system_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`operating_system_publication_only`",
                "Use reserved routes only",
            ),
        ),
    ),
)
def test_workflow_portfolio_to_operating_system_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (
        REPO_ROOT / "workflows" / "workflow_portfolio_to_operating_system" / "prompts" / prompt_name
    ).read_text(encoding="utf-8")

    for marker in required_markers:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"


def test_workflow_portfolio_to_operating_system_rejects_blank_task_title(tmp_path: Path) -> None:
    _install_repo_workflow_portfolio_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "workflow_portfolio_to_operating_system").parameters_cls

    with pytest.raises(WorkflowParameterError, match="task_title"):
        coerce_workflow_parameter_mapping(parameters_cls, {"task_title": "   "})


def test_workflow_portfolio_to_operating_system_normalizes_repeatable_inputs(tmp_path: Path) -> None:
    _install_repo_workflow_portfolio_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "workflow_portfolio_to_operating_system").parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "task_title": " Workflow portfolio operating-system review ",
            "sponsor_role": " Workflow Platform ",
            "desired_outcome": " ",
            "decision_drivers": [
                " prioritize recursive leverage ",
                "",
                "prioritize recursive leverage",
                "Prefer reusable governance pressure over hidden automation.",
            ],
            "constraints": [
                " keep runtime control narrow ",
                "",
                "keep runtime control narrow",
                "Stop at governance publication.",
            ],
            "focus_workflows": [
                " workflow_idea_to_workflow_package ",
                "",
                "task_to_workflow_strategy",
                "workflow_idea_to_workflow_package",
            ],
            "max_runs_per_workflow": 12,
        },
    )

    assert normalized == {
        "constraints": [
            "keep runtime control narrow",
            "Stop at governance publication.",
        ],
        "decision_drivers": [
            "prioritize recursive leverage",
            "Prefer reusable governance pressure over hidden automation.",
        ],
        "desired_outcome": None,
        "focus_workflows": [
            "workflow_idea_to_workflow_package",
            "task_to_workflow_strategy",
        ],
        "max_runs_per_workflow": 12,
        "sponsor_role": "Workflow Platform",
        "task_title": "Workflow portfolio operating-system review",
    }


def test_workflow_portfolio_to_operating_system_runs_and_publishes_terminal_governance_artifacts(
    tmp_path: Path,
) -> None:
    _install_repo_workflow_portfolio_package(tmp_path)
    seeded_paths = _seed_portfolio_run_health(tmp_path)

    provider = ScriptedLLMProvider(
        producer_turns=[
            _produce_governance_frame,
            _produce_operating_model,
            _produce_operating_package,
        ],
        verifier_turns=[
            Outcome(
                raw_output="portfolio governance framed\n",
                tag="portfolio_governance_framed",
                payload={
                    "summary": "The scope, sponsor pressure, and lifecycle criteria are explicit enough for portfolio analysis.",
                    "focus_workflows": [
                        "task_to_workflow_strategy",
                        "workflow_idea_to_workflow_package",
                        "workflow_run_history_to_failure_modes",
                    ],
                    "authoritative_artifacts": [
                        "portfolio_governance_brief",
                        "portfolio_decision_criteria",
                    ],
                    "decision_axes": [
                        "recursive leverage",
                        "run-health pressure",
                        "reuse versus decomposition",
                    ],
                },
            ),
            Outcome(
                raw_output="portfolio operating model analyzed\n",
                tag="portfolio_operating_model_analyzed",
                payload={
                    "summary": "The scoped portfolio now has explicit lifecycle recommendations and governance change candidates.",
                    "focus_workflows": [
                        "task_to_workflow_strategy",
                        "workflow_idea_to_workflow_package",
                        "workflow_run_history_to_failure_modes",
                    ],
                    "analyzed_workflows": [
                        "task_to_workflow_strategy",
                        "workflow_idea_to_workflow_package",
                        "workflow_run_history_to_failure_modes",
                    ],
                    "lifecycle_recommendations": [
                        {
                            "workflow_name": "task_to_workflow_strategy",
                            "lifecycle_posture": "refine",
                            "priority": "P1",
                        },
                        {
                            "workflow_name": "workflow_idea_to_workflow_package",
                            "lifecycle_posture": "keep",
                            "priority": "P2",
                        },
                        {
                            "workflow_name": "workflow_run_history_to_failure_modes",
                            "lifecycle_posture": "keep",
                            "priority": "P2",
                        },
                    ],
                    "change_candidate_ids": [
                        "refine_task_to_workflow_strategy",
                        "create_workflow_package_to_composable_building_blocks",
                    ],
                },
            ),
            Outcome(
                raw_output="portfolio operating system ready\n",
                tag="portfolio_operating_system_ready",
                payload={
                    "summary": "The governance package, summary, and next actions are aligned and ready for publication.",
                    "focus_workflows": [
                        "task_to_workflow_strategy",
                        "workflow_idea_to_workflow_package",
                        "workflow_run_history_to_failure_modes",
                    ],
                    "analyzed_workflows": [
                        "task_to_workflow_strategy",
                        "workflow_idea_to_workflow_package",
                        "workflow_run_history_to_failure_modes",
                    ],
                    "change_candidate_ids": [
                        "refine_task_to_workflow_strategy",
                        "create_workflow_package_to_composable_building_blocks",
                    ],
                    "priority_workflows": ["task_to_workflow_strategy"],
                    "authoritative_artifacts": [
                        "workflow_portfolio_operating_system",
                        "portfolio_operating_summary",
                        "portfolio_next_actions",
                        "workflow_lifecycle_matrix",
                        "portfolio_gap_analysis",
                        "portfolio_change_candidates",
                    ],
                    "next_action": "Hand this governance package to workflow_and_eval_to_refined_workflow_package for `task_to_workflow_strategy`, then queue `workflow_idea_to_workflow_package` for `workflow_package_to_composable_building_blocks` as a separate follow-on.",
                    "publication_boundary": "operating_system_publication_only",
                    "ready_for_publication": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "workflow_portfolio_to_operating_system",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="portfolio-governance-task",
            message="Recommend how the current workflow portfolio should evolve for the next recursive cycle.",
            workflow_params={
                "task_title": "Workflow portfolio operating-system review",
                "sponsor_role": "workflow platform",
                "desired_outcome": "Publish a governance package with explicit lifecycle recommendations and next actions.",
                "decision_drivers": [
                    "Prioritize recursive leverage and reusable value.",
                    "Keep governance explicit instead of runtime-owned automation.",
                ],
                "constraints": [
                    "Keep runtime control narrow.",
                    "Stop at governance publication.",
                ],
                "focus_workflows": [
                    "workflow_idea_to_workflow_package",
                    "task_to_workflow_strategy",
                    "workflow_run_history_to_failure_modes",
                ],
                "max_runs_per_workflow": 2,
            },
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "portfolio-governance-task"
    workflow_dir = task_dir / "wf_workflow_portfolio_to_operating_system"
    run_dir = next((workflow_dir / "runs").iterdir())

    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    capability_snapshot = json.loads((workflow_dir / "workflow_capability_snapshot.json").read_text(encoding="utf-8"))
    health_snapshot = json.loads((workflow_dir / "workflow_portfolio_health_snapshot.json").read_text(encoding="utf-8"))
    operating_summary = json.loads((workflow_dir / "portfolio_operating_summary.json").read_text(encoding="utf-8"))
    operating_receipt = json.loads((workflow_dir / "portfolio_operating_system_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "SUCCESS"
    assert (workflow_dir / "workflow_capability_snapshot.json").exists()
    assert (workflow_dir / "workflow_portfolio_health_snapshot.json").exists()
    assert (workflow_dir / "portfolio_governance_brief.md").exists()
    assert (workflow_dir / "portfolio_decision_criteria.md").exists()
    assert (workflow_dir / "workflow_lifecycle_matrix.md").exists()
    assert (workflow_dir / "portfolio_gap_analysis.md").exists()
    assert (workflow_dir / "portfolio_change_candidates.json").exists()
    assert (workflow_dir / "workflow_portfolio_operating_system.md").exists()
    assert (workflow_dir / "portfolio_operating_summary.json").exists()
    assert (workflow_dir / "portfolio_next_actions.md").exists()
    assert (workflow_dir / "portfolio_operating_system_receipt.json").exists()
    assert sorted(path.name for path in task_dir.glob("wf_*")) == ["wf_workflow_portfolio_to_operating_system"]
    children_file = run_dir / "children.jsonl"
    assert (not children_file.exists()) or children_file.read_text(encoding="utf-8") == ""

    assert invocation_contract == {
        "constraints": [
            "Keep runtime control narrow.",
            "Stop at governance publication.",
        ],
        "decision_drivers": [
            "Prioritize recursive leverage and reusable value.",
            "Keep governance explicit instead of runtime-owned automation.",
        ],
        "desired_outcome": "Publish a governance package with explicit lifecycle recommendations and next actions.",
        "focus_workflow_references": [
            "workflow_idea_to_workflow_package",
            "task_to_workflow_strategy",
            "workflow_run_history_to_failure_modes",
        ],
        "max_runs_per_workflow": 2,
        "message": "Recommend how the current workflow portfolio should evolve for the next recursive cycle.\n",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "sponsor_role": "workflow platform",
        "task_id": "portfolio-governance-task",
        "task_title": "Workflow portfolio operating-system review",
        "workflow_name": "workflow_portfolio_to_operating_system",
    }
    assert capability_snapshot["workflow_count"] == 5
    assert {entry["workflow_name"] for entry in capability_snapshot["workflows"]} == {
        "task_to_candidate_workflow_set",
        "task_to_workflow_strategy",
        "workflow_idea_to_workflow_package",
        "workflow_portfolio_to_operating_system",
        "workflow_run_history_to_failure_modes",
    }
    assert health_snapshot["repo_root"] == str(tmp_path.resolve())
    assert health_snapshot["run_id"] == run_dir.name
    assert health_snapshot["task_id"] == "portfolio-governance-task"
    assert health_snapshot["workflow_name"] == "workflow_portfolio_to_operating_system"
    assert health_snapshot["workflow_portfolio_health"]["max_runs_per_workflow"] == 2
    assert health_snapshot["workflow_portfolio_health"]["selected_workflow_names"] == [
        "task_to_workflow_strategy",
        "workflow_idea_to_workflow_package",
        "workflow_run_history_to_failure_modes",
    ]
    assert health_snapshot["workflow_portfolio_health"]["statuses"] is None
    assert health_snapshot["workflow_portfolio_health"]["workflow_count"] == 3

    health_by_workflow = {
        entry["workflow_name"]: entry for entry in health_snapshot["workflow_portfolio_health"]["workflows"]
    }
    assert set(health_by_workflow) == {
        "task_to_workflow_strategy",
        "workflow_idea_to_workflow_package",
        "workflow_run_history_to_failure_modes",
    }

    strategy_health = health_by_workflow["task_to_workflow_strategy"]
    assert strategy_health["title"] == "Task To Workflow Strategy"
    assert strategy_health["latest_run_id"] == "run-strategy-paused"
    assert strategy_health["latest_updated_at"] == "2026-04-24T08:10:00+00:00"
    assert strategy_health["run_count"] == 2
    assert strategy_health["status_counts"] == {"failed": 1, "paused": 1}
    assert strategy_health["recent_runs"] == [
        {
            "created_at": "2026-04-24T08:00:00+00:00",
            "error": None,
            "pending_question": "Should strategy adapt or compose next?",
            "request_excerpt": "Decide whether this initiative should reuse or create workflows.",
            "request_file": str(seeded_paths["strategy_paused"] / "request.md"),
            "run_folder": str(seeded_paths["strategy_paused"]),
            "run_id": "run-strategy-paused",
            "status": "paused",
            "task_id": "portfolio-alpha",
            "terminal": "PAUSE",
            "updated_at": "2026-04-24T08:10:00+00:00",
        },
        {
            "created_at": "2026-04-23T08:00:00+00:00",
            "error": "candidate package drift",
            "pending_question": None,
            "request_excerpt": "Re-evaluate the routing package after a failed governance review.",
            "request_file": str(seeded_paths["strategy_failed"] / "request.md"),
            "run_folder": str(seeded_paths["strategy_failed"]),
            "run_id": "run-strategy-failed",
            "status": "failed",
            "task_id": "portfolio-beta",
            "terminal": "FAIL",
            "updated_at": "2026-04-23T08:05:00+00:00",
        },
    ]
    assert "workflow-strategy" in strategy_health["aliases"]
    assert strategy_health["description"]

    builder_health = health_by_workflow["workflow_idea_to_workflow_package"]
    assert builder_health["title"] == "Workflow Idea To Workflow Package"
    assert builder_health["latest_run_id"] is None
    assert builder_health["latest_updated_at"] is None
    assert builder_health["recent_runs"] == []
    assert builder_health["run_count"] == 0
    assert builder_health["status_counts"] == {}
    assert "workflow-builder" in builder_health["aliases"]
    assert builder_health["description"]

    diagnostics_health = health_by_workflow["workflow_run_history_to_failure_modes"]
    assert diagnostics_health["title"] == "Workflow Run History To Failure Modes"
    assert diagnostics_health["latest_run_id"] == "run-diagnostics-success"
    assert diagnostics_health["latest_updated_at"] == "2026-04-24T07:40:00+00:00"
    assert diagnostics_health["run_count"] == 1
    assert diagnostics_health["status_counts"] == {"success": 1}
    assert diagnostics_health["recent_runs"] == [
        {
            "created_at": "2026-04-24T07:30:00+00:00",
            "error": None,
            "pending_question": None,
            "request_excerpt": "Publish workflow failure pressure for the release governance loop.",
            "request_file": str(seeded_paths["diagnostics_success"] / "request.md"),
            "run_folder": str(seeded_paths["diagnostics_success"]),
            "run_id": "run-diagnostics-success",
            "status": "success",
            "task_id": "portfolio-gamma",
            "terminal": "SUCCESS",
            "updated_at": "2026-04-24T07:40:00+00:00",
        }
    ]
    assert "workflow-failure-modes" in diagnostics_health["aliases"]
    assert diagnostics_health["description"]
    assert operating_summary == {
        "analyzed_workflows": [
            "task_to_workflow_strategy",
            "workflow_idea_to_workflow_package",
            "workflow_run_history_to_failure_modes",
        ],
        "authoritative_artifacts": [
            "workflow_portfolio_operating_system",
            "portfolio_operating_summary",
            "portfolio_next_actions",
            "workflow_lifecycle_matrix",
            "portfolio_gap_analysis",
            "portfolio_change_candidates",
        ],
        "change_candidate_ids": [
            "refine_task_to_workflow_strategy",
            "create_workflow_package_to_composable_building_blocks",
        ],
        "focus_workflows": [
            "task_to_workflow_strategy",
            "workflow_idea_to_workflow_package",
            "workflow_run_history_to_failure_modes",
        ],
        "governance_posture_counts": {
            "keep": 2,
            "refine": 1,
        },
        "lifecycle_recommendations": [
            {
                "lifecycle_posture": "refine",
                "priority": "P1",
                "workflow_name": "task_to_workflow_strategy",
            },
            {
                "lifecycle_posture": "keep",
                "priority": "P2",
                "workflow_name": "workflow_idea_to_workflow_package",
            },
            {
                "lifecycle_posture": "keep",
                "priority": "P2",
                "workflow_name": "workflow_run_history_to_failure_modes",
            },
        ],
        "next_action": "Hand this governance package to workflow_and_eval_to_refined_workflow_package for `task_to_workflow_strategy`, then queue `workflow_idea_to_workflow_package` for `workflow_package_to_composable_building_blocks` as a separate follow-on.",
        "priority_workflows": ["task_to_workflow_strategy"],
        "publication_boundary": "operating_system_publication_only",
        "ready_for_publication": True,
        "workflow_name": "workflow_portfolio_to_operating_system",
    }
    assert operating_receipt == {
        "analyzed_workflows": [
            "task_to_workflow_strategy",
            "workflow_idea_to_workflow_package",
            "workflow_run_history_to_failure_modes",
        ],
        "authoritative_artifacts": [
            "workflow_portfolio_operating_system",
            "portfolio_operating_summary",
            "portfolio_next_actions",
            "workflow_lifecycle_matrix",
            "portfolio_gap_analysis",
            "portfolio_change_candidates",
        ],
        "change_candidate_ids": [
            "refine_task_to_workflow_strategy",
            "create_workflow_package_to_composable_building_blocks",
        ],
        "desired_outcome": "Publish a governance package with explicit lifecycle recommendations and next actions.",
        "focus_workflows": [
            "task_to_workflow_strategy",
            "workflow_idea_to_workflow_package",
            "workflow_run_history_to_failure_modes",
        ],
        "lifecycle_postures": {
            "task_to_workflow_strategy": "refine",
            "workflow_idea_to_workflow_package": "keep",
            "workflow_run_history_to_failure_modes": "keep",
        },
        "next_action": "Hand this governance package to workflow_and_eval_to_refined_workflow_package for `task_to_workflow_strategy`, then queue `workflow_idea_to_workflow_package` for `workflow_package_to_composable_building_blocks` as a separate follow-on.",
        "portfolio_change_candidates": str(workflow_dir / "portfolio_change_candidates.json"),
        "portfolio_gap_analysis": str(workflow_dir / "portfolio_gap_analysis.md"),
        "portfolio_next_actions": str(workflow_dir / "portfolio_next_actions.md"),
        "portfolio_operating_summary": str(workflow_dir / "portfolio_operating_summary.json"),
        "priority_workflows": ["task_to_workflow_strategy"],
        "publication_boundary": "operating_system_publication_only",
        "published": True,
        "sponsor_role": "workflow platform",
        "task_title": "Workflow portfolio operating-system review",
        "workflow_capability_snapshot": str(workflow_dir / "workflow_capability_snapshot.json"),
        "workflow_lifecycle_matrix": str(workflow_dir / "workflow_lifecycle_matrix.md"),
        "workflow_name": "workflow_portfolio_to_operating_system",
        "workflow_portfolio_health_snapshot": str(workflow_dir / "workflow_portfolio_health_snapshot.json"),
        "workflow_portfolio_operating_system": str(workflow_dir / "workflow_portfolio_operating_system.md"),
    }
    assert [call.step_name for call in provider.calls] == [
        "frame_portfolio_governance",
        "frame_portfolio_governance",
        "analyze_portfolio_operating_model",
        "analyze_portfolio_operating_model",
        "package_portfolio_operating_system",
        "package_portfolio_operating_system",
    ]
    assert provider.calls[3].available_routes == (
        "portfolio_operating_model_analyzed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert provider.calls[5].route_contracts["portfolio_operating_system_ready"]["required_artifacts"] == [
        "workflow_portfolio_operating_system",
        "portfolio_operating_summary",
        "portfolio_next_actions",
    ]
    assert (run_dir / "run.json").exists()


@pytest.mark.parametrize("missing_filename", ["workflow_capability_snapshot.json", "workflow_portfolio_health_snapshot.json"])
def test_workflow_portfolio_to_operating_system_publish_rejects_missing_scoped_evidence_artifact(
    tmp_path: Path,
    monkeypatch,
    missing_filename: str,
) -> None:
    workflow_pkg, state, ctx = _make_publish_portfolio_operating_system_test_context(tmp_path, monkeypatch)
    (ctx.workflow_folder / missing_filename).unlink()

    with pytest.raises(FileNotFoundError, match="missing required publication artifact"):
        workflow_pkg.WorkflowPortfolioToOperatingSystem.on_publish_portfolio_operating_system(state, ctx)


def test_workflow_portfolio_to_operating_system_publish_rejects_unknown_focus_workflow_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_portfolio_operating_system_test_context(
        tmp_path,
        monkeypatch,
        focus_workflows=[
            "task_to_workflow_strategy",
            "unknown_workflow",
            "workflow_run_history_to_failure_modes",
        ],
        analyzed_workflows=[
            "task_to_workflow_strategy",
            "unknown_workflow",
            "workflow_run_history_to_failure_modes",
        ],
        lifecycle_postures={
            "task_to_workflow_strategy": "refine",
            "unknown_workflow": "keep",
            "workflow_run_history_to_failure_modes": "keep",
        },
    )

    with pytest.raises(ValueError, match="unknown focus-workflow references"):
        workflow_pkg.WorkflowPortfolioToOperatingSystem.on_publish_portfolio_operating_system(state, ctx)


def test_workflow_portfolio_to_operating_system_publish_rejects_summary_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_portfolio_operating_system_test_context(
        tmp_path,
        monkeypatch,
        summary_override={
            "governance_posture_counts": {
                "keep": 1,
                "refine": 2,
            }
        },
    )

    with pytest.raises(ValueError, match="must not drift from lifecycle_recommendations"):
        workflow_pkg.WorkflowPortfolioToOperatingSystem.on_publish_portfolio_operating_system(state, ctx)


def test_workflow_portfolio_to_operating_system_publish_rejects_invalid_lifecycle_posture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_portfolio_operating_system_test_context(
        tmp_path,
        monkeypatch,
        summary_override={
            "lifecycle_recommendations": [
                {
                    "workflow_name": "task_to_workflow_strategy",
                    "lifecycle_posture": "monitor",
                    "priority": "P1",
                },
                {
                    "workflow_name": "workflow_idea_to_workflow_package",
                    "lifecycle_posture": "keep",
                    "priority": "P2",
                },
                {
                    "workflow_name": "workflow_run_history_to_failure_modes",
                    "lifecycle_posture": "keep",
                    "priority": "P2",
                },
            ]
        },
    )

    with pytest.raises(ValueError, match="legal lifecycle_posture"):
        workflow_pkg.WorkflowPortfolioToOperatingSystem.on_publish_portfolio_operating_system(state, ctx)


@pytest.mark.parametrize(
    "next_actions_text",
    (
        (
            "# Portfolio Next Actions\n\n"
            "Boundary: operating_system_publication_only.\n"
            "Automatically run workflow_and_eval_to_refined_workflow_package for task_to_workflow_strategy next.\n"
        ),
        (
            "# Portfolio Next Actions\n\n"
            "Boundary: operating_system_publication_only.\n"
            "The runtime queues workflow_and_eval_to_refined_workflow_package for task_to_workflow_strategy next.\n"
        ),
        (
            "# Portfolio Next Actions\n\n"
            "Boundary: operating_system_publication_only.\n"
            "This workflow will launch workflow_and_eval_to_refined_workflow_package after publication.\n"
        ),
        (
            "# Portfolio Next Actions\n\n"
            "Boundary: operating_system_publication_only.\n"
            "This package automatically queues the refinement workflow after publication.\n"
        ),
    ),
)
def test_workflow_portfolio_to_operating_system_publish_rejects_hidden_downstream_execution_in_next_actions(
    tmp_path: Path,
    monkeypatch,
    next_actions_text: str,
) -> None:
    workflow_pkg, state, ctx = _make_publish_portfolio_operating_system_test_context(
        tmp_path,
        monkeypatch,
        next_actions_text=next_actions_text,
    )

    with pytest.raises(ValueError, match="portfolio_next_actions.md must not imply hidden downstream execution"):
        workflow_pkg.WorkflowPortfolioToOperatingSystem.on_publish_portfolio_operating_system(state, ctx)


def test_workflow_portfolio_to_operating_system_publish_rejects_hidden_downstream_execution_in_summary_next_action(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_portfolio_operating_system_test_context(
        tmp_path,
        monkeypatch,
        summary_override={
            "next_action": "The runtime queues workflow_and_eval_to_refined_workflow_package for task_to_workflow_strategy next.",
        },
    )

    with pytest.raises(
        ValueError,
        match="portfolio_operating_summary.json next_action must not imply hidden downstream execution",
    ):
        workflow_pkg.WorkflowPortfolioToOperatingSystem.on_publish_portfolio_operating_system(state, ctx)


def test_workflow_portfolio_to_operating_system_publish_allows_explicit_negative_guardrails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_portfolio_operating_system_test_context(
        tmp_path,
        monkeypatch,
        summary_override={
            "next_action": "Keep downstream execution explicit and do not auto-run follow-on workflows from this package.",
        },
        next_actions_text=(
            "# Portfolio Next Actions\n\n"
            "Boundary: operating_system_publication_only.\n"
            "1. Keep downstream execution explicit and do not auto-run follow-on workflows from this package.\n"
            "2. Hand this package to workflow_and_eval_to_refined_workflow_package for task_to_workflow_strategy.\n"
        ),
    )

    next_state, event = workflow_pkg.WorkflowPortfolioToOperatingSystem.on_publish_portfolio_operating_system(state, ctx)

    assert event.tag == "portfolio_operating_system_published"
    assert next_state.published is True
    assert (ctx.workflow_folder / "portfolio_operating_system_receipt.json").exists()


def _produce_governance_frame(request) -> str:
    request.artifacts.portfolio_governance_brief.write_text(
        "\n".join(
            (
                "# Portfolio Governance Brief",
                "",
                "Scope workflows:",
                "- `task_to_workflow_strategy`",
                "- `workflow_idea_to_workflow_package`",
                "- `workflow_run_history_to_failure_modes`",
                "",
                "Sponsor: workflow platform.",
                "Why now: the front door is showing repeated stalled runs, the builder remains foundational, and the diagnostic layer is healthy enough to keep stable while governance pressure is added above it.",
                "Terminal package: explicit keep/refine/decompose/merge/retire/create-next recommendations plus next actions.",
                "Boundary: operating_system_publication_only.",
                "",
            )
        )
        + "\n",
    )
    request.artifacts.portfolio_decision_criteria.write_text(
        "\n".join(
            (
                "# Portfolio Decision Criteria",
                "",
                "- Prefer refine when a current workflow shows repeated run-health pressure but still solves a valuable job.",
                "- Prefer keep when the workflow remains foundational and the scoped evidence does not justify change.",
                "- Prefer decompose or merge only when explicit overlap or monolith pressure is visible in the scoped evidence.",
                "- Prefer retire only when the scoped workflow no longer serves a valuable distinct job.",
                "- Prefer create-next only when the scoped evidence exposes a durable missing capability worth its own package.",
                "",
            )
        )
        + "\n",
    )
    return "framed portfolio governance\n"


def _produce_operating_model(request) -> str:
    request.artifacts.workflow_lifecycle_matrix.write_text(
        "\n".join(
            (
                "# Workflow Lifecycle Matrix",
                "",
                "| Workflow | Lifecycle posture | Priority | Evidence |",
                "| --- | --- | --- | --- |",
                "| `task_to_workflow_strategy` | `refine` | `P1` | repeated paused and failed runs show routing pressure but the front door remains strategically valuable |",
                "| `workflow_idea_to_workflow_package` | `keep` | `P2` | no scoped run-health pressure and it remains the standing builder baseline |",
                "| `workflow_run_history_to_failure_modes` | `keep` | `P2` | recent successful diagnostics show the building block is healthy enough to stay stable this cycle |",
                "",
            )
        )
        + "\n",
    )
    request.artifacts.portfolio_gap_analysis.write_text(
        "\n".join(
            (
                "# Portfolio Gap Analysis",
                "",
                "- The portfolio now has builder, routing, and diagnostics layers, but it still lacks a reusable decomposition workflow that can turn operating-system pressure into extracted building blocks.",
                "- No merge or retire candidate is justified in the current scoped evidence; the strongest pressure is a refinement of the front door plus a create-next decomposition workflow.",
                "- The builder remains credible, so create-next pressure should route through the existing builder rather than inventing runtime-owned governance automation.",
                "",
            )
        )
        + "\n",
    )
    request.artifacts.portfolio_change_candidates.write_text(
        json.dumps(
            {
                "change_candidates": [
                    {
                        "candidate_id": "refine_task_to_workflow_strategy",
                        "action": "refine",
                        "priority": "P1",
                        "workflow_names": ["task_to_workflow_strategy"],
                        "why_now": "Repeated paused and failed routing runs show the front door still needs sharper candidate handoff and governance signaling.",
                        "evidence_sources": [
                            "workflow_capability_snapshot",
                            "workflow_portfolio_health_snapshot",
                        ],
                        "next_step_hint": "workflow_and_eval_to_refined_workflow_package",
                    },
                    {
                        "candidate_id": "create_workflow_package_to_composable_building_blocks",
                        "action": "create_next",
                        "priority": "P2",
                        "why_now": "The portfolio now has enough mature workflows that decomposition pressure is becoming explicit and should be turned into a reusable package.",
                        "evidence_sources": [
                            "workflow_capability_snapshot",
                            "portfolio_gap_analysis",
                        ],
                        "next_step_hint": "workflow_idea_to_workflow_package",
                        "proposed_workflow_name": "workflow_package_to_composable_building_blocks",
                    },
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return "analyzed portfolio operating model\n"


def _produce_operating_package(request) -> str:
    request.artifacts.workflow_portfolio_operating_system.write_text(
        "\n".join(
            (
                "# Workflow Portfolio Operating System",
                "",
                "This governance package turns scoped portfolio evidence into explicit lifecycle recommendations and next actions.",
                "",
                "## Keep",
                "- `workflow_idea_to_workflow_package` remains the standing builder baseline.",
                "- `workflow_run_history_to_failure_modes` stays stable while the front door is refined above it.",
                "",
                "## Refine",
                "- `task_to_workflow_strategy` should be refined first because repeated paused and failed runs show portfolio-routing pressure.",
                "",
                "## Decompose",
                "- None this cycle.",
                "",
                "## Merge",
                "- None this cycle.",
                "",
                "## Retire",
                "- None this cycle.",
                "",
                "## Create Next",
                "- `workflow_package_to_composable_building_blocks` should be authored next through the standing builder path.",
                "",
                "## Handoff Boundary",
                "- operating_system_publication_only",
                "",
            )
        )
        + "\n",
    )
    request.artifacts.portfolio_operating_summary.write_text(
        json.dumps(
            {
                "analyzed_workflows": [
                    "task_to_workflow_strategy",
                    "workflow_idea_to_workflow_package",
                    "workflow_run_history_to_failure_modes",
                ],
                "authoritative_artifacts": [
                    "workflow_portfolio_operating_system",
                    "portfolio_operating_summary",
                    "portfolio_next_actions",
                    "workflow_lifecycle_matrix",
                    "portfolio_gap_analysis",
                    "portfolio_change_candidates",
                ],
                "change_candidate_ids": [
                    "refine_task_to_workflow_strategy",
                    "create_workflow_package_to_composable_building_blocks",
                ],
                "focus_workflows": [
                    "task_to_workflow_strategy",
                    "workflow_idea_to_workflow_package",
                    "workflow_run_history_to_failure_modes",
                ],
                "governance_posture_counts": {
                    "keep": 2,
                    "refine": 1,
                },
                "lifecycle_recommendations": [
                    {
                        "workflow_name": "task_to_workflow_strategy",
                        "lifecycle_posture": "refine",
                        "priority": "P1",
                    },
                    {
                        "workflow_name": "workflow_idea_to_workflow_package",
                        "lifecycle_posture": "keep",
                        "priority": "P2",
                    },
                    {
                        "workflow_name": "workflow_run_history_to_failure_modes",
                        "lifecycle_posture": "keep",
                        "priority": "P2",
                    },
                ],
                "next_action": "Hand this governance package to workflow_and_eval_to_refined_workflow_package for `task_to_workflow_strategy`, then queue `workflow_idea_to_workflow_package` for `workflow_package_to_composable_building_blocks` as a separate follow-on.",
                "priority_workflows": ["task_to_workflow_strategy"],
                "publication_boundary": "operating_system_publication_only",
                "ready_for_publication": True,
                "workflow_name": "workflow_portfolio_to_operating_system",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    request.artifacts.portfolio_next_actions.write_text(
        "\n".join(
            (
                "# Portfolio Next Actions",
                "",
                "Boundary: operating_system_publication_only.",
                "1. Hand this package to `workflow_and_eval_to_refined_workflow_package` for `task_to_workflow_strategy`.",
                "2. Hand the create-next recommendation to `workflow_idea_to_workflow_package` for `workflow_package_to_composable_building_blocks`.",
                "3. Re-run this governance workflow after the refined front door and the new decomposition package have evaluation evidence.",
                "",
            )
        )
        + "\n",
    )
    return "packaged operating system\n"


def _make_publish_portfolio_operating_system_test_context(
    tmp_path: Path,
    monkeypatch,
    *,
    focus_workflows: list[str] | None = None,
    analyzed_workflows: list[str] | None = None,
    lifecycle_postures: dict[str, str] | None = None,
    change_candidate_ids: list[str] | None = None,
    priority_workflows: list[str] | None = None,
    summary_override: dict[str, object] | None = None,
    next_actions_text: str | None = None,
) -> tuple[object, object, Context]:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_portfolio_to_operating_system")

    focus_workflows = list(
        focus_workflows
        or [
            "task_to_workflow_strategy",
            "workflow_idea_to_workflow_package",
            "workflow_run_history_to_failure_modes",
        ]
    )
    analyzed_workflows = list(analyzed_workflows or focus_workflows)
    lifecycle_postures = dict(
        lifecycle_postures
        or {
            "task_to_workflow_strategy": "refine",
            "workflow_idea_to_workflow_package": "keep",
            "workflow_run_history_to_failure_modes": "keep",
        }
    )
    change_candidate_ids = list(
        change_candidate_ids
        or [
            "refine_task_to_workflow_strategy",
            "create_workflow_package_to_composable_building_blocks",
        ]
    )
    priority_workflows = list(priority_workflows or ["task_to_workflow_strategy"])

    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_workflow_portfolio_to_operating_system"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)

    (workflow_folder / "workflow_capability_snapshot.json").write_text(
        json.dumps(
            {
                "workflow_count": 4,
                "workflows": [
                    {"workflow_name": "workflow_portfolio_to_operating_system"},
                    {"workflow_name": "task_to_workflow_strategy"},
                    {"workflow_name": "workflow_idea_to_workflow_package"},
                    {"workflow_name": "workflow_run_history_to_failure_modes"},
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "workflow_portfolio_health_snapshot.json").write_text(
        json.dumps(
            {
                "workflow_portfolio_health": {
                    "max_runs_per_workflow": 2,
                    "selected_workflow_names": focus_workflows,
                    "statuses": None,
                    "workflow_count": len(focus_workflows),
                    "workflows": [
                        {
                            "workflow_name": workflow_name,
                            "run_count": 0,
                            "status_counts": {},
                            "recent_runs": [],
                        }
                        for workflow_name in focus_workflows
                    ],
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "workflow_lifecycle_matrix.md").write_text(
        "\n".join(
            [
                "# Workflow Lifecycle Matrix",
                "",
                *[
                    f"- `{workflow_name}` -> `{lifecycle_postures[workflow_name]}`"
                    for workflow_name in analyzed_workflows
                ],
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "portfolio_gap_analysis.md").write_text(
        "# Portfolio Gap Analysis\n\n- The scoped portfolio still needs an explicit decomposition follow-on.\n",
        encoding="utf-8",
    )
    (workflow_folder / "portfolio_change_candidates.json").write_text(
        json.dumps(
            {
                "change_candidates": [
                    {
                        "candidate_id": change_candidate_ids[0],
                        "action": "refine",
                        "priority": "P1",
                        "workflow_names": ["task_to_workflow_strategy"],
                        "why_now": "The front door keeps stalling.",
                        "evidence_sources": [
                            "workflow_capability_snapshot",
                            "workflow_portfolio_health_snapshot",
                        ],
                        "next_step_hint": "workflow_and_eval_to_refined_workflow_package",
                    },
                    {
                        "candidate_id": change_candidate_ids[1],
                        "action": "create_next",
                        "priority": "P2",
                        "why_now": "The portfolio has explicit decomposition pressure.",
                        "evidence_sources": [
                            "portfolio_gap_analysis",
                            "workflow_capability_snapshot",
                        ],
                        "next_step_hint": "workflow_idea_to_workflow_package",
                        "proposed_workflow_name": "workflow_package_to_composable_building_blocks",
                    },
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "workflow_portfolio_operating_system.md").write_text(
        "\n".join(
            (
                "# Workflow Portfolio Operating System",
                "",
                "## Keep",
                "- `workflow_idea_to_workflow_package`.",
                "",
                "## Refine",
                "- `task_to_workflow_strategy`.",
                "",
                "## Decompose",
                "- None this cycle.",
                "",
                "## Merge",
                "- None this cycle.",
                "",
                "## Retire",
                "- None this cycle.",
                "",
                "## Create Next",
                "- `workflow_package_to_composable_building_blocks`.",
                "",
                "## Handoff Boundary",
                "- operating_system_publication_only",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    summary = {
        "analyzed_workflows": analyzed_workflows,
        "authoritative_artifacts": [
            "workflow_portfolio_operating_system",
            "portfolio_operating_summary",
            "portfolio_next_actions",
            "workflow_lifecycle_matrix",
            "portfolio_gap_analysis",
            "portfolio_change_candidates",
        ],
        "change_candidate_ids": change_candidate_ids,
        "focus_workflows": focus_workflows,
        "governance_posture_counts": {
            "keep": 2,
            "refine": 1,
        },
        "lifecycle_recommendations": [
            {
                "workflow_name": workflow_name,
                "lifecycle_posture": lifecycle_postures[workflow_name],
                "priority": "P1" if workflow_name == "task_to_workflow_strategy" else "P2",
            }
            for workflow_name in analyzed_workflows
        ],
        "next_action": "Hand this package to workflow_and_eval_to_refined_workflow_package for the front door, then author the decomposition workflow as a separate follow-on.",
        "priority_workflows": priority_workflows,
        "publication_boundary": "operating_system_publication_only",
        "ready_for_publication": True,
        "workflow_name": "workflow_portfolio_to_operating_system",
    }
    if summary_override:
        summary.update(summary_override)
    (workflow_folder / "portfolio_operating_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    (workflow_folder / "portfolio_next_actions.md").write_text(
        next_actions_text
        or (
            "# Portfolio Next Actions\n\n"
            "Boundary: operating_system_publication_only.\n"
            "1. Hand this package to workflow_and_eval_to_refined_workflow_package for task_to_workflow_strategy.\n"
            "2. Hand the create-next recommendation to workflow_idea_to_workflow_package.\n"
        ),
        encoding="utf-8",
    )

    state = workflow_pkg.WorkflowPortfolioToOperatingSystem.State(
        task_title="Workflow portfolio operating-system review",
        sponsor_role="workflow platform",
        desired_outcome="Publish a governance package with explicit lifecycle recommendations and next actions.",
        focus_workflows=focus_workflows,
        analyzed_workflows=analyzed_workflows,
        lifecycle_postures=lifecycle_postures,
        change_candidate_ids=change_candidate_ids,
        priority_workflows=priority_workflows,
        max_runs_per_workflow=2,
    )
    ctx = Context(
        task_id="portfolio-governance-task",
        run_id="run-1",
        workflow_name="workflow_portfolio_to_operating_system",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "workflow_portfolio_to_operating_system",
        state=state,
        session_store=InMemorySessionStore(),
    )
    return workflow_pkg, state, ctx


def _install_repo_workflow_portfolio_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
        "workflow_portfolio_to_operating_system",
        "workflow_idea_to_workflow_package",
        "task_to_candidate_workflow_set",
        "task_to_workflow_strategy",
        "workflow_run_history_to_failure_modes",
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


def _seed_portfolio_run_health(root: Path) -> dict[str, Path]:
    return {
        "strategy_failed": _write_run_summary_record(
            root,
            task_id="portfolio-beta",
            workflow_name="task_to_workflow_strategy",
            run_id="run-strategy-failed",
            status="failed",
            created_at="2026-04-23T08:00:00+00:00",
            updated_at="2026-04-23T08:05:00+00:00",
            request_text="Re-evaluate the routing package after a failed governance review.\n",
            terminal="FAIL",
            error="candidate package drift",
        ),
        "strategy_paused": _write_run_summary_record(
            root,
            task_id="portfolio-alpha",
            workflow_name="task_to_workflow_strategy",
            run_id="run-strategy-paused",
            status="paused",
            created_at="2026-04-24T08:00:00+00:00",
            updated_at="2026-04-24T08:10:00+00:00",
            request_text="Decide whether this initiative should reuse or create workflows.\n",
            terminal="PAUSE",
            pending_question="Should strategy adapt or compose next?",
        ),
        "diagnostics_success": _write_run_summary_record(
            root,
            task_id="portfolio-gamma",
            workflow_name="workflow_run_history_to_failure_modes",
            run_id="run-diagnostics-success",
            status="success",
            created_at="2026-04-24T07:30:00+00:00",
            updated_at="2026-04-24T07:40:00+00:00",
            request_text="Publish workflow failure pressure for the release governance loop.\n",
            terminal="SUCCESS",
        ),
        "candidate_set_success": _write_run_summary_record(
            root,
            task_id="portfolio-delta",
            workflow_name="task_to_candidate_workflow_set",
            run_id="run-candidate-set-success",
            status="success",
            created_at="2026-04-22T07:00:00+00:00",
            updated_at="2026-04-22T07:05:00+00:00",
            request_text="Publish a ranked candidate set for the delivery planning initiative.\n",
            terminal="SUCCESS",
        ),
    }


def _write_run_summary_record(
    root: Path,
    *,
    task_id: str,
    workflow_name: str,
    run_id: str,
    status: str,
    created_at: str,
    updated_at: str,
    request_text: str,
    terminal: str | None = None,
    error: str | None = None,
    pending_question: str | None = None,
) -> Path:
    run_dir = root / ".autoloop" / "tasks" / task_id / f"wf_{workflow_name}" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "request.md").write_text(request_text, encoding="utf-8")
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "created_at": created_at,
                "error": error,
                "pending_question": pending_question,
                "run_id": run_id,
                "status": status,
                "task_id": task_id,
                "terminal": terminal,
                "updated_at": updated_at,
                "workflow_name": workflow_name,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir
