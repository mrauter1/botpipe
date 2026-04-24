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
_SCOPED_TASK_IDS = ["recursive-beta", "recursive-alpha"]
_FOCUS_WORKFLOWS = [
    "company_operation_to_recursive_improvement_cycle",
    "workflow_and_eval_to_refined_workflow_package",
    "workflow_package_to_composable_building_blocks",
    "workflow_portfolio_to_operating_system",
]
_CANDIDATE_IDS = [
    "stabilize_portfolio_governance_handoff",
    "refine_company_cycle_package_contract",
    "author_eval_suite_for_company_cycle",
    "decompose_recursive_handoff_evidence",
    "tighten_recursive_escalation_policy",
    "institutionalize_recursive_operating_review",
]
_PRIORITY_CATEGORIES = [
    "workflow_portfolio",
    "workflow_package",
    "evaluation_follow_through",
    "decomposition_follow_through",
    "composition_or_escalation_policy",
    "operating_pattern",
]


def _clear_workflow_modules() -> None:
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def test_repo_workflows_namespace_discovers_company_operation_to_recursive_improvement_cycle_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "company_operation_to_recursive_improvement_cycle" in discovered
    package = discovered["company_operation_to_recursive_improvement_cycle"]
    assert package.package_name == "company_operation_to_recursive_improvement_cycle"
    assert "company-recursive-improvement" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT
        / "workflows"
        / "company_operation_to_recursive_improvement_cycle"
        / "workflow.toml"
    )


def test_company_operation_to_recursive_improvement_cycle_compiles_with_explicit_control_contracts(
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.company_operation_to_recursive_improvement_cycle")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.CompanyOperationToRecursiveImprovementCycle)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "capture_company_operation_context",
        "frame_company_operation",
        "analyze_recursive_improvement_pressures",
        "package_recursive_improvement_cycle",
        "publish_recursive_improvement_cycle",
    )

    frame_step = compiled.steps["frame_company_operation"]
    assert frame_step.available_routes == (
        "company_operation_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert frame_step.route_contracts["company_operation_framed"]["required_artifacts"] == [
        "company_operation_brief",
        "recursive_improvement_criteria",
    ]
    assert frame_step.expected_output_schema is not None

    analysis_step = compiled.steps["analyze_recursive_improvement_pressures"]
    assert analysis_step.route_contracts["recursive_improvement_pressures_analyzed"]["required_artifacts"] == [
        "company_pressure_map",
        "recursive_improvement_priority_matrix",
        "recursive_improvement_candidates",
    ]
    assert analysis_step.expected_output_schema is not None
    assert set(analysis_step.expected_output_schema["required"]) >= {
        "summary",
        "focus_task_ids",
        "focus_workflows",
        "candidate_ids",
        "priority_recommendations",
    }

    package_step = compiled.steps["package_recursive_improvement_cycle"]
    assert package_step.route_contracts["recursive_improvement_cycle_ready"]["required_artifacts"] == [
        "recursive_improvement_cycle",
        "recursive_improvement_summary",
        "recursive_improvement_next_actions",
    ]
    assert package_step.expected_output_schema is not None
    assert set(package_step.expected_output_schema["required"]) >= {
        "summary",
        "focus_task_ids",
        "focus_workflows",
        "candidate_ids",
        "priority_item_ids",
        "priority_categories",
        "authoritative_artifacts",
        "next_action",
        "publication_boundary",
        "ready_for_publication",
    }

    publish_step = compiled.steps["publish_recursive_improvement_cycle"]
    assert publish_step.requires == (
        "workflow_capability_snapshot",
        "workflow_portfolio_health_snapshot",
        "company_operation_snapshot",
        "company_pressure_map",
        "recursive_improvement_priority_matrix",
        "recursive_improvement_candidates",
        "recursive_improvement_cycle",
        "recursive_improvement_summary",
        "recursive_improvement_next_actions",
    )


def test_company_operation_to_recursive_improvement_cycle_docs_capture_decision_records() -> None:
    text = (
        REPO_ROOT / "docs" / "workflows" / "company_operation_to_recursive_improvement_cycle.md"
    ).read_text(encoding="utf-8")

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_company_operation_to_recursive_improvement_cycle.py",
    ):
        assert required in text


def test_company_operation_to_recursive_improvement_cycle_prompt_readme_lists_route_grammar_and_runtime_boundary() -> None:
    text = (
        REPO_ROOT
        / "workflows"
        / "company_operation_to_recursive_improvement_cycle"
        / "prompts"
        / "README.md"
    ).read_text(encoding="utf-8")

    for required in (
        "Reserved routes:",
        "- `question`",
        "- `blocked`",
        "- `failed`",
        "Application routes:",
        "- `company_operation_framed`",
        "- `recursive_improvement_pressures_analyzed`",
        "- `recursive_improvement_cycle_ready`",
        "The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.",
    ):
        assert required in text


@pytest.mark.parametrize(
    ("prompt_name", "required_markers"),
    (
        (
            "frame_producer.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Evidence requirements",
                "Route guidance for the verifier",
                "Forbidden",
                "`company_operation_snapshot`",
                "`company_operation_brief`",
                "`recursive_improvement_criteria`",
                "`company_operation_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "Reserved routes are only",
            ),
        ),
        (
            "frame_verifier.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Artifact checks",
                "Evidence requirements",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "Do not overwrite `company_operation_brief` or `recursive_improvement_criteria` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`company_operation_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
        (
            "analyze_producer.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Evidence requirements",
                "Route guidance for the verifier",
                "Forbidden",
                "`company_pressure_map`",
                "`recursive_improvement_priority_matrix`",
                "`recursive_improvement_candidates`",
                "`recursive_improvement_pressures_analyzed`",
                "`needs_rework`",
                "`needs_replan`",
                "Reserved routes are only",
            ),
        ),
        (
            "analyze_verifier.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Artifact checks",
                "Evidence requirements",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "Do not overwrite `company_pressure_map`, `recursive_improvement_priority_matrix`, or `recursive_improvement_candidates` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`recursive_improvement_pressures_analyzed`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
        (
            "package_producer.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Evidence requirements",
                "Route guidance for the verifier",
                "Forbidden",
                "`recursive_improvement_cycle`",
                "`recursive_improvement_summary`",
                "`recursive_improvement_next_actions`",
                "`recursive_improvement_cycle_receipt.json`",
                "`recursive_improvement_cycle_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`recursive_improvement_publication_only`",
                "Reserved routes are only",
            ),
        ),
        (
            "package_verifier.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Artifact checks",
                "Evidence requirements",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "Do not overwrite `recursive_improvement_cycle`, `recursive_improvement_summary`, or `recursive_improvement_next_actions` during verification.",
                "Do not create `recursive_improvement_cycle_receipt.json` in this step.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`recursive_improvement_cycle_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`recursive_improvement_publication_only`",
                "Use reserved routes only",
            ),
        ),
    ),
)
def test_company_operation_to_recursive_improvement_cycle_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (
        REPO_ROOT
        / "workflows"
        / "company_operation_to_recursive_improvement_cycle"
        / "prompts"
        / prompt_name
    ).read_text(encoding="utf-8")

    for marker in required_markers:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"


