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


def test_repo_workflows_namespace_discovers_task_to_workflow_strategy_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "task_to_workflow_strategy" in discovered
    package = discovered["task_to_workflow_strategy"]
    assert package.package_name == "task_to_workflow_strategy"
    assert "workflow-strategy" in package.aliases
    assert package.manifest_path == (REPO_ROOT / "workflows" / "task_to_workflow_strategy" / "workflow.toml")


def test_task_to_workflow_strategy_package_compiles_with_explicit_control_contracts(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.task_to_workflow_strategy")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.TaskToWorkflowStrategy)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "capture_workflow_portfolio",
        "frame_task",
        "build_candidate_workflow_set",
        "select_strategy",
        "package_strategy",
        "publish_strategy",
    )

    frame_step = compiled.steps["frame_task"]
    assert frame_step.available_routes == (
        "task_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert frame_step.route_contracts["task_framed"]["required_artifacts"] == [
        "task_strategy_brief",
        "workflow_selection_criteria",
    ]
    assert frame_step.expected_output_schema is not None

    selection_step = compiled.steps["select_strategy"]
    assert selection_step.route_contracts["strategy_selected"]["required_artifacts"] == ["strategy_decision"]
    assert selection_step.expected_output_schema is not None

    package_step = compiled.steps["package_strategy"]
    assert package_step.route_contracts["strategy_package_ready"]["required_artifacts"] == [
        "workflow_strategy_package",
        "strategy_summary",
        "strategy_next_action",
    ]
    assert package_step.expected_output_schema is not None

    publish_step = compiled.steps["publish_strategy"]
    assert publish_step.requires == (
        "workflow_portfolio_snapshot",
        "workflow_candidate_matrix",
        "workflow_gap_analysis",
        "candidate_route_posture",
        "candidate_workflow_set",
        "candidate_workflow_set_summary",
        "candidate_next_action",
        "strategy_decision",
        "workflow_strategy_package",
        "strategy_summary",
        "strategy_next_action",
    )


def test_task_to_workflow_strategy_package_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "task_to_workflow_strategy.md").read_text(encoding="utf-8")

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_task_to_workflow_strategy.py",
    ):
        assert required in text


def test_task_to_workflow_strategy_adapt_handoff_docs_and_prompts_reference_adaptation_building_block() -> None:
    doc_text = (REPO_ROOT / "docs" / "workflows" / "task_to_workflow_strategy.md").read_text(encoding="utf-8")
    select_prompt = (
        REPO_ROOT / "workflows" / "task_to_workflow_strategy" / "prompts" / "select_producer.md"
    ).read_text(encoding="utf-8")
    package_prompt = (
        REPO_ROOT / "workflows" / "task_to_workflow_strategy" / "prompts" / "package_producer.md"
    ).read_text(encoding="utf-8")
    verifier_prompt = (
        REPO_ROOT / "workflows" / "task_to_workflow_strategy" / "prompts" / "package_verifier.md"
    ).read_text(encoding="utf-8")
    checklist = (
        REPO_ROOT / "workflows" / "task_to_workflow_strategy" / "assets" / "strategy_package_checklist.md"
    ).read_text(encoding="utf-8")

    for text in (doc_text, select_prompt, package_prompt, verifier_prompt, checklist):
        assert "candidate_workflow_to_adapted_execution_plan" in text


def test_task_to_workflow_strategy_package_rejects_blank_task_title(tmp_path: Path) -> None:
    _install_repo_task_to_workflow_strategy_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "task_to_workflow_strategy").parameters_cls

    with pytest.raises(WorkflowParameterError, match="task_title"):
        coerce_workflow_parameter_mapping(parameters_cls, {"task_title": "   "})


def test_task_to_workflow_strategy_package_normalizes_repeatable_inputs(tmp_path: Path) -> None:
    _install_repo_task_to_workflow_strategy_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "task_to_workflow_strategy").parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "task_title": " Admin impersonation privilege escalation response ",
            "sponsor_role": " Security Engineering ",
            "desired_outcome": " ",
            "constraints": [
                " prefer reuse over new authoring ",
                "",
                "prefer reuse over new authoring",
                "Keep the front door at strategy publication.",
            ],
            "evidence_expectations": [
                " deliver a verified remediation package ",
                "",
                "deliver a verified remediation package",
                "Keep rejected routes explicit.",
            ],
        },
    )

    assert normalized == {
        "constraints": [
            "prefer reuse over new authoring",
            "Keep the front door at strategy publication.",
        ],
        "desired_outcome": None,
        "evidence_expectations": [
            "deliver a verified remediation package",
            "Keep rejected routes explicit.",
        ],
        "sponsor_role": "Security Engineering",
        "task_title": "Admin impersonation privilege escalation response",
    }


