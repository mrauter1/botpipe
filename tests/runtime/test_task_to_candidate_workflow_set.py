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


def test_repo_workflows_namespace_discovers_task_to_candidate_workflow_set_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "task_to_candidate_workflow_set" in discovered
    package = discovered["task_to_candidate_workflow_set"]
    assert package.package_name == "task_to_candidate_workflow_set"
    assert "candidate-workflow-set" in package.aliases
    assert package.manifest_path == (REPO_ROOT / "workflows" / "task_to_candidate_workflow_set" / "workflow.toml")


def test_task_to_candidate_workflow_set_package_compiles_with_explicit_control_contracts(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.task_to_candidate_workflow_set")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.TaskToCandidateWorkflowSet)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "capture_workflow_capabilities",
        "frame_candidate_request",
        "analyze_candidate_workflows",
        "package_candidate_workflow_set",
        "publish_candidate_workflow_set",
    )

    frame_step = compiled.steps["frame_candidate_request"]
    assert frame_step.available_routes == (
        "candidate_request_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert frame_step.route_contracts["candidate_request_framed"]["required_artifacts"] == [
        "candidate_request_brief",
        "candidate_selection_criteria",
    ]
    assert frame_step.expected_output_schema is not None

    analysis_step = compiled.steps["analyze_candidate_workflows"]
    assert analysis_step.route_contracts["candidate_workflows_analyzed"]["required_artifacts"] == [
        "workflow_candidate_matrix",
        "workflow_gap_analysis",
        "candidate_route_posture",
    ]
    assert analysis_step.expected_output_schema is not None

    package_step = compiled.steps["package_candidate_workflow_set"]
    assert package_step.route_contracts["candidate_workflow_set_ready"]["required_artifacts"] == [
        "candidate_workflow_set",
        "candidate_workflow_set_summary",
        "candidate_next_action",
    ]
    assert package_step.expected_output_schema is not None


def test_task_to_candidate_workflow_set_package_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "task_to_candidate_workflow_set.md").read_text(encoding="utf-8")

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_task_to_candidate_workflow_set.py",
    ):
        assert required in text


def test_task_to_candidate_workflow_set_package_rejects_blank_task_title(tmp_path: Path) -> None:
    _install_repo_task_to_candidate_workflow_set_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "task_to_candidate_workflow_set").parameters_cls

    with pytest.raises(WorkflowParameterError, match="task_title"):
        coerce_workflow_parameter_mapping(parameters_cls, {"task_title": "   "})


def test_task_to_candidate_workflow_set_package_normalizes_repeatable_inputs(tmp_path: Path) -> None:
    _install_repo_task_to_candidate_workflow_set_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "task_to_candidate_workflow_set").parameters_cls

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
                "Keep the building block at candidate-set publication.",
            ],
            "evidence_expectations": [
                " publish a strategy-ready candidate set ",
                "",
                "publish a strategy-ready candidate set",
                "Keep the builder baseline explicit.",
            ],
        },
    )

    assert normalized == {
        "constraints": [
            "prefer reuse over new authoring",
            "Keep the building block at candidate-set publication.",
        ],
        "desired_outcome": None,
        "evidence_expectations": [
            "publish a strategy-ready candidate set",
            "Keep the builder baseline explicit.",
        ],
        "sponsor_role": "Security Engineering",
        "task_title": "Admin impersonation privilege escalation response",
    }