def test_company_operation_to_recursive_improvement_cycle_rejects_blank_task_title(tmp_path: Path) -> None:
    _install_repo_company_operation_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "company_operation_to_recursive_improvement_cycle").parameters_cls

    with pytest.raises(WorkflowParameterError, match="task_title"):
        coerce_workflow_parameter_mapping(parameters_cls, {"task_title": "   "})


def test_company_operation_to_recursive_improvement_cycle_normalizes_repeatable_inputs(tmp_path: Path) -> None:
    _install_repo_company_operation_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "company_operation_to_recursive_improvement_cycle").parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "task_title": " Company recursive-improvement review ",
            "sponsor_role": " Workflow Platform ",
            "desired_outcome": " ",
            "decision_drivers": [
                " prioritize reusable leverage ",
                "",
                "prioritize reusable leverage",
                "Keep runtime control narrow and stop at publication.",
            ],
            "constraints": [
                " do not auto-run downstream workflows ",
                "",
                "do not auto-run downstream workflows",
                "Keep next actions explicit.",
            ],
            "focus_tasks": [
                " recursive-alpha ",
                "",
                "recursive-beta",
                "recursive-alpha",
            ],
            "focus_workflows": [
                " workflow_portfolio_to_operating_system ",
                "",
                "workflow_package_to_composable_building_blocks",
                "workflow_portfolio_to_operating_system",
            ],
            "statuses": [
                " success ",
                "",
                "paused",
                "success",
            ],
            "max_tasks": 12,
            "max_runs_per_workflow": 4,
            "max_messages_per_task": 3,
        },
    )

    assert normalized == {
        "constraints": [
            "do not auto-run downstream workflows",
            "Keep next actions explicit.",
        ],
        "decision_drivers": [
            "prioritize reusable leverage",
            "Keep runtime control narrow and stop at publication.",
        ],
        "desired_outcome": None,
        "focus_tasks": ["recursive-alpha", "recursive-beta"],
        "focus_workflows": [
            "workflow_portfolio_to_operating_system",
            "workflow_package_to_composable_building_blocks",
        ],
        "max_messages_per_task": 3,
        "max_runs_per_workflow": 4,
        "max_tasks": 12,
        "sponsor_role": "Workflow Platform",
        "statuses": ["success", "paused"],
        "task_title": "Company recursive-improvement review",
    }


