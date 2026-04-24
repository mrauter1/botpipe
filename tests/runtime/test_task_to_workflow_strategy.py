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
    assert selection_step.route_contracts["strategy_selected"]["required_artifacts"] == [
        "workflow_candidate_matrix",
        "workflow_gap_analysis",
        "strategy_decision",
    ]
    assert selection_step.expected_output_schema is not None

    package_step = compiled.steps["package_strategy"]
    assert package_step.route_contracts["strategy_package_ready"]["required_artifacts"] == [
        "workflow_strategy_package",
        "strategy_summary",
        "strategy_next_action",
    ]
    assert package_step.expected_output_schema is not None


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
                request.artifacts.strategy_decision.write_text(
                    "\n".join(
                        (
                            "# Strategy Decision",
                            "",
                            "Selected strategy: `run_existing`.",
                            "Recommended workflow: `security_finding_to_verified_remediation`.",
                            "Rejected routes: `compose`, `adapt`, and `create_new`.",
                            "This front-door workflow stops at strategy publication so the downstream execution decision remains explicit and inspectable.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "selected strategy\n",
            )[3],
            lambda request: (
                request.artifacts.workflow_strategy_package.write_text(
                    "\n".join(
                        (
                            "# Workflow Strategy Package",
                            "",
                            "Selected route: `run_existing`.",
                            "Recommended workflow: `security_finding_to_verified_remediation`.",
                            "Why it won: it already closes the finding to a durable remediation and closure package.",
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
                raw_output="strategy selected\n",
                tag="strategy_selected",
                payload={
                    "summary": "The portfolio comparison supports running the existing security remediation workflow.",
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
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    portfolio_snapshot = json.loads((workflow_dir / "workflow_portfolio_snapshot.json").read_text(encoding="utf-8"))
    strategy_summary = json.loads((workflow_dir / "strategy_summary.json").read_text(encoding="utf-8"))
    strategy_receipt = json.loads((workflow_dir / "strategy_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "SUCCESS"
    assert (workflow_dir / "workflow_portfolio_snapshot.json").exists()
    assert (workflow_dir / "task_strategy_brief.md").exists()
    assert (workflow_dir / "workflow_candidate_matrix.md").exists()
    assert (workflow_dir / "workflow_strategy_package.md").exists()
    assert (workflow_dir / "strategy_summary.json").exists()
    assert (workflow_dir / "strategy_next_action.md").exists()
    assert (workflow_dir / "strategy_receipt.json").exists()
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
    assert portfolio_snapshot["workflow_count"] == 4
    assert {entry["workflow_name"] for entry in portfolio_snapshot["workflows"]} == {
        "investigation_request_to_evidence_pack",
        "security_finding_to_verified_remediation",
        "task_to_workflow_strategy",
        "workflow_idea_to_workflow_package",
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
        "select_strategy",
        "select_strategy",
        "package_strategy",
        "package_strategy",
    ]
    assert provider.calls[3].available_routes == (
        "strategy_selected",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert provider.calls[5].route_contracts["strategy_package_ready"]["required_artifacts"] == [
        "workflow_strategy_package",
        "strategy_summary",
        "strategy_next_action",
    ]
    assert (run_dir / "run.json").exists()


def test_task_to_workflow_strategy_publish_strategy_rejects_summary_without_builder_baseline(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
        "strategy_decision.md",
        "workflow_strategy_package.md",
        "strategy_next_action.md",
    ):
        (workflow_folder / name).write_text("{}\n" if name.endswith(".json") else "# Placeholder\n", encoding="utf-8")

    (workflow_folder / "strategy_summary.json").write_text(
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
                    "incident_to_hardening_program",
                ],
                "create_new_required": False,
                "next_action": "Run security_finding_to_verified_remediation next.",
                "ready_for_handoff": True,
                "recommended_workflows": ["security_finding_to_verified_remediation"],
                "rejected_routes": ["compose", "adapt", "create_new"],
                "selected_strategy": "run_existing",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    state = workflow_pkg.TaskToWorkflowStrategy.State(
        task_title="Admin impersonation privilege escalation response",
        sponsor_role="security engineering",
        desired_outcome="Choose the best existing workflow strategy for verified remediation work.",
        selected_strategy="run_existing",
        recommended_workflows=["security_finding_to_verified_remediation"],
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

    with pytest.raises(ValueError, match="builder baseline"):
        workflow_pkg.TaskToWorkflowStrategy.on_publish_strategy(state, ctx)


def _install_repo_task_to_workflow_strategy_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
        "task_to_workflow_strategy",
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