def test_task_to_workflow_strategy_package_runs_and_publishes_terminal_strategy_artifacts(tmp_path: Path) -> None:
    _install_repo_task_to_workflow_strategy_package(tmp_path)

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.task_strategy_brief.write_text(
                    "\n".join(
                        (
                            "# Task Strategy Brief",
                            "",
                            "Task: respond to the admin impersonation privilege-escalation finding.",
                            "Sponsor: security engineering.",
                            "Desired outcome: choose the strongest existing workflow strategy for verified remediation work.",
                            "Terminal need: a durable remediation and closure package rather than a one-shot analysis.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.workflow_selection_criteria.write_text(
                    "\n".join(
                        (
                            "# Workflow Selection Criteria",
                            "",
                            "- Prefer an existing end-to-end workflow when it already closes the task to a durable package.",
                            "- Choose composition only when no single workflow reaches the required terminal outcome.",
                            "- Choose adaptation only when the existing workflow is close but materially mismatched.",
                            "- Choose create-new only if the current portfolio has a real fit gap after comparing at least three candidates.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "framed task\n",
            )[2],
            lambda request: (
                request.artifacts.candidate_request_brief.write_text(
                    "\n".join(
                        (
                            "# Candidate Request Brief",
                            "",
                            "Task: respond to the admin impersonation privilege-escalation finding.",
                            "Sponsor: security engineering.",
                            "Desired outcome: publish a ranked candidate-workflow set for downstream strategy selection.",
                            "Terminal need: a durable candidate package rather than a one-shot recommendation.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.candidate_selection_criteria.write_text(
                    "\n".join(
                        (
                            "# Candidate Selection Criteria",
                            "",
                            "- Prefer a direct-fit workflow when it already closes the task to a durable remediation package.",
                            "- Use composition only when no single workflow reaches the required terminal outcome.",
                            "- Use adaptation only when the leading workflow is close but materially mismatched.",
                            "- Treat a material gap as builder pressure only after the current portfolio has been compared explicitly.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "child candidate request framed\n",
            )[2],
            lambda request: (
                request.artifacts.workflow_candidate_matrix.write_text(
                    "\n".join(
                        (
                            "# Workflow Candidate Matrix",
                            "",
                            "| Candidate | What it solves | Fit | Gaps | Best route if chosen | Decision |",
                            "| --- | --- | --- | --- | --- | --- |",
                            "| `security_finding_to_verified_remediation` | End-to-end security remediation and closure packaging | Strong | Needs task-specific finding parameters only | `run_existing` | winner |",
                            "| `investigation_request_to_evidence_pack` | Evidence assembly only | Partial | Stops before remediation and closure packaging | `compose` | loses because downstream remediation would still be missing |",
                            "| `workflow_idea_to_workflow_package` | Builder baseline for greenfield authoring | Weak for this task | Portfolio already has a credible remediation workflow | `create_new` | loses because no material fit gap exists |",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.workflow_gap_analysis.write_text(
                    "\n".join(
                        (
                            "# Workflow Gap Analysis",
                            "",
                            "- The current portfolio already contains an end-to-end workflow that turns a concrete security finding into a verified remediation package.",
                            "- Composition is unnecessary because `security_finding_to_verified_remediation` already composes the evidence-pack building block internally.",
                            "- Adaptation is unnecessary because the task matches the existing workflow boundary closely.",
                            "- `create_new` is not justified because the builder baseline reveals no material fit gap.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.candidate_route_posture.write_text(
                    "\n".join(
                        (
                            "# Candidate Route Posture",
                            "",
                            "Ranked candidates:",
                            "1. `security_finding_to_verified_remediation`",
                            "2. `investigation_request_to_evidence_pack`",
                            "3. `workflow_idea_to_workflow_package`",
                            "",
                            "Portfolio posture: `direct_fit`.",
                            "Downstream strategy selection should choose whether to run the leading workflow as-is, but it should not redo candidate retrieval.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "child candidate workflows analyzed\n",
            )[3],
            lambda request: (
                request.artifacts.candidate_workflow_set.write_text(
                    "\n".join(
                        (
                            "# Candidate Workflow Set",
                            "",
                            "Leading posture: `direct_fit`.",
                            "Ranked candidates:",
                            "1. `security_finding_to_verified_remediation`",
                            "2. `investigation_request_to_evidence_pack`",
                            "3. `workflow_idea_to_workflow_package`",
                            "",
                            "Why the winner matters: it already closes the finding to a durable remediation and closure package.",
                            "This building block stops at candidate-set publication so a downstream strategy layer can choose the final route explicitly.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.candidate_workflow_set_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "candidate_workflow_set",
                                "candidate_workflow_set_summary",
                                "candidate_next_action",
                            ],
                            "builder_baseline_workflow": "workflow_idea_to_workflow_package",
                            "builder_considered": True,
                            "comparison_candidates": [
                                "security_finding_to_verified_remediation",
                                "investigation_request_to_evidence_pack",
                                "workflow_idea_to_workflow_package",
                            ],
                            "next_action": "Use this candidate package to choose the final workflow strategy without redoing candidate retrieval.",
                            "portfolio_posture": "direct_fit",
                            "ranked_candidates": [
                                "security_finding_to_verified_remediation",
                                "investigation_request_to_evidence_pack",
                                "workflow_idea_to_workflow_package",
                            ],
                            "ready_for_strategy_selection": True,
                            "recommended_candidate_workflows": ["security_finding_to_verified_remediation"],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                request.artifacts.candidate_next_action.write_text(
                    "\n".join(
                        (
                            "# Candidate Next Action",
                            "",
                            "1. Use the candidate-workflow-set package to choose the final run_existing/compose/adapt/create_new route.",
                            "2. Preserve the ranked candidate order and builder-baseline reasoning.",
                            "3. Carry `security_finding_to_verified_remediation` forward as the leading workflow candidate.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "child candidate workflow set packaged\n",
            )[3],
            lambda request: (
                request.artifacts.strategy_decision.write_text(
                    "\n".join(
                        (
                            "# Strategy Decision",
                            "",
                            "Selected strategy: `run_existing`.",
                            "Recommended workflow: `security_finding_to_verified_remediation`.",
                            "Rejected routes: `compose`, `adapt`, and `create_new`.",
                            "The child candidate-workflow-set package showed a `direct_fit` posture, so this front-door workflow stops at strategy publication instead of auto-running the selection.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "selected strategy\n",
            )[1],
            lambda request: (
                request.artifacts.workflow_strategy_package.write_text(
                    "\n".join(
                        (
                            "# Workflow Strategy Package",
                            "",
                            "Selected route: `run_existing`.",
                            "Recommended workflow: `security_finding_to_verified_remediation`.",
                            "Child candidate posture: `direct_fit`.",
                            "Why it won: it already closes the finding to a durable remediation and closure package.",
                            "Candidate package input: the child workflow ranked the existing remediation workflow first and kept the builder baseline explicit.",
                            "Carry forward: finding title, sponsor role, affected system, and evidence paths.",
                            "No downstream workflow was executed in this run; this package is the terminal handoff artifact.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.strategy_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "workflow_strategy_package",
                                "strategy_summary",
                                "strategy_next_action",
                            ],
                            "builder_baseline_workflow": "workflow_idea_to_workflow_package",
                            "builder_considered": True,
                            "comparison_candidates": [
                                "security_finding_to_verified_remediation",
                                "investigation_request_to_evidence_pack",
                                "workflow_idea_to_workflow_package",
                            ],
                            "create_new_required": False,
                            "next_action": "Run security_finding_to_verified_remediation with the finding-specific parameters captured in the strategy package.",
                            "ready_for_handoff": True,
                            "recommended_workflows": ["security_finding_to_verified_remediation"],
                            "rejected_routes": ["compose", "adapt", "create_new"],
                            "selected_strategy": "run_existing",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                request.artifacts.strategy_next_action.write_text(
                    "\n".join(
                        (
                            "# Strategy Next Action",
                            "",
                            "1. Run `security_finding_to_verified_remediation`.",
                            "2. Supply the finding title, sponsor role, affected system, and evidence paths from the incoming task.",
                            "3. Keep this strategy package attached to the downstream run so the rejected routes stay explicit.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "packaged strategy\n",
            )[3],
        ],
        verifier_turns=[
            Outcome(
                raw_output="task framed\n",
                tag="task_framed",
                payload={
                    "summary": "The task trigger, terminal outcome, and selection criteria are explicit.",
                    "authoritative_artifacts": [
                        "task_strategy_brief",
                        "workflow_selection_criteria",
                    ],
                    "decision_axes": ["terminal outcome", "portfolio fit", "fit gap"],
                },
            ),
            Outcome(
                raw_output="child candidate request framed\n",
                tag="candidate_request_framed",
                payload={
                    "summary": "The child candidate request and selection criteria are explicit.",
                    "authoritative_artifacts": [
                        "candidate_request_brief",
                        "candidate_selection_criteria",
                    ],
                    "decision_axes": ["terminal outcome", "portfolio fit", "fit gap"],
                },
            ),
            Outcome(
                raw_output="child candidate workflows analyzed\n",
                tag="candidate_workflows_analyzed",
                payload={
                    "summary": "The current portfolio comparison supports a direct-fit posture.",
                    "compared_workflows": [
                        "security_finding_to_verified_remediation",
                        "investigation_request_to_evidence_pack",
                        "workflow_idea_to_workflow_package",
                    ],
                    "ranked_candidates": [
                        "security_finding_to_verified_remediation",
                        "investigation_request_to_evidence_pack",
                        "workflow_idea_to_workflow_package",
                    ],
                    "portfolio_posture": "direct_fit",
                    "builder_considered": True,
                },
            ),
            Outcome(
                raw_output="child candidate workflow set ready\n",
                tag="candidate_workflow_set_ready",
                payload={
                    "summary": "The child candidate-workflow-set package, summary, and next action are aligned.",
                    "comparison_candidates": [
                        "security_finding_to_verified_remediation",
                        "investigation_request_to_evidence_pack",
                        "workflow_idea_to_workflow_package",
                    ],
                    "ranked_candidates": [
                        "security_finding_to_verified_remediation",
                        "investigation_request_to_evidence_pack",
                        "workflow_idea_to_workflow_package",
                    ],
                    "recommended_candidate_workflows": ["security_finding_to_verified_remediation"],
                    "builder_baseline_workflow": "workflow_idea_to_workflow_package",
                    "builder_considered": True,
                    "portfolio_posture": "direct_fit",
                    "authoritative_artifacts": [
                        "candidate_workflow_set",
                        "candidate_workflow_set_summary",
                        "candidate_next_action",
                    ],
                    "next_action": "Use this candidate package to choose the final workflow strategy without redoing candidate retrieval.",
                    "ready_for_strategy_selection": True,
                },
            ),
            Outcome(
                raw_output="strategy selected\n",
                tag="strategy_selected",
                payload={
                    "summary": "The child candidate package supports running the existing security remediation workflow.",
                    "compared_workflows": [
                        "security_finding_to_verified_remediation",
                        "investigation_request_to_evidence_pack",
                        "workflow_idea_to_workflow_package",
                    ],
                    "selected_strategy": "run_existing",
                    "recommended_workflows": ["security_finding_to_verified_remediation"],
                    "builder_considered": True,
                    "rejected_routes": ["compose", "adapt", "create_new"],
                },
            ),
            Outcome(
                raw_output="strategy package ready\n",
                tag="strategy_package_ready",
                payload={
                    "summary": "The strategy package, machine-readable summary, and next action are aligned.",
                    "selected_strategy": "run_existing",
                    "recommended_workflows": ["security_finding_to_verified_remediation"],
                    "authoritative_artifacts": [
                        "workflow_strategy_package",
                        "strategy_summary",
                        "strategy_next_action",
                    ],
                    "next_action": "Run security_finding_to_verified_remediation with the finding-specific parameters captured in the strategy package.",
                    "ready_for_handoff": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "task_to_workflow_strategy",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-to-workflow-strategy-task",
            message="Pentest found privilege escalation in admin impersonation.",
            workflow_params={
                "task_title": "Admin impersonation privilege escalation response",
                "sponsor_role": "security engineering",
                "desired_outcome": "Choose the best existing workflow strategy for verified remediation work.",
                "constraints": [
                    "Prefer reuse over new authoring when the portfolio fit is credible.",
                    "Keep the front door at strategy publication.",
                ],
                "evidence_expectations": [
                    "Need a durable remediation and closure package.",
                    "Keep the rejected routes explicit.",
                ],
            },
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "task-to-workflow-strategy-task"
    workflow_dir = task_dir / "wf_task_to_workflow_strategy"
    child_workflow_dir = task_dir / "wf_task_to_candidate_workflow_set"
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    portfolio_snapshot = json.loads((workflow_dir / "workflow_portfolio_snapshot.json").read_text(encoding="utf-8"))
    candidate_summary = json.loads((workflow_dir / "candidate_workflow_set_summary.json").read_text(encoding="utf-8"))
    strategy_summary = json.loads((workflow_dir / "strategy_summary.json").read_text(encoding="utf-8"))
    strategy_receipt = json.loads((workflow_dir / "strategy_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "SUCCESS"
    assert (workflow_dir / "workflow_portfolio_snapshot.json").exists()
    assert (workflow_dir / "task_strategy_brief.md").exists()
    assert (workflow_dir / "workflow_candidate_matrix.md").exists()
    assert (workflow_dir / "candidate_route_posture.md").exists()
    assert (workflow_dir / "candidate_workflow_set.md").exists()
    assert (workflow_dir / "candidate_workflow_set_summary.json").exists()
    assert (workflow_dir / "candidate_next_action.md").exists()
    assert (workflow_dir / "workflow_strategy_package.md").exists()
    assert (workflow_dir / "strategy_summary.json").exists()
    assert (workflow_dir / "strategy_next_action.md").exists()
    assert (workflow_dir / "strategy_receipt.json").exists()
    assert (child_workflow_dir / "candidate_workflow_set_receipt.json").exists()
    assert not (task_dir / "wf_security_finding_to_verified_remediation").exists()
    assert invocation_contract == {
        "constraints": [
            "Prefer reuse over new authoring when the portfolio fit is credible.",
            "Keep the front door at strategy publication.",
        ],
        "desired_outcome": "Choose the best existing workflow strategy for verified remediation work.",
        "evidence_expectations": [
            "Need a durable remediation and closure package.",
            "Keep the rejected routes explicit.",
        ],
        "message": "Pentest found privilege escalation in admin impersonation.\n",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "sponsor_role": "security engineering",
        "task_id": "task-to-workflow-strategy-task",
        "task_title": "Admin impersonation privilege escalation response",
        "workflow_name": "task_to_workflow_strategy",
    }
    assert portfolio_snapshot["workflow_count"] == 5
    assert {entry["workflow_name"] for entry in portfolio_snapshot["workflows"]} == {
        "investigation_request_to_evidence_pack",
        "security_finding_to_verified_remediation",
        "task_to_candidate_workflow_set",
        "task_to_workflow_strategy",
        "workflow_idea_to_workflow_package",
    }
    assert candidate_summary == {
        "authoritative_artifacts": [
            "candidate_workflow_set",
            "candidate_workflow_set_summary",
            "candidate_next_action",
        ],
        "builder_baseline_workflow": "workflow_idea_to_workflow_package",
        "builder_considered": True,
        "comparison_candidates": [
            "security_finding_to_verified_remediation",
            "investigation_request_to_evidence_pack",
            "workflow_idea_to_workflow_package",
        ],
        "next_action": "Use this candidate package to choose the final workflow strategy without redoing candidate retrieval.",
        "portfolio_posture": "direct_fit",
        "ranked_candidates": [
            "security_finding_to_verified_remediation",
            "investigation_request_to_evidence_pack",
            "workflow_idea_to_workflow_package",
        ],
        "ready_for_strategy_selection": True,
        "recommended_candidate_workflows": ["security_finding_to_verified_remediation"],
    }
    assert strategy_summary == {
        "authoritative_artifacts": [
            "workflow_strategy_package",
            "strategy_summary",
            "strategy_next_action",
        ],
        "builder_baseline_workflow": "workflow_idea_to_workflow_package",
        "builder_considered": True,
        "comparison_candidates": [
            "security_finding_to_verified_remediation",
            "investigation_request_to_evidence_pack",
            "workflow_idea_to_workflow_package",
        ],
        "create_new_required": False,
        "next_action": "Run security_finding_to_verified_remediation with the finding-specific parameters captured in the strategy package.",
        "ready_for_handoff": True,
        "recommended_workflows": ["security_finding_to_verified_remediation"],
        "rejected_routes": ["compose", "adapt", "create_new"],
        "selected_strategy": "run_existing",
    }
    assert strategy_receipt == {
        "authoritative_artifacts": [
            "workflow_strategy_package",
            "strategy_summary",
            "strategy_next_action",
        ],
        "builder_baseline_workflow": "workflow_idea_to_workflow_package",
        "comparison_candidates": [
            "security_finding_to_verified_remediation",
            "investigation_request_to_evidence_pack",
            "workflow_idea_to_workflow_package",
        ],
        "desired_outcome": "Choose the best existing workflow strategy for verified remediation work.",
        "next_action": "Run security_finding_to_verified_remediation with the finding-specific parameters captured in the strategy package.",
        "published": True,
        "recommended_workflows": ["security_finding_to_verified_remediation"],
        "rejected_routes": ["compose", "adapt", "create_new"],
        "selected_strategy": "run_existing",
        "sponsor_role": "security engineering",
        "strategy_next_action": str(workflow_dir / "strategy_next_action.md"),
        "strategy_summary": str(workflow_dir / "strategy_summary.json"),
        "task_title": "Admin impersonation privilege escalation response",
        "workflow_name": "task_to_workflow_strategy",
        "workflow_portfolio_snapshot": str(workflow_dir / "workflow_portfolio_snapshot.json"),
        "workflow_strategy_package": str(workflow_dir / "workflow_strategy_package.md"),
    }
    assert [call.step_name for call in provider.calls] == [
        "frame_task",
        "frame_task",
        "frame_candidate_request",
        "frame_candidate_request",
        "analyze_candidate_workflows",
        "analyze_candidate_workflows",
        "package_candidate_workflow_set",
        "package_candidate_workflow_set",
        "select_strategy",
        "select_strategy",
        "package_strategy",
        "package_strategy",
    ]
    assert provider.calls[7].route_contracts["candidate_workflow_set_ready"]["required_artifacts"] == [
        "candidate_workflow_set",
        "candidate_workflow_set_summary",
        "candidate_next_action",
    ]
    assert provider.calls[9].available_routes == (
        "strategy_selected",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert provider.calls[11].route_contracts["strategy_package_ready"]["required_artifacts"] == [
        "workflow_strategy_package",
        "strategy_summary",
        "strategy_next_action",
    ]
    assert (run_dir / "run.json").exists()


def test_task_to_workflow_strategy_runs_and_publishes_concrete_adapt_handoff_without_widening_summary_fields(
    tmp_path: Path,
) -> None:
    _install_repo_task_to_workflow_strategy_package(tmp_path)

    expected_next_action = (
        "Run candidate_workflow_to_adapted_execution_plan for security_finding_to_verified_remediation "
        "using the task title, sponsor role, constraints, and evidence expectations captured in this strategy package."
    )

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.task_strategy_brief.write_text(
                    "\n".join(
                        (
                            "# Task Strategy Brief",
                            "",
                            "Task: respond to the admin impersonation privilege-escalation finding with a stricter remediation posture.",
                            "Sponsor: security engineering.",
                            "Desired outcome: choose the strongest workflow strategy for a durable adaptation handoff.",
                            "Terminal need: a validated execution-ready handoff without auto-running the selected workflow.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.workflow_selection_criteria.write_text(
                    "\n".join(
                        (
                            "# Workflow Selection Criteria",
                            "",
                            "- Prefer adaptation when an existing end-to-end workflow is close but still needs task-specific execution shaping.",
                            "- Keep the front door at strategy publication rather than downstream execution.",
                            "- Keep the workflow-builder baseline visible before claiming a create-new gap.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "framed task\n",
            )[2],
            lambda request: (
                request.artifacts.candidate_request_brief.write_text(
                    "\n".join(
                        (
                            "# Candidate Request Brief",
                            "",
                            "Task: respond to the admin impersonation privilege-escalation finding with a stricter remediation posture.",
                            "Sponsor: security engineering.",
                            "Desired outcome: publish a ranked candidate-workflow set for strategy selection.",
                            "Terminal need: preserve reuse over rebuild while keeping execution explicit.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.candidate_selection_criteria.write_text(
                    "\n".join(
                        (
                            "# Candidate Selection Criteria",
                            "",
                            "- Prefer an end-to-end workflow when it already closes the task boundary.",
                            "- Choose adaptation when the leading workflow is credible but needs a task-specific execution plan.",
                            "- Keep builder pressure visible only after at least three candidates are compared.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "child candidate request framed\n",
            )[2],
            lambda request: (
                request.artifacts.workflow_candidate_matrix.write_text(
                    "\n".join(
                        (
                            "# Workflow Candidate Matrix",
                            "",
                            "| Candidate | What it solves | Fit | Gaps | Best route if chosen | Decision |",
                            "| --- | --- | --- | --- | --- | --- |",
                            "| `security_finding_to_verified_remediation` | End-to-end remediation and closure packaging | Strong | Needs a tighter task-specific execution plan for this finding | `adapt` | winner |",
                            "| `investigation_request_to_evidence_pack` | Evidence assembly only | Partial | Stops before remediation and closure | `compose` | loses because a durable remediation handoff would still be missing |",
                            "| `workflow_idea_to_workflow_package` | Builder baseline for greenfield authoring | Weak | No material gap exists because a close workflow already exists | `create_new` | loses because adaptation is credible |",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.workflow_gap_analysis.write_text(
                    "\n".join(
                        (
                            "# Workflow Gap Analysis",
                            "",
                            "- The current portfolio already contains an end-to-end workflow for verified remediation work.",
                            "- Running that workflow as-is would skip the task-specific execution shaping this case needs.",
                            "- Composition alone is still too narrow because the terminal need is a concrete adapted execution handoff.",
                            "- `create_new` is not justified because the builder baseline reveals no durable fit gap.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.candidate_route_posture.write_text(
                    "\n".join(
                        (
                            "# Candidate Route Posture",
                            "",
                            "Ranked candidates:",
                            "1. `security_finding_to_verified_remediation`",
                            "2. `investigation_request_to_evidence_pack`",
                            "3. `workflow_idea_to_workflow_package`",
                            "",
                            "Portfolio posture: `adapt_needed`.",
                            "Downstream strategy selection should choose an explicit adaptation handoff rather than auto-running the leading workflow.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "child candidate workflows analyzed\n",
            )[3],
            lambda request: (
                request.artifacts.candidate_workflow_set.write_text(
                    "\n".join(
                        (
                            "# Candidate Workflow Set",
                            "",
                            "Leading posture: `adapt_needed`.",
                            "Ranked candidates:",
                            "1. `security_finding_to_verified_remediation`",
                            "2. `investigation_request_to_evidence_pack`",
                            "3. `workflow_idea_to_workflow_package`",
                            "",
                            "Why the winner matters: it already owns the remediation boundary, but this task still needs a concrete adaptation handoff before execution.",
                            "This building block stops at candidate-set publication so the front door can choose the final route explicitly.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.candidate_workflow_set_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "candidate_workflow_set",
                                "candidate_workflow_set_summary",
                                "candidate_next_action",
                            ],
                            "builder_baseline_workflow": "workflow_idea_to_workflow_package",
                            "builder_considered": True,
                            "comparison_candidates": [
                                "security_finding_to_verified_remediation",
                                "investigation_request_to_evidence_pack",
                                "workflow_idea_to_workflow_package",
                            ],
                            "next_action": "Use this candidate package to choose the final workflow strategy without redoing candidate retrieval.",
                            "portfolio_posture": "adapt_needed",
                            "ranked_candidates": [
                                "security_finding_to_verified_remediation",
                                "investigation_request_to_evidence_pack",
                                "workflow_idea_to_workflow_package",
                            ],
                            "ready_for_strategy_selection": True,
                            "recommended_candidate_workflows": ["security_finding_to_verified_remediation"],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                request.artifacts.candidate_next_action.write_text(
                    "\n".join(
                        (
                            "# Candidate Next Action",
                            "",
                            "1. Use the candidate-workflow-set package to choose the final run_existing/compose/adapt/create_new route.",
                            "2. Preserve the leading `security_finding_to_verified_remediation` recommendation.",
                            "3. Keep downstream execution explicit; the next layer should choose whether to adapt rather than auto-run the workflow.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "child candidate workflow set packaged\n",
            )[3],
            lambda request: (
                request.artifacts.strategy_decision.write_text(
                    "\n".join(
                        (
                            "# Strategy Decision",
                            "",
                            "Selected strategy: `adapt`.",
                            "Recommended workflow: `security_finding_to_verified_remediation`.",
                            "Rejected routes: `run_existing`, `compose`, and `create_new`.",
                            "The child candidate-workflow-set package showed an `adapt_needed` posture, so the concrete downstream handoff is `candidate_workflow_to_adapted_execution_plan`, not direct workflow execution.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "selected strategy\n",
            )[1],
            lambda request: (
                request.artifacts.workflow_strategy_package.write_text(
                    "\n".join(
                        (
                            "# Workflow Strategy Package",
                            "",
                            "Selected route: `adapt`.",
                            "Recommended workflow: `security_finding_to_verified_remediation`.",
                            "Child candidate posture: `adapt_needed`.",
                            "Why it won: the existing remediation workflow already owns the problem boundary but this case needs a task-specific execution plan before the workflow runs.",
                            "Concrete next building block: run `candidate_workflow_to_adapted_execution_plan` for `security_finding_to_verified_remediation` using the task facts captured in this strategy package.",
                            "Carry forward: task title, sponsor role, constraints, evidence expectations, and the finding-specific context from the incoming request.",
                            "No downstream workflow was executed in this run; this package is the terminal handoff artifact.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.strategy_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "workflow_strategy_package",
                                "strategy_summary",
                                "strategy_next_action",
                            ],
                            "builder_baseline_workflow": "workflow_idea_to_workflow_package",
                            "builder_considered": True,
                            "comparison_candidates": [
                                "security_finding_to_verified_remediation",
                                "investigation_request_to_evidence_pack",
                                "workflow_idea_to_workflow_package",
                            ],
                            "create_new_required": False,
                            "next_action": expected_next_action,
                            "ready_for_handoff": True,
                            "recommended_workflows": ["security_finding_to_verified_remediation"],
                            "rejected_routes": ["run_existing", "compose", "create_new"],
                            "selected_strategy": "adapt",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                request.artifacts.strategy_next_action.write_text(
                    "\n".join(
                        (
                            "# Strategy Next Action",
                            "",
                            "1. Run `candidate_workflow_to_adapted_execution_plan`.",
                            "2. Pass `security_finding_to_verified_remediation` as the selected workflow to adapt.",
                            "3. Carry forward the task title, sponsor role, constraints, evidence expectations, and the finding-specific context from this strategy package.",
                            "4. Do not run `security_finding_to_verified_remediation` directly from this front-door workflow.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "packaged strategy\n",
            )[3],
        ],
        verifier_turns=[
            Outcome(
                raw_output="task framed\n",
                tag="task_framed",
                payload={
                    "summary": "The task trigger, terminal outcome, and selection criteria are explicit.",
                    "authoritative_artifacts": [
                        "task_strategy_brief",
                        "workflow_selection_criteria",
                    ],
                    "decision_axes": ["terminal outcome", "portfolio fit", "adaptation need"],
                },
            ),
            Outcome(
                raw_output="child candidate request framed\n",
                tag="candidate_request_framed",
                payload={
                    "summary": "The child candidate request and selection criteria are explicit.",
                    "authoritative_artifacts": [
                        "candidate_request_brief",
                        "candidate_selection_criteria",
                    ],
                    "decision_axes": ["terminal outcome", "portfolio fit", "adaptation need"],
                },
            ),
            Outcome(
                raw_output="child candidate workflows analyzed\n",
                tag="candidate_workflows_analyzed",
                payload={
                    "summary": "The current portfolio comparison supports an adaptation-needed posture.",
                    "compared_workflows": [
                        "security_finding_to_verified_remediation",
                        "investigation_request_to_evidence_pack",
                        "workflow_idea_to_workflow_package",
                    ],
                    "ranked_candidates": [
                        "security_finding_to_verified_remediation",
                        "investigation_request_to_evidence_pack",
                        "workflow_idea_to_workflow_package",
                    ],
                    "portfolio_posture": "adapt_needed",
                    "builder_considered": True,
                },
            ),
            Outcome(
                raw_output="child candidate workflow set ready\n",
                tag="candidate_workflow_set_ready",
                payload={
                    "summary": "The child candidate-workflow-set package, summary, and next action are aligned.",
                    "comparison_candidates": [
                        "security_finding_to_verified_remediation",
                        "investigation_request_to_evidence_pack",
                        "workflow_idea_to_workflow_package",
                    ],
                    "ranked_candidates": [
                        "security_finding_to_verified_remediation",
                        "investigation_request_to_evidence_pack",
                        "workflow_idea_to_workflow_package",
                    ],
                    "recommended_candidate_workflows": ["security_finding_to_verified_remediation"],
                    "builder_baseline_workflow": "workflow_idea_to_workflow_package",
                    "builder_considered": True,
                    "portfolio_posture": "adapt_needed",
                    "authoritative_artifacts": [
                        "candidate_workflow_set",
                        "candidate_workflow_set_summary",
                        "candidate_next_action",
                    ],
                    "next_action": "Use this candidate package to choose the final workflow strategy without redoing candidate retrieval.",
                    "ready_for_strategy_selection": True,
                },
            ),
            Outcome(
                raw_output="strategy selected\n",
                tag="strategy_selected",
                payload={
                    "summary": "The child candidate package supports an explicit adaptation handoff for the existing security remediation workflow.",
                    "compared_workflows": [
                        "security_finding_to_verified_remediation",
                        "investigation_request_to_evidence_pack",
                        "workflow_idea_to_workflow_package",
                    ],
                    "selected_strategy": "adapt",
                    "recommended_workflows": ["security_finding_to_verified_remediation"],
                    "builder_considered": True,
                    "rejected_routes": ["run_existing", "compose", "create_new"],
                },
            ),
            Outcome(
                raw_output="strategy package ready\n",
                tag="strategy_package_ready",
                payload={
                    "summary": "The adapt handoff is concrete, uses the existing summary field set, and stays at strategy publication.",
                    "selected_strategy": "adapt",
                    "recommended_workflows": ["security_finding_to_verified_remediation"],
                    "authoritative_artifacts": [
                        "workflow_strategy_package",
                        "strategy_summary",
                        "strategy_next_action",
                    ],
                    "next_action": expected_next_action,
                    "ready_for_handoff": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "task_to_workflow_strategy",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-to-workflow-strategy-adapt-task",
            message="Pentest found a privilege-escalation variant that needs a stricter remediation execution plan.",
            workflow_params={
                "task_title": "Admin impersonation privilege escalation adaptation plan",
                "sponsor_role": "security engineering",
                "desired_outcome": "Choose the best workflow strategy for an explicit adaptation handoff.",
                "constraints": [
                    "Prefer adaptation over new authoring when the existing workflow is close.",
                    "Keep the front door at strategy publication.",
                ],
                "evidence_expectations": [
                    "Need a durable adapted execution handoff.",
                    "Keep downstream workflow execution explicit.",
                ],
            },
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "task-to-workflow-strategy-adapt-task"
    workflow_dir = task_dir / "wf_task_to_workflow_strategy"
    strategy_summary = json.loads((workflow_dir / "strategy_summary.json").read_text(encoding="utf-8"))
    strategy_receipt = json.loads((workflow_dir / "strategy_receipt.json").read_text(encoding="utf-8"))
    workflow_strategy_package = (workflow_dir / "workflow_strategy_package.md").read_text(encoding="utf-8")
    strategy_next_action = (workflow_dir / "strategy_next_action.md").read_text(encoding="utf-8")

    assert result.terminal == "SUCCESS"
    assert strategy_summary == {
        "authoritative_artifacts": [
            "workflow_strategy_package",
            "strategy_summary",
            "strategy_next_action",
        ],
        "builder_baseline_workflow": "workflow_idea_to_workflow_package",
        "builder_considered": True,
        "comparison_candidates": [
            "security_finding_to_verified_remediation",
            "investigation_request_to_evidence_pack",
            "workflow_idea_to_workflow_package",
        ],
        "create_new_required": False,
        "next_action": expected_next_action,
        "ready_for_handoff": True,
        "recommended_workflows": ["security_finding_to_verified_remediation"],
        "rejected_routes": ["run_existing", "compose", "create_new"],
        "selected_strategy": "adapt",
    }
    assert "candidate_workflow_to_adapted_execution_plan" in workflow_strategy_package
    assert "security_finding_to_verified_remediation" in workflow_strategy_package
    assert "candidate_workflow_to_adapted_execution_plan" in strategy_next_action
    assert "security_finding_to_verified_remediation" in strategy_next_action
    assert strategy_receipt["next_action"] == expected_next_action
    assert not (task_dir / "wf_candidate_workflow_to_adapted_execution_plan").exists()
    assert not (task_dir / "wf_security_finding_to_verified_remediation").exists()


def test_task_to_workflow_strategy_publish_strategy_rejects_summary_without_builder_baseline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_strategy_test_context(
        tmp_path,
        monkeypatch,
        strategy_summary={
            "authoritative_artifacts": [
                "workflow_strategy_package",
                "strategy_summary",
                "strategy_next_action",
            ],
            "builder_baseline_workflow": "workflow_idea_to_workflow_package",
            "builder_considered": True,
            "comparison_candidates": [
                "security_finding_to_verified_remediation",
                "investigation_request_to_evidence_pack",
                "incident_to_hardening_program",
            ],
            "create_new_required": False,
            "next_action": "Run security_finding_to_verified_remediation next.",
            "ready_for_handoff": True,
            "recommended_workflows": ["security_finding_to_verified_remediation"],
            "rejected_routes": ["compose", "adapt", "create_new"],
            "selected_strategy": "run_existing",
        },
    )

    with pytest.raises(ValueError, match="builder baseline"):
        workflow_pkg.TaskToWorkflowStrategy.on_publish_strategy(state, ctx)


def test_task_to_workflow_strategy_publish_strategy_rejects_compose_summary_with_only_one_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_strategy_test_context(
        tmp_path,
        monkeypatch,
        strategy_summary={
            "authoritative_artifacts": [
                "workflow_strategy_package",
                "strategy_summary",
                "strategy_next_action",
            ],
            "builder_baseline_workflow": "workflow_idea_to_workflow_package",
            "builder_considered": True,
            "comparison_candidates": [
                "security_finding_to_verified_remediation",
                "investigation_request_to_evidence_pack",
                "workflow_idea_to_workflow_package",
            ],
            "create_new_required": False,
            "next_action": "Compose the evidence pack and remediation workflow next.",
            "ready_for_handoff": True,
            "recommended_workflows": ["security_finding_to_verified_remediation"],
            "rejected_routes": ["run_existing", "adapt", "create_new"],
            "selected_strategy": "compose",
        },
    )

    with pytest.raises(ValueError, match="at least two workflows for compose"):
        workflow_pkg.TaskToWorkflowStrategy.on_publish_strategy(state, ctx)


@pytest.mark.parametrize(
    ("workflow_strategy_package_text", "summary_next_action", "strategy_next_action_text", "match"),
    [
        (
            "\n".join(
                (
                    "# Workflow Strategy Package",
                    "",
                    "Selected route: `adapt`.",
                    "Recommended workflow: `security_finding_to_verified_remediation`.",
                    "Keep the downstream handoff explicit.",
                    "",
                )
            )
            + "\n",
            "Run candidate_workflow_to_adapted_execution_plan for security_finding_to_verified_remediation using the captured task context.",
            "\n".join(
                (
                    "# Strategy Next Action",
                    "",
                    "1. Run `candidate_workflow_to_adapted_execution_plan`.",
                    "2. Pass `security_finding_to_verified_remediation` as the selected workflow.",
                    "",
                )
            )
            + "\n",
            "workflow_strategy_package\\.md must name candidate_workflow_to_adapted_execution_plan",
        ),
        (
            "\n".join(
                (
                    "# Workflow Strategy Package",
                    "",
                    "Run `candidate_workflow_to_adapted_execution_plan` for `security_finding_to_verified_remediation`.",
                    "",
                )
            )
            + "\n",
            "Run candidate_workflow_to_adapted_execution_plan using the captured task context.",
            "\n".join(
                (
                    "# Strategy Next Action",
                    "",
                    "1. Run `candidate_workflow_to_adapted_execution_plan`.",
                    "2. Pass `security_finding_to_verified_remediation` as the selected workflow.",
                    "",
                )
            )
            + "\n",
            "strategy_summary\\.json next_action must name the selected workflow",
        ),
        (
            "\n".join(
                (
                    "# Workflow Strategy Package",
                    "",
                    "Run `candidate_workflow_to_adapted_execution_plan` for `security_finding_to_verified_remediation`.",
                    "",
                )
            )
            + "\n",
            "Run candidate_workflow_to_adapted_execution_plan for security_finding_to_verified_remediation using the captured task context.",
            "\n".join(
                (
                    "# Strategy Next Action",
                    "",
                    "1. Pass `security_finding_to_verified_remediation` as the selected workflow.",
                    "2. Keep downstream execution explicit.",
                    "",
                )
            )
            + "\n",
            "strategy_next_action\\.md must name candidate_workflow_to_adapted_execution_plan",
        ),
    ],
)
def test_task_to_workflow_strategy_publish_strategy_rejects_non_concrete_adapt_handoff(
    tmp_path: Path,
    monkeypatch,
    workflow_strategy_package_text: str,
    summary_next_action: str,
    strategy_next_action_text: str,
    match: str,
) -> None:
    workflow_pkg, state, ctx = _make_publish_strategy_test_context(
        tmp_path,
        monkeypatch,
        strategy_summary={
            "authoritative_artifacts": [
                "workflow_strategy_package",
                "strategy_summary",
                "strategy_next_action",
            ],
            "builder_baseline_workflow": "workflow_idea_to_workflow_package",
            "builder_considered": True,
            "comparison_candidates": [
                "security_finding_to_verified_remediation",
                "investigation_request_to_evidence_pack",
                "workflow_idea_to_workflow_package",
            ],
            "create_new_required": False,
            "next_action": summary_next_action,
            "ready_for_handoff": True,
            "recommended_workflows": ["security_finding_to_verified_remediation"],
            "rejected_routes": ["run_existing", "compose", "create_new"],
            "selected_strategy": "adapt",
        },
        workflow_strategy_package_text=workflow_strategy_package_text,
        strategy_next_action_text=strategy_next_action_text,
    )

    with pytest.raises(ValueError, match=match):
        workflow_pkg.TaskToWorkflowStrategy.on_publish_strategy(state, ctx)


def _make_publish_strategy_test_context(
    tmp_path: Path,
    monkeypatch,
    *,
    strategy_summary: dict[str, object],
    candidate_workflow_set_summary: dict[str, object] | None = None,
    workflow_strategy_package_text: str | None = None,
    strategy_next_action_text: str | None = None,
) -> tuple[object, object, Context]:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.task_to_workflow_strategy")
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_task_to_workflow_strategy"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)

    for name in (
        "workflow_portfolio_snapshot.json",
        "workflow_candidate_matrix.md",
        "workflow_gap_analysis.md",
        "candidate_route_posture.md",
        "candidate_workflow_set.md",
        "candidate_next_action.md",
        "strategy_decision.md",
    ):
        (workflow_folder / name).write_text("{}\n" if name.endswith(".json") else "# Placeholder\n", encoding="utf-8")

    (workflow_folder / "workflow_strategy_package.md").write_text(
        workflow_strategy_package_text or "# Placeholder\n",
        encoding="utf-8",
    )
    (workflow_folder / "strategy_next_action.md").write_text(
        strategy_next_action_text or "# Placeholder\n",
        encoding="utf-8",
    )

    if candidate_workflow_set_summary is None:
        posture = {
            "run_existing": "direct_fit",
            "compose": "compose_needed",
            "adapt": "adapt_needed",
            "create_new": "material_gap",
        }[str(strategy_summary["selected_strategy"])]
        candidate_workflow_set_summary = {
            "authoritative_artifacts": [
                "candidate_workflow_set",
                "candidate_workflow_set_summary",
                "candidate_next_action",
            ],
            "builder_baseline_workflow": "workflow_idea_to_workflow_package",
            "builder_considered": True,
            "comparison_candidates": list(strategy_summary["comparison_candidates"]),
            "next_action": "Use this candidate package to choose the final workflow strategy without redoing candidate retrieval.",
            "portfolio_posture": posture,
            "ranked_candidates": list(strategy_summary["comparison_candidates"]),
            "ready_for_strategy_selection": True,
            "recommended_candidate_workflows": list(strategy_summary["recommended_workflows"]),
        }

    (workflow_folder / "candidate_workflow_set_summary.json").write_text(
        json.dumps(candidate_workflow_set_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    (workflow_folder / "strategy_summary.json").write_text(
        json.dumps(strategy_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    state = workflow_pkg.TaskToWorkflowStrategy.State(
        task_title="Admin impersonation privilege escalation response",
        sponsor_role="security engineering",
        desired_outcome="Choose the best existing workflow strategy for verified remediation work.",
        selected_strategy=strategy_summary["selected_strategy"],
        recommended_workflows=list(strategy_summary["recommended_workflows"]),
    )
    ctx = Context(
        task_id="task-to-workflow-strategy-task",
        run_id="run-1",
        workflow_name="task_to_workflow_strategy",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "task_to_workflow_strategy",
        state=state,
        session_store=InMemorySessionStore(),
    )
    return workflow_pkg, state, ctx


def _install_repo_task_to_workflow_strategy_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
        "task_to_workflow_strategy",
        "task_to_candidate_workflow_set",
        "workflow_idea_to_workflow_package",
        "investigation_request_to_evidence_pack",
        "security_finding_to_verified_remediation",
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