def test_task_to_candidate_workflow_set_package_runs_and_publishes_terminal_candidate_artifacts(tmp_path: Path) -> None:
    _install_repo_task_to_candidate_workflow_set_package(tmp_path)

    provider = ScriptedLLMProvider(
        producer_turns=[
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
                "framed candidate request\n",
            )[2],
            lambda request: (
                request.artifacts.workflow_candidate_matrix.write_text(
                    "\n".join(
                        (
                            "# Workflow Candidate Matrix",
                            "",
                            "| Candidate | What it solves | Fit | Gaps | Result |",
                            "| --- | --- | --- | --- | --- |",
                            "| `security_finding_to_verified_remediation` | End-to-end security remediation and closure packaging | Strong | Needs task-specific finding parameters only | winner |",
                            "| `investigation_request_to_evidence_pack` | Evidence assembly only | Partial | Stops before remediation and closure packaging | loses because the downstream remediation workflow would still need to be chosen |",
                            "| `workflow_idea_to_workflow_package` | Builder baseline for greenfield authoring | Weak for this task | Portfolio already has a credible remediation workflow | loses because no material fit gap exists |",
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
                            "- Composition is unnecessary because `security_finding_to_verified_remediation` already consumes the evidence-pack building block.",
                            "- Adaptation is unnecessary because the task matches the existing workflow boundary closely.",
                            "- The builder baseline confirms there is no material gap that should pressure `create_new`.",
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
                "analyzed candidate workflows\n",
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
                            "next_action": "Pass this candidate package to task_to_workflow_strategy so it can choose the final run_existing/compose/adapt/create_new route explicitly.",
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
                            "1. Hand this package to `task_to_workflow_strategy`.",
                            "2. Preserve the ranked candidate order and builder-baseline reasoning.",
                            "3. Use `security_finding_to_verified_remediation` as the leading workflow candidate for final strategy selection.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "packaged candidate workflow set\n",
            )[3],
        ],
        verifier_turns=[
            Outcome(
                raw_output="candidate request framed\n",
                tag="candidate_request_framed",
                payload={
                    "summary": "The task trigger, terminal outcome, and candidate-selection criteria are explicit.",
                    "authoritative_artifacts": [
                        "candidate_request_brief",
                        "candidate_selection_criteria",
                    ],
                    "decision_axes": ["terminal outcome", "portfolio fit", "fit gap"],
                },
            ),
            Outcome(
                raw_output="candidate workflows analyzed\n",
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
                raw_output="candidate workflow set ready\n",
                tag="candidate_workflow_set_ready",
                payload={
                    "summary": "The candidate-workflow-set package, summary, and next action are aligned.",
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
                    "next_action": "Pass this candidate package to task_to_workflow_strategy so it can choose the final run_existing/compose/adapt/create_new route explicitly.",
                    "ready_for_strategy_selection": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "task_to_candidate_workflow_set",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-to-candidate-workflow-set-task",
            message="Pentest found privilege escalation in admin impersonation.",
            workflow_params={
                "task_title": "Admin impersonation privilege escalation response",
                "sponsor_role": "security engineering",
                "desired_outcome": "Publish a ranked candidate-workflow set for downstream strategy selection.",
                "constraints": [
                    "Prefer reuse over new authoring when the portfolio fit is credible.",
                    "Keep the building block at candidate-set publication.",
                ],
                "evidence_expectations": [
                    "Need a strategy-ready candidate package.",
                    "Keep the builder baseline explicit.",
                ],
            },
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "task-to-candidate-workflow-set-task"
    workflow_dir = task_dir / "wf_task_to_candidate_workflow_set"
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    capability_snapshot = json.loads((workflow_dir / "workflow_capability_snapshot.json").read_text(encoding="utf-8"))
    candidate_summary = json.loads((workflow_dir / "candidate_workflow_set_summary.json").read_text(encoding="utf-8"))
    candidate_receipt = json.loads((workflow_dir / "candidate_workflow_set_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "SUCCESS"
    assert (workflow_dir / "workflow_capability_snapshot.json").exists()
    assert (workflow_dir / "candidate_request_brief.md").exists()
    assert (workflow_dir / "workflow_candidate_matrix.md").exists()
    assert (workflow_dir / "candidate_route_posture.md").exists()
    assert (workflow_dir / "candidate_workflow_set.md").exists()
    assert (workflow_dir / "candidate_workflow_set_summary.json").exists()
    assert (workflow_dir / "candidate_next_action.md").exists()
    assert (workflow_dir / "candidate_workflow_set_receipt.json").exists()
    assert invocation_contract == {
        "constraints": [
            "Prefer reuse over new authoring when the portfolio fit is credible.",
            "Keep the building block at candidate-set publication.",
        ],
        "desired_outcome": "Publish a ranked candidate-workflow set for downstream strategy selection.",
        "evidence_expectations": [
            "Need a strategy-ready candidate package.",
            "Keep the builder baseline explicit.",
        ],
        "message": "Pentest found privilege escalation in admin impersonation.\n",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "sponsor_role": "security engineering",
        "task_id": "task-to-candidate-workflow-set-task",
        "task_title": "Admin impersonation privilege escalation response",
        "workflow_name": "task_to_candidate_workflow_set",
    }
    assert capability_snapshot["workflow_count"] == 4
    assert {entry["workflow_name"] for entry in capability_snapshot["workflows"]} == {
        "investigation_request_to_evidence_pack",
        "security_finding_to_verified_remediation",
        "task_to_candidate_workflow_set",
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
        "next_action": "Pass this candidate package to task_to_workflow_strategy so it can choose the final run_existing/compose/adapt/create_new route explicitly.",
        "portfolio_posture": "direct_fit",
        "ranked_candidates": [
            "security_finding_to_verified_remediation",
            "investigation_request_to_evidence_pack",
            "workflow_idea_to_workflow_package",
        ],
        "ready_for_strategy_selection": True,
        "recommended_candidate_workflows": ["security_finding_to_verified_remediation"],
    }
    assert candidate_receipt == {
        "authoritative_artifacts": [
            "candidate_workflow_set",
            "candidate_workflow_set_summary",
            "candidate_next_action",
        ],
        "builder_baseline_workflow": "workflow_idea_to_workflow_package",
        "candidate_next_action": str(workflow_dir / "candidate_next_action.md"),
        "candidate_route_posture": str(workflow_dir / "candidate_route_posture.md"),
        "candidate_workflow_set": str(workflow_dir / "candidate_workflow_set.md"),
        "candidate_workflow_set_summary": str(workflow_dir / "candidate_workflow_set_summary.json"),
        "comparison_candidates": [
            "security_finding_to_verified_remediation",
            "investigation_request_to_evidence_pack",
            "workflow_idea_to_workflow_package",
        ],
        "desired_outcome": "Publish a ranked candidate-workflow set for downstream strategy selection.",
        "next_action": "Pass this candidate package to task_to_workflow_strategy so it can choose the final run_existing/compose/adapt/create_new route explicitly.",
        "portfolio_posture": "direct_fit",
        "published": True,
        "ranked_candidates": [
            "security_finding_to_verified_remediation",
            "investigation_request_to_evidence_pack",
            "workflow_idea_to_workflow_package",
        ],
        "recommended_candidate_workflows": ["security_finding_to_verified_remediation"],
        "sponsor_role": "security engineering",
        "task_title": "Admin impersonation privilege escalation response",
        "workflow_candidate_matrix": str(workflow_dir / "workflow_candidate_matrix.md"),
        "workflow_capability_snapshot": str(workflow_dir / "workflow_capability_snapshot.json"),
        "workflow_gap_analysis": str(workflow_dir / "workflow_gap_analysis.md"),
        "workflow_name": "task_to_candidate_workflow_set",
    }
    assert [call.step_name for call in provider.calls] == [
        "frame_candidate_request",
        "frame_candidate_request",
        "analyze_candidate_workflows",
        "analyze_candidate_workflows",
        "package_candidate_workflow_set",
        "package_candidate_workflow_set",
    ]
    assert provider.calls[3].available_routes == (
        "candidate_workflows_analyzed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert provider.calls[5].route_contracts["candidate_workflow_set_ready"]["required_artifacts"] == [
        "candidate_workflow_set",
        "candidate_workflow_set_summary",
        "candidate_next_action",
    ]
    assert (run_dir / "run.json").exists()


def test_task_to_candidate_workflow_set_publish_rejects_summary_without_builder_baseline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_candidate_workflow_set_test_context(
        tmp_path,
        monkeypatch,
        candidate_summary={
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
                "task_to_candidate_workflow_set",
            ],
            "next_action": "Pass the candidate set to task_to_workflow_strategy next.",
            "portfolio_posture": "direct_fit",
            "ranked_candidates": [
                "security_finding_to_verified_remediation",
                "investigation_request_to_evidence_pack",
                "task_to_candidate_workflow_set",
            ],
            "ready_for_strategy_selection": True,
            "recommended_candidate_workflows": ["security_finding_to_verified_remediation"],
        },
    )

    with pytest.raises(ValueError, match="builder baseline"):
        workflow_pkg.TaskToCandidateWorkflowSet.on_publish_candidate_workflow_set(state, ctx)


def test_task_to_candidate_workflow_set_publish_rejects_compose_posture_with_only_one_recommended_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_pkg, state, ctx = _make_publish_candidate_workflow_set_test_context(
        tmp_path,
        monkeypatch,
        candidate_summary={
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
            "next_action": "Pass the candidate set to task_to_workflow_strategy next.",
            "portfolio_posture": "compose_needed",
            "ranked_candidates": [
                "security_finding_to_verified_remediation",
                "investigation_request_to_evidence_pack",
                "workflow_idea_to_workflow_package",
            ],
            "ready_for_strategy_selection": True,
            "recommended_candidate_workflows": ["security_finding_to_verified_remediation"],
        },
        portfolio_posture="compose_needed",
        recommended_candidate_workflows=["security_finding_to_verified_remediation"],
    )

    with pytest.raises(ValueError, match="at least two workflows when portfolio_posture is compose_needed"):
        workflow_pkg.TaskToCandidateWorkflowSet.on_publish_candidate_workflow_set(state, ctx)


def _make_publish_candidate_workflow_set_test_context(
    tmp_path: Path,
    monkeypatch,
    *,
    candidate_summary: dict[str, object],
    portfolio_posture: str = "direct_fit",
    recommended_candidate_workflows: list[str] | None = None,
) -> tuple[object, object, Context]:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.task_to_candidate_workflow_set")
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_task_to_candidate_workflow_set"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)

    (workflow_folder / "workflow_capability_snapshot.json").write_text(
        json.dumps(
            {
                "workflow_count": 4,
                "workflows": [
                    {"workflow_name": "task_to_candidate_workflow_set"},
                    {"workflow_name": "workflow_idea_to_workflow_package"},
                    {"workflow_name": "investigation_request_to_evidence_pack"},
                    {"workflow_name": "security_finding_to_verified_remediation"},
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for name in (
        "workflow_candidate_matrix.md",
        "workflow_gap_analysis.md",
        "candidate_route_posture.md",
        "candidate_workflow_set.md",
        "candidate_next_action.md",
    ):
        (workflow_folder / name).write_text("# Placeholder\n", encoding="utf-8")

    (workflow_folder / "candidate_workflow_set_summary.json").write_text(
        json.dumps(candidate_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    state = workflow_pkg.TaskToCandidateWorkflowSet.State(
        task_title="Admin impersonation privilege escalation response",
        sponsor_role="security engineering",
        desired_outcome="Publish a ranked candidate-workflow set for downstream strategy selection.",
        portfolio_posture=portfolio_posture,
        recommended_candidate_workflows=list(
            recommended_candidate_workflows or candidate_summary["recommended_candidate_workflows"]
        ),
    )
    ctx = Context(
        task_id="task-to-candidate-workflow-set-task",
        run_id="run-1",
        workflow_name="task_to_candidate_workflow_set",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "task_to_candidate_workflow_set",
        state=state,
        session_store=InMemorySessionStore(),
    )
    return workflow_pkg, state, ctx


def _install_repo_task_to_candidate_workflow_set_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
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