def test_company_operation_to_recursive_improvement_cycle_runs_and_publishes_terminal_cycle_artifacts(
    tmp_path: Path,
) -> None:
    _install_repo_company_operation_package(tmp_path)
    seeded_paths = _seed_company_operation_history(tmp_path)

    provider = ScriptedLLMProvider(
        producer_turns=[
            _produce_company_frame,
            _produce_recursive_pressure_analysis,
            _produce_recursive_cycle_package,
        ],
        verifier_turns=[
            Outcome(
                raw_output="company operation framed\n",
                tag="company_operation_framed",
                payload={
                    "summary": "The scoped company context, sponsor pressure, and recursive-improvement criteria are explicit enough for analysis.",
                    "focus_task_ids": _SCOPED_TASK_IDS,
                    "focus_workflows": _FOCUS_WORKFLOWS,
                    "authoritative_artifacts": [
                        "company_operation_brief",
                        "recursive_improvement_criteria",
                    ],
                    "decision_axes": [
                        "recursive leverage",
                        "workflow health pressure",
                        "follow-through discipline",
                        "operating-pattern durability",
                    ],
                },
            ),
            Outcome(
                raw_output="recursive improvement pressures analyzed\n",
                tag="recursive_improvement_pressures_analyzed",
                payload={
                    "summary": "The company pressure map now has an explicit ranked recursive-improvement candidate set.",
                    "focus_task_ids": _SCOPED_TASK_IDS,
                    "focus_workflows": _FOCUS_WORKFLOWS,
                    "candidate_ids": _CANDIDATE_IDS,
                    "priority_recommendations": [
                        {
                            "candidate_id": "stabilize_portfolio_governance_handoff",
                            "category": "workflow_portfolio",
                            "priority": "P1",
                        },
                        {
                            "candidate_id": "refine_company_cycle_package_contract",
                            "category": "workflow_package",
                            "priority": "P1",
                        },
                        {
                            "candidate_id": "author_eval_suite_for_company_cycle",
                            "category": "evaluation_follow_through",
                            "priority": "P1",
                        },
                        {
                            "candidate_id": "decompose_recursive_handoff_evidence",
                            "category": "decomposition_follow_through",
                            "priority": "P2",
                        },
                        {
                            "candidate_id": "tighten_recursive_escalation_policy",
                            "category": "composition_or_escalation_policy",
                            "priority": "P2",
                        },
                        {
                            "candidate_id": "institutionalize_recursive_operating_review",
                            "category": "operating_pattern",
                            "priority": "P3",
                        },
                    ],
                },
            ),
            Outcome(
                raw_output="recursive improvement cycle ready\n",
                tag="recursive_improvement_cycle_ready",
                payload={
                    "summary": "The recursive-improvement cycle package, summary, and next actions are aligned and ready for publication.",
                    "focus_task_ids": _SCOPED_TASK_IDS,
                    "focus_workflows": _FOCUS_WORKFLOWS,
                    "candidate_ids": _CANDIDATE_IDS,
                    "priority_item_ids": _CANDIDATE_IDS,
                    "priority_categories": _PRIORITY_CATEGORIES,
                    "authoritative_artifacts": [
                        "recursive_improvement_cycle",
                        "recursive_improvement_summary",
                        "recursive_improvement_next_actions",
                        "company_pressure_map",
                        "recursive_improvement_priority_matrix",
                        "recursive_improvement_candidates",
                    ],
                    "next_action": "Hand this cycle package to `workflow_to_eval_suite` for `company_operation_to_recursive_improvement_cycle`, then hand the governance follow-through item to `workflow_and_eval_to_refined_workflow_package` as a separate follow-on.",
                    "publication_boundary": "recursive_improvement_publication_only",
                    "ready_for_publication": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "company_operation_to_recursive_improvement_cycle",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="company-recursive-task",
            message="Recommend the next recursive improvement cycle from current company work history and workflow telemetry.",
            workflow_params={
                "task_title": "Company recursive-improvement review",
                "sponsor_role": "workflow platform",
                "desired_outcome": "Publish a prioritized recursive improvement cycle package.",
                "decision_drivers": [
                    "Prioritize reusable leverage across workflows and operating patterns.",
                    "Keep runtime control narrow and stop at publication.",
                ],
                "constraints": [
                    "Do not auto-run downstream workflows.",
                    "Keep next actions explicit.",
                ],
                "focus_tasks": ["recursive-alpha", "recursive-beta"],
                "focus_workflows": [
                    "workflow_portfolio_to_operating_system",
                    "workflow_package_to_composable_building_blocks",
                    "workflow_and_eval_to_refined_workflow_package",
                    "company_operation_to_recursive_improvement_cycle",
                ],
                "statuses": ["success", "paused", "failed"],
                "max_tasks": 2,
                "max_runs_per_workflow": 2,
                "max_messages_per_task": 2,
            },
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "company-recursive-task"
    workflow_dir = task_dir / "wf_company_operation_to_recursive_improvement_cycle"
    run_dir = next((workflow_dir / "runs").iterdir())

    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    capability_snapshot = json.loads((workflow_dir / "workflow_capability_snapshot.json").read_text(encoding="utf-8"))
    health_snapshot = json.loads((workflow_dir / "workflow_portfolio_health_snapshot.json").read_text(encoding="utf-8"))
    company_snapshot = json.loads((workflow_dir / "company_operation_snapshot.json").read_text(encoding="utf-8"))
    cycle_summary = json.loads((workflow_dir / "recursive_improvement_summary.json").read_text(encoding="utf-8"))
    cycle_receipt = json.loads((workflow_dir / "recursive_improvement_cycle_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "SUCCESS"
    assert (workflow_dir / "workflow_capability_snapshot.json").exists()
    assert (workflow_dir / "workflow_portfolio_health_snapshot.json").exists()
    assert (workflow_dir / "company_operation_snapshot.json").exists()
    assert (workflow_dir / "company_operation_brief.md").exists()
    assert (workflow_dir / "recursive_improvement_criteria.md").exists()
    assert (workflow_dir / "company_pressure_map.md").exists()
    assert (workflow_dir / "recursive_improvement_priority_matrix.md").exists()
    assert (workflow_dir / "recursive_improvement_candidates.json").exists()
    assert (workflow_dir / "recursive_improvement_cycle.md").exists()
    assert (workflow_dir / "recursive_improvement_summary.json").exists()
    assert (workflow_dir / "recursive_improvement_next_actions.md").exists()
    assert (workflow_dir / "recursive_improvement_cycle_receipt.json").exists()
    assert sorted(path.name for path in task_dir.glob("wf_*")) == ["wf_company_operation_to_recursive_improvement_cycle"]
    children_file = run_dir / "children.jsonl"
    assert (not children_file.exists()) or children_file.read_text(encoding="utf-8") == ""

    assert invocation_contract == {
        "constraints": [
            "Do not auto-run downstream workflows.",
            "Keep next actions explicit.",
        ],
        "decision_drivers": [
            "Prioritize reusable leverage across workflows and operating patterns.",
            "Keep runtime control narrow and stop at publication.",
        ],
        "desired_outcome": "Publish a prioritized recursive improvement cycle package.",
        "focus_task_references": ["recursive-alpha", "recursive-beta"],
        "focus_workflow_references": [
            "workflow_portfolio_to_operating_system",
            "workflow_package_to_composable_building_blocks",
            "workflow_and_eval_to_refined_workflow_package",
            "company_operation_to_recursive_improvement_cycle",
        ],
        "max_messages_per_task": 2,
        "max_runs_per_workflow": 2,
        "max_tasks": 2,
        "message": "Recommend the next recursive improvement cycle from current company work history and workflow telemetry.\n",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "sponsor_role": "workflow platform",
        "statuses": ["success", "paused", "failed"],
        "task_id": "company-recursive-task",
        "task_title": "Company recursive-improvement review",
        "workflow_name": "company_operation_to_recursive_improvement_cycle",
    }
    assert capability_snapshot["workflow_count"] == 6
    assert {entry["workflow_name"] for entry in capability_snapshot["workflows"]} == {
        "company_operation_to_recursive_improvement_cycle",
        "workflow_and_eval_to_refined_workflow_package",
        "workflow_idea_to_workflow_package",
        "workflow_package_to_composable_building_blocks",
        "workflow_portfolio_to_operating_system",
        "workflow_to_eval_suite",
    }
    assert health_snapshot["repo_root"] == str(tmp_path.resolve())
    assert health_snapshot["run_id"] == run_dir.name
    assert health_snapshot["task_id"] == "company-recursive-task"
    assert health_snapshot["workflow_name"] == "company_operation_to_recursive_improvement_cycle"
    assert health_snapshot["workflow_portfolio_health"]["max_runs_per_workflow"] == 2
    assert health_snapshot["workflow_portfolio_health"]["selected_workflow_names"] == _FOCUS_WORKFLOWS
    assert health_snapshot["workflow_portfolio_health"]["statuses"] == ["failed", "paused", "success"]
    assert health_snapshot["workflow_portfolio_health"]["workflow_count"] == 4

    health_by_workflow = {
        entry["workflow_name"]: entry for entry in health_snapshot["workflow_portfolio_health"]["workflows"]
    }
    assert health_by_workflow["company_operation_to_recursive_improvement_cycle"]["run_count"] == 0
    assert health_by_workflow["company_operation_to_recursive_improvement_cycle"]["recent_runs"] == []
    assert health_by_workflow["workflow_and_eval_to_refined_workflow_package"]["run_count"] == 1
    assert health_by_workflow["workflow_and_eval_to_refined_workflow_package"]["status_counts"] == {"success": 1}
    assert health_by_workflow["workflow_package_to_composable_building_blocks"]["run_count"] == 1
    assert health_by_workflow["workflow_package_to_composable_building_blocks"]["status_counts"] == {"failed": 1}
    assert health_by_workflow["workflow_portfolio_to_operating_system"]["run_count"] == 2
    assert health_by_workflow["workflow_portfolio_to_operating_system"]["status_counts"] == {"paused": 1, "success": 1}

    assert company_snapshot["repo_root"] == str(tmp_path.resolve())
    assert company_snapshot["run_id"] == run_dir.name
    assert company_snapshot["task_id"] == "company-recursive-task"
    assert company_snapshot["workflow_name"] == "company_operation_to_recursive_improvement_cycle"
    assert company_snapshot["company_operation"]["max_tasks"] == 2
    assert company_snapshot["company_operation"]["max_runs_per_workflow"] == 2
    assert company_snapshot["company_operation"]["max_messages_per_task"] == 2
    assert company_snapshot["company_operation"]["selected_task_ids"] == ["recursive-alpha", "recursive-beta"]
    assert company_snapshot["company_operation"]["selected_workflow_names"] == _FOCUS_WORKFLOWS
    assert company_snapshot["company_operation"]["statuses"] == ["failed", "paused", "success"]
    assert company_snapshot["company_operation"]["task_count"] == 2
    assert [entry["task_id"] for entry in company_snapshot["company_operation"]["tasks"]] == _SCOPED_TASK_IDS
    assert company_snapshot["company_operation"]["tasks"][0]["recent_messages"][0] == {
        "message_excerpt": "Need an explicit operating-review cadence before the next recursive package is approved.",
        "ts": "2026-04-24T09:04:00+00:00",
    }
    assert company_snapshot["company_operation"]["tasks"][0]["workflow_run_summaries"][0]["workflow_name"] == "company_operation_to_recursive_improvement_cycle"
    assert company_snapshot["company_operation"]["tasks"][0]["workflow_run_summaries"][0]["run_count"] == 0
    assert company_snapshot["company_operation"]["tasks"][1]["workflow_run_summaries"][3]["workflow_name"] == "workflow_portfolio_to_operating_system"
    assert company_snapshot["company_operation"]["tasks"][1]["workflow_run_summaries"][3]["run_count"] == 2
    assert company_snapshot["company_operation"]["tasks"][1]["workflow_run_summaries"][3]["recent_runs"][0]["run_id"] == "run-portfolio-paused"
    assert company_snapshot["company_operation"]["tasks"][1]["workflow_run_summaries"][3]["recent_runs"][1]["run_id"] == "run-portfolio-success"
    assert company_snapshot["company_operation"]["tasks"][1]["recent_messages"][0]["ts"] == "2026-04-24T09:03:00+00:00"
    assert company_snapshot["company_operation"]["tasks"][1]["recent_messages"][1]["message_excerpt"].startswith(
        "Leadership wants the recursive governance package to explain why decomposition"
    )

    assert cycle_summary == {
        "authoritative_artifacts": [
            "recursive_improvement_cycle",
            "recursive_improvement_summary",
            "recursive_improvement_next_actions",
            "company_pressure_map",
            "recursive_improvement_priority_matrix",
            "recursive_improvement_candidates",
        ],
        "candidate_ids": _CANDIDATE_IDS,
        "focus_task_ids": _SCOPED_TASK_IDS,
        "focus_workflows": _FOCUS_WORKFLOWS,
        "next_action": "Hand this cycle package to `workflow_to_eval_suite` for `company_operation_to_recursive_improvement_cycle`, then hand the governance follow-through item to `workflow_and_eval_to_refined_workflow_package` as a separate follow-on.",
        "priority_categories": _PRIORITY_CATEGORIES,
        "priority_category_counts": {
            "composition_or_escalation_policy": 1,
            "decomposition_follow_through": 1,
            "evaluation_follow_through": 1,
            "operating_pattern": 1,
            "workflow_package": 1,
            "workflow_portfolio": 1,
        },
        "priority_item_ids": _CANDIDATE_IDS,
        "publication_boundary": "recursive_improvement_publication_only",
        "ready_for_publication": True,
        "workflow_name": "company_operation_to_recursive_improvement_cycle",
    }
    assert cycle_receipt == {
        "authoritative_artifacts": [
            "recursive_improvement_cycle",
            "recursive_improvement_summary",
            "recursive_improvement_next_actions",
            "company_pressure_map",
            "recursive_improvement_priority_matrix",
            "recursive_improvement_candidates",
        ],
        "candidate_ids": _CANDIDATE_IDS,
        "company_operation_snapshot": str(workflow_dir / "company_operation_snapshot.json"),
        "company_pressure_map": str(workflow_dir / "company_pressure_map.md"),
        "desired_outcome": "Publish a prioritized recursive improvement cycle package.",
        "focus_task_ids": _SCOPED_TASK_IDS,
        "focus_workflows": _FOCUS_WORKFLOWS,
        "next_action": "Hand this cycle package to `workflow_to_eval_suite` for `company_operation_to_recursive_improvement_cycle`, then hand the governance follow-through item to `workflow_and_eval_to_refined_workflow_package` as a separate follow-on.",
        "priority_categories": _PRIORITY_CATEGORIES,
        "priority_item_ids": _CANDIDATE_IDS,
        "publication_boundary": "recursive_improvement_publication_only",
        "published": True,
        "recursive_improvement_candidates": str(workflow_dir / "recursive_improvement_candidates.json"),
        "recursive_improvement_cycle": str(workflow_dir / "recursive_improvement_cycle.md"),
        "recursive_improvement_next_actions": str(workflow_dir / "recursive_improvement_next_actions.md"),
        "recursive_improvement_priority_matrix": str(workflow_dir / "recursive_improvement_priority_matrix.md"),
        "recursive_improvement_summary": str(workflow_dir / "recursive_improvement_summary.json"),
        "sponsor_role": "workflow platform",
        "task_title": "Company recursive-improvement review",
        "workflow_capability_snapshot": str(workflow_dir / "workflow_capability_snapshot.json"),
        "workflow_name": "company_operation_to_recursive_improvement_cycle",
        "workflow_portfolio_health_snapshot": str(workflow_dir / "workflow_portfolio_health_snapshot.json"),
    }
    assert [call.step_name for call in provider.calls] == [
        "frame_company_operation",
        "frame_company_operation",
        "analyze_recursive_improvement_pressures",
        "analyze_recursive_improvement_pressures",
        "package_recursive_improvement_cycle",
        "package_recursive_improvement_cycle",
    ]
    assert provider.calls[3].available_routes == (
        "recursive_improvement_pressures_analyzed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert provider.calls[5].route_contracts["recursive_improvement_cycle_ready"]["required_artifacts"] == [
        "recursive_improvement_cycle",
        "recursive_improvement_summary",
        "recursive_improvement_next_actions",
    ]
    assert health_by_workflow["workflow_portfolio_to_operating_system"]["recent_runs"][0]["request_file"] == str(
        seeded_paths["portfolio_paused"] / "request.md"
    )
    assert (run_dir / "run.json").exists()


@pytest.mark.parametrize(
    "missing_filename",
    [
        "workflow_capability_snapshot.json",
        "workflow_portfolio_health_snapshot.json",
        "company_operation_snapshot.json",
    ],
)
def test_company_operation_to_recursive_improvement_cycle_publish_rejects_missing_snapshot_artifact(
    tmp_path: Path,
    monkeypatch,
    missing_filename: str,
) -> None:
    workflow_pkg, state, ctx = _make_publish_company_operation_cycle_test_context(tmp_path, monkeypatch)
    (ctx.workflow_folder / missing_filename).unlink()

    with pytest.raises(FileNotFoundError, match="missing required publication artifact"):
        workflow_pkg.CompanyOperationToRecursiveImprovementCycle.on_publish_recursive_improvement_cycle(state, ctx)


def test_company_operation_to_recursive_improvement_cycle_publish_rejects_unknown_focus_task_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_company_operation_cycle_test_context(
        tmp_path,
        monkeypatch,
        summary_override={"focus_task_ids": ["recursive-beta", "ghost-task"]},
    )

    with pytest.raises(ValueError, match="unknown focus-task references"):
        workflow_pkg.CompanyOperationToRecursiveImprovementCycle.on_publish_recursive_improvement_cycle(state, ctx)


def test_company_operation_to_recursive_improvement_cycle_publish_rejects_unknown_focus_workflow_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_company_operation_cycle_test_context(
        tmp_path,
        monkeypatch,
        focus_workflows=[
            "company_operation_to_recursive_improvement_cycle",
            "workflow_package_to_composable_building_blocks",
            "workflow_portfolio_to_operating_system",
            "unknown_workflow",
        ],
    )

    with pytest.raises(ValueError, match="unknown focus-workflow references"):
        workflow_pkg.CompanyOperationToRecursiveImprovementCycle.on_publish_recursive_improvement_cycle(state, ctx)


def test_company_operation_to_recursive_improvement_cycle_publish_rejects_summary_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_company_operation_cycle_test_context(
        tmp_path,
        monkeypatch,
        summary_override={
            "priority_category_counts": {
                "composition_or_escalation_policy": 2,
                "decomposition_follow_through": 1,
                "evaluation_follow_through": 1,
                "operating_pattern": 1,
                "workflow_package": 1,
                "workflow_portfolio": 1,
            }
        },
    )

    with pytest.raises(ValueError, match="must not drift from recursive_improvement_candidates.json"):
        workflow_pkg.CompanyOperationToRecursiveImprovementCycle.on_publish_recursive_improvement_cycle(state, ctx)


def test_company_operation_to_recursive_improvement_cycle_publish_rejects_invalid_priority_category(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_company_operation_cycle_test_context(
        tmp_path,
        monkeypatch,
        summary_override={
            "priority_categories": [
                "workflow_portfolio",
                "workflow_package",
                "monitoring",
            ]
        },
    )

    with pytest.raises(ValueError, match="legal priority categories"):
        workflow_pkg.CompanyOperationToRecursiveImprovementCycle.on_publish_recursive_improvement_cycle(state, ctx)


@pytest.mark.parametrize(
    "next_actions_text",
    (
        (
            "# Recursive Improvement Next Actions\n\n"
            "Boundary: recursive_improvement_publication_only.\n"
            "Automatically run workflow_to_eval_suite for company_operation_to_recursive_improvement_cycle next.\n"
        ),
        (
            "# Recursive Improvement Next Actions\n\n"
            "Boundary: recursive_improvement_publication_only.\n"
            "The runtime queues workflow_and_eval_to_refined_workflow_package after publication.\n"
        ),
        (
            "# Recursive Improvement Next Actions\n\n"
            "Boundary: recursive_improvement_publication_only.\n"
            "This workflow will launch workflow_package_to_composable_building_blocks after publication.\n"
        ),
    ),
)
def test_company_operation_to_recursive_improvement_cycle_publish_rejects_hidden_downstream_execution_in_next_actions(
    tmp_path: Path,
    monkeypatch,
    next_actions_text: str,
) -> None:
    workflow_pkg, state, ctx = _make_publish_company_operation_cycle_test_context(
        tmp_path,
        monkeypatch,
        next_actions_text=next_actions_text,
    )

    with pytest.raises(ValueError, match="recursive_improvement_next_actions.md must not imply hidden downstream execution"):
        workflow_pkg.CompanyOperationToRecursiveImprovementCycle.on_publish_recursive_improvement_cycle(state, ctx)


def test_company_operation_to_recursive_improvement_cycle_publish_rejects_hidden_downstream_execution_in_summary_next_action(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_company_operation_cycle_test_context(
        tmp_path,
        monkeypatch,
        summary_override={
            "next_action": "The runtime queues workflow_to_eval_suite for company_operation_to_recursive_improvement_cycle next.",
        },
    )

    with pytest.raises(
        ValueError,
        match="recursive_improvement_summary.json next_action must not imply hidden downstream execution",
    ):
        workflow_pkg.CompanyOperationToRecursiveImprovementCycle.on_publish_recursive_improvement_cycle(state, ctx)


def _produce_company_frame(request) -> str:
    request.artifacts.company_operation_brief.write_text(
        "\n".join(
            (
                "# Company Operation Brief",
                "",
                "Scoped tasks:",
                "- `recursive-beta`",
                "- `recursive-alpha`",
                "",
                "Scoped workflows:",
                "- `company_operation_to_recursive_improvement_cycle`",
                "- `workflow_and_eval_to_refined_workflow_package`",
                "- `workflow_package_to_composable_building_blocks`",
                "- `workflow_portfolio_to_operating_system`",
                "",
                "Sponsor: workflow platform.",
                "Why now: portfolio governance and decomposition pressure are visible in the current company task slice, but there is no durable cycle package that turns that pressure into the next recursive improvement agenda.",
                "Terminal package: explicit recursive-improvement priorities, next actions, and a deterministic receipt.",
                "Boundary: recursive_improvement_publication_only.",
                "",
            )
        )
        + "\n",
    )
    request.artifacts.recursive_improvement_criteria.write_text(
        "\n".join(
            (
                "# Recursive Improvement Criteria",
                "",
                "- Prefer workflow-portfolio priorities when scoped telemetry shows repeated governance stalls or missing coordination across shipped layers.",
                "- Prefer workflow-package priorities when the current package contract itself needs tighter scope, validation, or publication discipline.",
                "- Prefer evaluation, refinement, or decomposition follow-through when the next credible move is to harden a shipped workflow rather than invent a runtime-owned shortcut.",
                "- Prefer composition or escalation policy priorities when the current workflow set still hands off work ambiguously.",
                "- Prefer operating-pattern priorities when the company needs a repeatable review cadence or explicit ownership convention beyond one workflow package.",
                "",
            )
        )
        + "\n",
    )
    return "framed company operation\n"


def _produce_recursive_pressure_analysis(request) -> str:
    request.artifacts.company_pressure_map.write_text(
        "\n".join(
            (
                "# Company Pressure Map",
                "",
                "- `recursive-alpha` shows paused portfolio-governance work and a still-successful refinement path, which suggests the portfolio layer is valuable but the handoff remains fragile.",
                "- `recursive-beta` shows a failed decomposition package plus messages asking for an explicit operating-review cadence, which adds both decomposition follow-through pressure and operating-pattern pressure.",
                "- The current company workflow itself has no prior runs in the scoped slice, so it needs an explicit package contract and evaluation handoff before future cycles can rely on it confidently.",
                "",
            )
        )
        + "\n",
    )
    request.artifacts.recursive_improvement_priority_matrix.write_text(
        "\n".join(
            (
                "# Recursive Improvement Priority Matrix",
                "",
                "| candidate_id | category | priority | evidence |",
                "| --- | --- | --- | --- |",
                "| `stabilize_portfolio_governance_handoff` | `workflow_portfolio` | `P1` | paused governance telemetry shows the portfolio layer still needs a tighter recursive handoff |",
                "| `refine_company_cycle_package_contract` | `workflow_package` | `P1` | the new company workflow needs a stronger package contract before later cycles trust it |",
                "| `author_eval_suite_for_company_cycle` | `evaluation_follow_through` | `P1` | the company workflow should publish an eval suite before later refinement work depends on it |",
                "| `decompose_recursive_handoff_evidence` | `decomposition_follow_through` | `P2` | the failed decomposition run shows the decomposition follow-through still needs a cleaner evidence surface |",
                "| `tighten_recursive_escalation_policy` | `composition_or_escalation_policy` | `P2` | task messages show uncertainty about who should take the next recursive handoff |",
                "| `institutionalize_recursive_operating_review` | `operating_pattern` | `P3` | the company task slice keeps asking for an explicit operating-review cadence |",
                "",
            )
        )
        + "\n",
    )
    request.artifacts.recursive_improvement_candidates.write_text(
        json.dumps(
            {
                "improvement_candidates": [
                    {
                        "candidate_id": "stabilize_portfolio_governance_handoff",
                        "category": "workflow_portfolio",
                        "priority": "P1",
                        "task_ids": ["recursive-alpha"],
                        "title": "Stabilize the portfolio-governance handoff boundary.",
                        "why_now": "Paused governance telemetry shows the portfolio layer is valuable but still hands off recursive work too loosely.",
                        "evidence_sources": [
                            "workflow_portfolio_health_snapshot",
                            "company_operation_snapshot",
                        ],
                        "next_step_hint": "workflow_and_eval_to_refined_workflow_package",
                        "workflow_names": ["workflow_portfolio_to_operating_system"],
                    },
                    {
                        "candidate_id": "refine_company_cycle_package_contract",
                        "category": "workflow_package",
                        "priority": "P1",
                        "title": "Refine the company cycle package contract before later cycles depend on it.",
                        "why_now": "The new company workflow needs a stronger publication contract and clearer package surface immediately.",
                        "evidence_sources": [
                            "workflow_capability_snapshot",
                            "company_pressure_map",
                        ],
                        "next_step_hint": "workflow_and_eval_to_refined_workflow_package",
                        "workflow_names": ["company_operation_to_recursive_improvement_cycle"],
                    },
                    {
                        "candidate_id": "author_eval_suite_for_company_cycle",
                        "category": "evaluation_follow_through",
                        "priority": "P1",
                        "title": "Author an eval suite for the company recursive-improvement workflow.",
                        "why_now": "The company workflow should publish benchmark and edge coverage before future refinement or governance work trusts it.",
                        "evidence_sources": [
                            "workflow_capability_snapshot",
                            "company_pressure_map",
                        ],
                        "next_step_hint": "workflow_to_eval_suite",
                        "workflow_names": ["company_operation_to_recursive_improvement_cycle"],
                    },
                    {
                        "candidate_id": "decompose_recursive_handoff_evidence",
                        "category": "decomposition_follow_through",
                        "priority": "P2",
                        "task_ids": ["recursive-beta"],
                        "title": "Tighten decomposition follow-through evidence for recursive handoffs.",
                        "why_now": "The failed decomposition run shows the evidence boundary still needs a cleaner recursive handoff.",
                        "evidence_sources": [
                            "workflow_portfolio_health_snapshot",
                            "company_operation_snapshot",
                        ],
                        "next_step_hint": "workflow_package_to_composable_building_blocks",
                        "workflow_names": ["workflow_package_to_composable_building_blocks"],
                    },
                    {
                        "candidate_id": "tighten_recursive_escalation_policy",
                        "category": "composition_or_escalation_policy",
                        "priority": "P2",
                        "task_ids": ["recursive-alpha", "recursive-beta"],
                        "title": "Make recursive escalation and handoff policy explicit across the current governance and decomposition layers.",
                        "why_now": "Task messages keep asking who should own the next recursive step, which means the composition policy is still implicit.",
                        "evidence_sources": [
                            "company_operation_snapshot",
                            "company_pressure_map",
                        ],
                        "next_step_hint": "company_operation_to_recursive_improvement_cycle",
                        "workflow_names": [
                            "workflow_package_to_composable_building_blocks",
                            "workflow_portfolio_to_operating_system",
                        ],
                    },
                    {
                        "candidate_id": "institutionalize_recursive_operating_review",
                        "category": "operating_pattern",
                        "priority": "P3",
                        "task_ids": ["recursive-alpha", "recursive-beta"],
                        "title": "Institutionalize a lightweight recursive operating review cadence.",
                        "why_now": "The scoped company work repeatedly asks for an explicit review cadence before packages are trusted downstream.",
                        "evidence_sources": [
                            "company_operation_snapshot",
                            "company_pressure_map",
                        ],
                        "next_step_hint": "human_operating_review",
                    },
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return "analyzed recursive improvement pressures\n"


def _produce_recursive_cycle_package(request) -> str:
    request.artifacts.recursive_improvement_cycle.write_text(
        "\n".join(
            (
                "# Recursive Improvement Cycle",
                "",
                "This cycle package turns scoped company work history and workflow telemetry into the next explicit recursive agenda.",
                "",
                "## Workflow Portfolio",
                "- `stabilize_portfolio_governance_handoff`: refine the governance handoff boundary first.",
                "",
                "## Workflow Packages",
                "- `refine_company_cycle_package_contract`: tighten the package contract for `company_operation_to_recursive_improvement_cycle` before later cycles depend on it.",
                "",
                "## Evaluation / Refinement / Decomposition Follow-Through",
                "- `author_eval_suite_for_company_cycle`: publish an eval suite for `company_operation_to_recursive_improvement_cycle`.",
                "- `decompose_recursive_handoff_evidence`: clean up the decomposition evidence handoff before another company-level cycle relies on it.",
                "",
                "## Composition / Escalation Policy",
                "- `tighten_recursive_escalation_policy`: make the recursive escalation owner explicit across governance and decomposition follow-through.",
                "",
                "## Operating Patterns",
                "- `institutionalize_recursive_operating_review`: publish one lightweight operating review cadence for future recursive cycles.",
                "",
                "## Publication Boundary",
                "- recursive_improvement_publication_only",
                "",
            )
        )
        + "\n",
    )
    request.artifacts.recursive_improvement_summary.write_text(
        json.dumps(
            {
                "authoritative_artifacts": [
                    "recursive_improvement_cycle",
                    "recursive_improvement_summary",
                    "recursive_improvement_next_actions",
                    "company_pressure_map",
                    "recursive_improvement_priority_matrix",
                    "recursive_improvement_candidates",
                ],
                "candidate_ids": _CANDIDATE_IDS,
                "focus_task_ids": _SCOPED_TASK_IDS,
                "focus_workflows": _FOCUS_WORKFLOWS,
                "next_action": "Hand this cycle package to `workflow_to_eval_suite` for `company_operation_to_recursive_improvement_cycle`, then hand the governance follow-through item to `workflow_and_eval_to_refined_workflow_package` as a separate follow-on.",
                "priority_categories": _PRIORITY_CATEGORIES,
                "priority_category_counts": {
                    "composition_or_escalation_policy": 1,
                    "decomposition_follow_through": 1,
                    "evaluation_follow_through": 1,
                    "operating_pattern": 1,
                    "workflow_package": 1,
                    "workflow_portfolio": 1,
                },
                "priority_item_ids": _CANDIDATE_IDS,
                "publication_boundary": "recursive_improvement_publication_only",
                "ready_for_publication": True,
                "workflow_name": "company_operation_to_recursive_improvement_cycle",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    request.artifacts.recursive_improvement_next_actions.write_text(
        "\n".join(
            (
                "# Recursive Improvement Next Actions",
                "",
                "Boundary: recursive_improvement_publication_only.",
                "1. Hand this package to `workflow_to_eval_suite` for `company_operation_to_recursive_improvement_cycle`.",
                "2. Hand the portfolio-governance handoff item to `workflow_and_eval_to_refined_workflow_package` for `workflow_portfolio_to_operating_system`.",
                "3. Re-run this workflow after the package refinement and eval-suite follow-through are complete.",
                "",
            )
        )
        + "\n",
    )
    return "packaged recursive improvement cycle\n"


def _make_publish_company_operation_cycle_test_context(
    tmp_path: Path,
    monkeypatch,
    *,
    focus_workflows: list[str] | None = None,
    scoped_task_ids: list[str] | None = None,
    summary_override: dict[str, object] | None = None,
    next_actions_text: str | None = None,
) -> tuple[object, object, Context]:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.company_operation_to_recursive_improvement_cycle")

    focus_workflows = list(focus_workflows or _FOCUS_WORKFLOWS)
    scoped_task_ids = list(scoped_task_ids or _SCOPED_TASK_IDS)

    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_company_operation_to_recursive_improvement_cycle"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)

    (workflow_folder / "workflow_capability_snapshot.json").write_text(
        json.dumps(
            {
                "workflow_count": 5,
                "workflows": [
                    {"workflow_name": "company_operation_to_recursive_improvement_cycle"},
                    {"workflow_name": "workflow_and_eval_to_refined_workflow_package"},
                    {"workflow_name": "workflow_idea_to_workflow_package"},
                    {"workflow_name": "workflow_package_to_composable_building_blocks"},
                    {"workflow_name": "workflow_portfolio_to_operating_system"},
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
                    "statuses": ["failed", "paused", "success"],
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
    (workflow_folder / "company_operation_snapshot.json").write_text(
        json.dumps(
            {
                "company_operation": {
                    "max_messages_per_task": 2,
                    "max_runs_per_workflow": 2,
                    "max_tasks": 2,
                    "selected_task_ids": ["recursive-alpha", "recursive-beta"],
                    "selected_workflow_names": focus_workflows,
                    "statuses": ["failed", "paused", "success"],
                    "task_count": len(scoped_task_ids),
                    "tasks": [
                        {
                            "task_id": task_id,
                            "workflow_run_summaries": [
                                {
                                    "workflow_name": workflow_name,
                                    "run_count": 0,
                                    "status_counts": {},
                                    "recent_runs": [],
                                    "latest_run_id": None,
                                    "latest_updated_at": None,
                                }
                                for workflow_name in focus_workflows
                            ],
                        }
                        for task_id in scoped_task_ids
                    ],
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "company_pressure_map.md").write_text(
        "# Company Pressure Map\n\n- recursive pressure is explicit across the scoped company slice.\n",
        encoding="utf-8",
    )
    (workflow_folder / "recursive_improvement_priority_matrix.md").write_text(
        "\n".join(
            [
                "# Recursive Improvement Priority Matrix",
                "",
                *[
                    f"- `{candidate_id}`"
                    for candidate_id in _CANDIDATE_IDS
                ],
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "recursive_improvement_candidates.json").write_text(
        json.dumps(
            {
                "improvement_candidates": [
                    {
                        "candidate_id": "stabilize_portfolio_governance_handoff",
                        "category": "workflow_portfolio",
                        "priority": "P1",
                        "task_ids": ["recursive-alpha"],
                        "title": "Stabilize the portfolio-governance handoff boundary.",
                        "why_now": "The governance layer keeps stalling.",
                        "evidence_sources": [
                            "workflow_portfolio_health_snapshot",
                            "company_operation_snapshot",
                        ],
                        "next_step_hint": "workflow_and_eval_to_refined_workflow_package",
                        "workflow_names": ["workflow_portfolio_to_operating_system"],
                    },
                    {
                        "candidate_id": "refine_company_cycle_package_contract",
                        "category": "workflow_package",
                        "priority": "P1",
                        "title": "Refine the company cycle package contract.",
                        "why_now": "The company learner needs a stronger package boundary.",
                        "evidence_sources": [
                            "workflow_capability_snapshot",
                            "company_pressure_map",
                        ],
                        "next_step_hint": "workflow_and_eval_to_refined_workflow_package",
                        "workflow_names": ["company_operation_to_recursive_improvement_cycle"],
                    },
                    {
                        "candidate_id": "author_eval_suite_for_company_cycle",
                        "category": "evaluation_follow_through",
                        "priority": "P1",
                        "title": "Author an eval suite for the company workflow.",
                        "why_now": "Later cycles need explicit evaluation coverage.",
                        "evidence_sources": [
                            "workflow_capability_snapshot",
                            "company_pressure_map",
                        ],
                        "next_step_hint": "workflow_to_eval_suite",
                        "workflow_names": ["company_operation_to_recursive_improvement_cycle"],
                    },
                    {
                        "candidate_id": "decompose_recursive_handoff_evidence",
                        "category": "decomposition_follow_through",
                        "priority": "P2",
                        "task_ids": ["recursive-beta"],
                        "title": "Tighten decomposition follow-through evidence.",
                        "why_now": "The decomposition layer still has a weak handoff surface.",
                        "evidence_sources": [
                            "workflow_portfolio_health_snapshot",
                            "company_operation_snapshot",
                        ],
                        "next_step_hint": "workflow_package_to_composable_building_blocks",
                        "workflow_names": ["workflow_package_to_composable_building_blocks"],
                    },
                    {
                        "candidate_id": "tighten_recursive_escalation_policy",
                        "category": "composition_or_escalation_policy",
                        "priority": "P2",
                        "task_ids": ["recursive-alpha", "recursive-beta"],
                        "title": "Make recursive escalation policy explicit.",
                        "why_now": "The current task slice still asks who owns the next handoff.",
                        "evidence_sources": [
                            "company_operation_snapshot",
                            "company_pressure_map",
                        ],
                        "next_step_hint": "company_operation_to_recursive_improvement_cycle",
                        "workflow_names": [
                            "workflow_package_to_composable_building_blocks",
                            "workflow_portfolio_to_operating_system",
                        ],
                    },
                    {
                        "candidate_id": "institutionalize_recursive_operating_review",
                        "category": "operating_pattern",
                        "priority": "P3",
                        "task_ids": ["recursive-alpha", "recursive-beta"],
                        "title": "Publish a recursive operating-review cadence.",
                        "why_now": "The company slice keeps asking for explicit review ownership.",
                        "evidence_sources": [
                            "company_operation_snapshot",
                            "company_pressure_map",
                        ],
                        "next_step_hint": "human_operating_review",
                    },
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "recursive_improvement_cycle.md").write_text(
        "\n".join(
            (
                "# Recursive Improvement Cycle",
                "",
                "## Workflow Portfolio",
                "- `stabilize_portfolio_governance_handoff`.",
                "",
                "## Workflow Packages",
                "- `refine_company_cycle_package_contract`.",
                "",
                "## Evaluation / Refinement / Decomposition Follow-Through",
                "- `author_eval_suite_for_company_cycle`.",
                "- `decompose_recursive_handoff_evidence`.",
                "",
                "## Composition / Escalation Policy",
                "- `tighten_recursive_escalation_policy`.",
                "",
                "## Operating Patterns",
                "- `institutionalize_recursive_operating_review`.",
                "",
                "## Publication Boundary",
                "- recursive_improvement_publication_only",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    summary = {
        "authoritative_artifacts": [
            "recursive_improvement_cycle",
            "recursive_improvement_summary",
            "recursive_improvement_next_actions",
            "company_pressure_map",
            "recursive_improvement_priority_matrix",
            "recursive_improvement_candidates",
        ],
        "candidate_ids": _CANDIDATE_IDS,
        "focus_task_ids": scoped_task_ids,
        "focus_workflows": focus_workflows,
        "next_action": "Hand this cycle package to workflow_to_eval_suite for company_operation_to_recursive_improvement_cycle, then hand the governance follow-through item to workflow_and_eval_to_refined_workflow_package as a separate follow-on.",
        "priority_categories": _PRIORITY_CATEGORIES,
        "priority_category_counts": {
            "composition_or_escalation_policy": 1,
            "decomposition_follow_through": 1,
            "evaluation_follow_through": 1,
            "operating_pattern": 1,
            "workflow_package": 1,
            "workflow_portfolio": 1,
        },
        "priority_item_ids": _CANDIDATE_IDS,
        "publication_boundary": "recursive_improvement_publication_only",
        "ready_for_publication": True,
        "workflow_name": "company_operation_to_recursive_improvement_cycle",
    }
    if summary_override:
        summary.update(summary_override)
    (workflow_folder / "recursive_improvement_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    (workflow_folder / "recursive_improvement_next_actions.md").write_text(
        next_actions_text
        or (
            "# Recursive Improvement Next Actions\n\n"
            "Boundary: recursive_improvement_publication_only.\n"
            "1. Hand this package to workflow_to_eval_suite for company_operation_to_recursive_improvement_cycle.\n"
            "2. Hand the governance follow-through item to workflow_and_eval_to_refined_workflow_package.\n"
        ),
        encoding="utf-8",
    )

    state = workflow_pkg.CompanyOperationToRecursiveImprovementCycle.State(
        task_title="Company recursive-improvement review",
        sponsor_role="workflow platform",
        desired_outcome="Publish a prioritized recursive improvement cycle package.",
        scoped_task_ids=scoped_task_ids,
        focus_workflows=focus_workflows,
        candidate_ids=_CANDIDATE_IDS,
        priority_item_ids=_CANDIDATE_IDS,
        priority_categories=_PRIORITY_CATEGORIES,
        max_tasks=2,
        max_runs_per_workflow=2,
        max_messages_per_task=2,
    )
    ctx = Context(
        task_id="company-recursive-task",
        run_id="run-1",
        workflow_name="company_operation_to_recursive_improvement_cycle",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "company_operation_to_recursive_improvement_cycle",
        state=state,
        session_store=InMemorySessionStore(),
    )
    return workflow_pkg, state, ctx


def _install_repo_company_operation_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
        "company_operation_to_recursive_improvement_cycle",
        "workflow_and_eval_to_refined_workflow_package",
        "workflow_idea_to_workflow_package",
        "workflow_package_to_composable_building_blocks",
        "workflow_portfolio_to_operating_system",
        "workflow_to_eval_suite",
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


def _seed_company_operation_history(root: Path) -> dict[str, Path]:
    _write_task_operation_record(
        root,
        task_id="recursive-alpha",
        created_at="2026-04-24T09:00:00+00:00",
        updated_at="2026-04-24T09:04:00+00:00",
        request_text="Stabilize the portfolio governance handoff.\n",
        messages=[
            (
                "2026-04-24T09:02:00+00:00",
                "Leadership wants the recursive governance package to explain why decomposition follow-through still lacks a clear owner.",
            ),
            (
                "2026-04-24T09:03:00+00:00",
                "Need the governance handoff to name the next operator before the recursive cycle can close.",
            ),
        ],
    )
    _write_task_operation_record(
        root,
        task_id="recursive-beta",
        created_at="2026-04-24T09:00:00+00:00",
        updated_at="2026-04-24T09:05:00+00:00",
        request_text="Recover the failed decomposition handoff.\n",
        messages=[
            (
                "2026-04-24T09:03:00+00:00",
                "The decomposition workflow still needs a cleaner evidence handoff before the next recursive package can trust it.",
            ),
            (
                "2026-04-24T09:04:00+00:00",
                "Need an explicit operating-review cadence before the next recursive package is approved.",
            ),
        ],
    )
    return {
        "portfolio_success": _write_run_summary_record(
            root,
            task_id="recursive-alpha",
            workflow_name="workflow_portfolio_to_operating_system",
            run_id="run-portfolio-success",
            status="success",
            created_at="2026-04-23T09:00:00+00:00",
            updated_at="2026-04-23T09:05:00+00:00",
            request_text="Publish the last portfolio governance package.\n",
            terminal="SUCCESS",
        ),
        "portfolio_paused": _write_run_summary_record(
            root,
            task_id="recursive-alpha",
            workflow_name="workflow_portfolio_to_operating_system",
            run_id="run-portfolio-paused",
            status="paused",
            created_at="2026-04-24T09:00:00+00:00",
            updated_at="2026-04-24T09:04:00+00:00",
            request_text="Refresh the portfolio governance package after decomposition feedback.\n",
            terminal="PAUSE",
            pending_question="Who owns the next governance handoff?",
        ),
        "refinement_success": _write_run_summary_record(
            root,
            task_id="recursive-alpha",
            workflow_name="workflow_and_eval_to_refined_workflow_package",
            run_id="run-refinement-success",
            status="success",
            created_at="2026-04-24T08:30:00+00:00",
            updated_at="2026-04-24T08:45:00+00:00",
            request_text="Publish the refinement candidate for the governance handoff workflow.\n",
            terminal="SUCCESS",
        ),
        "decomposition_failed": _write_run_summary_record(
            root,
            task_id="recursive-beta",
            workflow_name="workflow_package_to_composable_building_blocks",
            run_id="run-decomposition-failed",
            status="failed",
            created_at="2026-04-24T09:00:00+00:00",
            updated_at="2026-04-24T09:05:00+00:00",
            request_text="Recover the decomposition package after evidence drift.\n",
            terminal="FAIL",
            error="candidate evidence drift",
        ),
    }


def _write_task_operation_record(
    root: Path,
    *,
    task_id: str,
    created_at: str,
    updated_at: str,
    request_text: str,
    messages: list[tuple[str, str]],
) -> Path:
    task_dir = root / ".autoloop" / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "request.md").write_text(request_text, encoding="utf-8")
    (task_dir / "messages.jsonl").write_text(
        "".join(json.dumps({"message": message, "ts": ts}, sort_keys=True) + "\n" for ts, message in messages),
        encoding="utf-8",
    )
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "created_at": created_at,
                "messages_file": str(Path(".autoloop") / "tasks" / task_id / "messages.jsonl"),
                "request_file": str(Path(".autoloop") / "tasks" / task_id / "request.md"),
                "request_updated_at": messages[-1][0] if messages else updated_at,
                "task_id": task_id,
                "updated_at": updated_at,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return task_dir


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
