from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

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
from core.primitives import Outcome


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


def test_repo_workflows_namespace_discovers_release_go_no_go_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "release_candidate_to_go_no_go" in discovered
    package = discovered["release_candidate_to_go_no_go"]
    assert package.package_name == "release_candidate_to_go_no_go"
    assert "release-go-no-go" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "workflows" / "release_candidate_to_go_no_go" / "workflow.toml"
    )


def test_release_go_no_go_package_compiles_with_explicit_control_contracts(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.release_candidate_to_go_no_go")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.ReleaseCandidateToGoNoGo)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "frame_release",
        "assemble_evidence_pack",
        "assess_go_no_go",
        "prepare_decision_package",
        "publish_decision",
    )

    frame_step = compiled.steps["frame_release"]
    assert frame_step.available_routes == (
        "release_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(compiled.route("frame_release", "release_framed").required_writes) == [
        "frame_release.release_scope_brief",
        "frame_release.decision_criteria",
        "frame_release.evidence_intake_register",
    ]
    assert compiled.route("frame_release", "release_framed").handoff == (
        "Locks the release framing so evidence assembly can proceed against a fixed gate."
    )
    assert frame_step.expected_output_schema is not None

    assessment_step = compiled.steps["assess_go_no_go"]
    assert list(compiled.route("assess_go_no_go", "assessment_ready").required_writes) == [
        "assess_go_no_go.go_no_go_assessment",
        "assess_go_no_go.risk_register",
        "assess_go_no_go.decision_summary",
    ]
    assert assessment_step.expected_output_schema is not None

    package_step = compiled.steps["prepare_decision_package"]
    assert list(compiled.route("prepare_decision_package", "decision_package_ready").required_writes) == [
        "prepare_decision_package.release_decision_package",
        "prepare_decision_package.release_communications_draft",
    ]


def test_release_go_no_go_package_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "release_candidate_to_go_no_go.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_release_candidate_to_go_no_go.py",
    ):
        assert required in text


def test_release_go_no_go_prompt_readme_uses_shared_contract_sections() -> None:
    text = (REPO_ROOT / "workflows" / "release_candidate_to_go_no_go" / "prompts" / "README.md").read_text(
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
        "`release_framed`",
        "`evidence_pack_ready`",
        "`assessment_ready`",
        "`decision_package_ready`",
        "`needs_rework`",
        "`needs_replan`",
        "`frame_producer.md` / `frame_verifier.md`",
        "ReleaseDecisionPackagePayload",
        "compact human-readable step contract",
        "Provider raw output is runtime telemetry",
    ):
        assert required in text


def test_release_go_no_go_prompt_inventory_matches_expected_contract_surface() -> None:
    prompt_dir = REPO_ROOT / "workflows" / "release_candidate_to_go_no_go" / "prompts"

    assert sorted(path.name for path in prompt_dir.glob("*.md")) == [
        "README.md",
        "assessment_producer.md",
        "assessment_verifier.md",
        "evidence_producer.md",
        "evidence_verifier.md",
        "frame_producer.md",
        "frame_verifier.md",
        "package_producer.md",
        "package_verifier.md",
    ]


@pytest.mark.parametrize(
    ("prompt_name", "required_markers"),
    (
        (
            "frame_producer.md",
            (
                "`release_scope_brief`",
                "`decision_criteria`",
                "`evidence_intake_register`",
                "`release_framed`",
                "`needs_replan`",
            ),
        ),
        (
            "frame_verifier.md",
            (
                "Required outcome structure",
                "`release_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "`authoritative_artifacts`",
            ),
        ),
        (
            "evidence_producer.md",
            (
                "`release_inventory`",
                "`test_evidence_pack`",
                "`blocking_issues`",
                "`evidence_pack_ready`",
                "`needs_rework`",
            ),
        ),
        (
            "evidence_verifier.md",
            (
                "Required outcome structure",
                "`evidence_pack_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`blocker_artifacts`",
            ),
        ),
        (
            "assessment_producer.md",
            (
                "`go_no_go_assessment`",
                "`risk_register`",
                "`decision_summary`",
                "`assessment_ready`",
                "`conditional_go`",
            ),
        ),
        (
            "assessment_verifier.md",
            (
                "Required outcome structure",
                "`assessment_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`blocking_issue_count`",
            ),
        ),
        (
            "package_producer.md",
            (
                "`release_decision_package`",
                "`release_communications_draft`",
                "`decision_package_ready`",
                "`conditional_go`",
                "`decision_summary`",
            ),
        ),
        (
            "package_verifier.md",
            (
                "Required outcome structure",
                "`decision_package_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`communication_ready`",
            ),
        ),
    ),
)
def test_release_go_no_go_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (REPO_ROOT / "workflows" / "release_candidate_to_go_no_go" / "prompts" / prompt_name).read_text(
        encoding="utf-8"
    )

    _assert_compact_prompt_contract(prompt_name, text, required_markers)


def test_release_go_no_go_package_rejects_blank_release_name(tmp_path: Path) -> None:
    _install_repo_release_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "release_candidate_to_go_no_go").parameters_cls

    with pytest.raises(WorkflowParameterError, match="release_name"):
        coerce_workflow_parameter_mapping(parameters_cls, {"release_name": "   "})


def test_release_go_no_go_package_normalizes_repeatable_evidence_paths(tmp_path: Path) -> None:
    _install_repo_release_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "release_candidate_to_go_no_go").parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "release_name": " 2026.04 ",
            "target_date": " ",
            "deployment_environment": " production ",
            "release_owner": " Release Captain ",
            "evidence_paths": [
                " docs/releases/2026.04.md ",
                "",
                "docs/releases/2026.04.md",
                "reports/test-summary-2026.04.md",
            ],
        },
    )

    assert normalized == {
        "deployment_environment": "production",
        "evidence_paths": [
            "docs/releases/2026.04.md",
            "reports/test-summary-2026.04.md",
        ],
        "release_name": "2026.04",
        "release_owner": "Release Captain",
        "target_date": None,
    }


def test_release_go_no_go_bootstrap_reads_typed_ctx_params(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.release_candidate_to_go_no_go")
    parameters_cls = resolve_workflow_reference(REPO_ROOT, "release_candidate_to_go_no_go").parameters_cls
    assert parameters_cls is not None
    typed_params = parameters_cls.model_validate(
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "release_name": " 2026.04 ",
                "target_date": " 2026-05-01 ",
                "deployment_environment": " staging ",
                "release_owner": " Release Captain ",
                "evidence_paths": [
                    " docs/releases/2026.04.md ",
                    "",
                    "docs/releases/2026.04.md",
                    "reports/test-summary-2026.04.md",
                ],
            },
        )
    )

    task_folder = tmp_path / ".autoloop" / "tasks" / "typed-bootstrap-task"
    workflow_folder = task_folder / "wf_release_candidate_to_go_no_go"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Typed bootstrap request.\n", encoding="utf-8")

    ctx = Context(
        task_id="typed-bootstrap-task",
        run_id="run-1",
        workflow_name="release_candidate_to_go_no_go",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "release_candidate_to_go_no_go",
        state=workflow_pkg.ReleaseCandidateToGoNoGo.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={
            "release_name": "wrong release",
            "target_date": "wrong-date",
            "deployment_environment": "production",
            "release_owner": "Wrong Owner",
            "evidence_paths": ["wrong/path.md"],
        },
    )

    next_state, event = workflow_pkg.ReleaseCandidateToGoNoGo.on_bootstrap(
        workflow_pkg.ReleaseCandidateToGoNoGo.State(),
        ctx,
    )

    assert event.tag == "inputs_prepared"
    assert next_state.release_name == "2026.04"
    assert next_state.target_date == "2026-05-01"
    assert next_state.deployment_environment == "staging"
    assert next_state.release_owner == "Release Captain"
    assert next_state.evidence_paths == [
        "docs/releases/2026.04.md",
        "reports/test-summary-2026.04.md",
    ]
    assert ctx.get_session("frame_session") is not None
    assert ctx.get_session("evidence_session") is not None
    assert ctx.get_session("assessment_session") is not None
    assert ctx.get_session("package_session") is not None

    invocation_contract = json.loads((workflow_folder / "invocation_contract.json").read_text(encoding="utf-8"))
    assert invocation_contract["release_name"] == "2026.04"
    assert invocation_contract["target_date"] == "2026-05-01"
    assert invocation_contract["deployment_environment"] == "staging"
    assert invocation_contract["release_owner"] == "Release Captain"
    assert invocation_contract["evidence_paths"] == next_state.evidence_paths


def test_release_go_no_go_package_runs_and_emits_terminal_receipt(tmp_path: Path) -> None:
    _install_repo_release_package(tmp_path)

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.release_scope_brief.write_text(
                    "\n".join(
                        (
                            "# Release Scope Brief",
                            "",
                            "Release: `2026.04`.",
                            "Target date: `2026-04-24`.",
                            "Environment: `production`.",
                            "Scope: billing, SSO, and audit-log fixes queued for the Friday deployment.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.decision_criteria.write_text(
                    "\n".join(
                        (
                            "# Decision Criteria",
                            "",
                            "- No unresolved Sev-1 blockers.",
                            "- Test evidence must cover the touched surfaces or gaps must be explicit.",
                            "- Rollback procedure must exist and be ready.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.evidence_intake_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Intake Register",
                            "",
                            "- docs/releases/2026.04.md",
                            "- reports/test-summary-2026.04.md",
                            "- runbooks/prod-release-checklist.md",
                            "",
                        )
                    )
                    + "\n"
                ),
                "framed release\n",
            )[3],
            lambda request: (
                request.artifacts.release_inventory.write_text(
                    "\n".join(
                        (
                            "# Release Inventory",
                            "",
                            "- Reviewed release notes and task summary for 2026.04.",
                            "- Candidate includes billing fixes, SSO updates, and audit-log stabilization.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.test_evidence_pack.write_text(
                    "\n".join(
                        (
                            "# Test Evidence Pack",
                            "",
                            "- Regression suite passed for billing and auth surfaces.",
                            "- Load testing evidence is missing for the audit-log path.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.operational_readiness.write_text(
                    "\n".join(
                        (
                            "# Operational Readiness",
                            "",
                            "- Deployment checklist is complete.",
                            "- On-call coverage is assigned.",
                            "- Dashboard link is still pending.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.rollback_readiness.write_text(
                    "\n".join(
                        (
                            "# Rollback Readiness",
                            "",
                            "- Rollback script exists and was reviewed.",
                            "- Database rollback is not required for this release.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.blocking_issues.write_text(
                    "\n".join(
                        (
                            "# Blocking Issues",
                            "",
                            "- Conditional blocker: audit-log dashboard validation is still pending.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "assembled evidence\n",
            )[5],
            lambda request: (
                request.artifacts.go_no_go_assessment.write_text(
                    "\n".join(
                        (
                            "# Go / No-Go Assessment",
                            "",
                            "Recommendation: `conditional_go`.",
                            "Rationale: release evidence is strong, but launch should stay conditional on dashboard validation.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.risk_register.write_text(
                    "\n".join(
                        (
                            "# Risk Register",
                            "",
                            "| Risk | Severity | Mitigation | Status |",
                            "| --- | --- | --- | --- |",
                            "| Audit-log observability gap | medium | Validate dashboard before cutover | conditional |",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.decision_summary.write_text(
                    json.dumps(
                        {
                            "recommended_decision": "conditional_go",
                            "blocking_issue_count": 1,
                            "ready_for_packaging": True,
                            "authoritative_artifacts": [
                                "go_no_go_assessment",
                                "risk_register",
                                "decision_summary",
                            ],
                            "justification_summary": "Proceed if the audit-log dashboard is validated before cutover.",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                "assessed release\n",
            )[3],
            lambda request: (
                request.artifacts.release_decision_package.write_text(
                    "\n".join(
                        (
                            "# Release Decision Package",
                            "",
                            "Decision: `conditional_go`.",
                            "Blocking condition: validate the audit-log dashboard before deployment.",
                            "Rollback posture: reviewed and ready.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.release_communications_draft.write_text(
                    "\n".join(
                        (
                            "# Release Communications Draft",
                            "",
                            "We are prepared to ship release 2026.04 once the audit-log dashboard is validated.",
                            "If the validation slips, hold the release.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "prepared package\n",
            )[2],
        ],
        verifier_turns=[
            Outcome(
                raw_output="release framed\n",
                tag="release_framed",
                payload={
                    "summary": "The release boundary and criteria are explicit.",
                    "authoritative_artifacts": [
                        "release_scope_brief",
                        "decision_criteria",
                        "evidence_intake_register",
                    ],
                    "evidence_focus": ["tests", "rollback", "operations"],
                },
            ),
            Outcome(
                raw_output="evidence ready\n",
                tag="evidence_pack_ready",
                payload={
                    "summary": "The evidence pack covers scope, testing, operations, rollback, and blockers.",
                    "evidence_artifacts": [
                        "release_inventory",
                        "test_evidence_pack",
                        "operational_readiness",
                        "rollback_readiness",
                        "blocking_issues",
                    ],
                    "blocker_artifacts": ["blocking_issues"],
                    "unresolved_gaps": ["audit-log dashboard validation pending"],
                },
            ),
            Outcome(
                raw_output="assessment ready\n",
                tag="assessment_ready",
                payload={
                    "summary": "The assessment supports conditional release packaging.",
                    "evidence_artifacts": [
                        "go_no_go_assessment",
                        "risk_register",
                        "decision_summary",
                    ],
                    "recommended_decision": "conditional_go",
                    "blocking_issue_count": 1,
                },
            ),
            Outcome(
                raw_output="decision package ready\n",
                tag="decision_package_ready",
                payload={
                    "summary": "The package and communication draft are aligned to the assessed recommendation.",
                    "package_artifacts": [
                        "release_decision_package",
                        "release_communications_draft",
                    ],
                    "decision": "conditional_go",
                    "communication_ready": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "release_candidate_to_go_no_go",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="release-go-no-go-task",
            message="We want to ship release 2026.04 on Friday.",
            workflow_params={
                "release_name": "2026.04",
                "target_date": "2026-04-24",
                "deployment_environment": "production",
                "release_owner": "Release Captain",
                "evidence_paths": [
                    "docs/releases/2026.04.md",
                    "reports/test-summary-2026.04.md",
                ],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "release-go-no-go-task" / "wf_release_candidate_to_go_no_go"
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    decision_summary = json.loads((workflow_dir / "decision_summary.json").read_text(encoding="utf-8"))
    decision_receipt = json.loads((workflow_dir / "decision_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert (workflow_dir / "release_scope_brief.md").exists()
    assert (workflow_dir / "decision_criteria.md").exists()
    assert (workflow_dir / "release_inventory.md").exists()
    assert (workflow_dir / "go_no_go_assessment.md").exists()
    assert (workflow_dir / "release_decision_package.md").exists()
    assert (workflow_dir / "release_communications_draft.md").exists()
    assert (workflow_dir / "decision_receipt.json").exists()
    assert invocation_contract == {
        "deployment_environment": "production",
        "evidence_paths": [
            "docs/releases/2026.04.md",
            "reports/test-summary-2026.04.md",
        ],
        "message": "We want to ship release 2026.04 on Friday.\n",
        "release_name": "2026.04",
        "release_owner": "Release Captain",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "target_date": "2026-04-24",
        "task_id": "release-go-no-go-task",
        "workflow_name": "release_candidate_to_go_no_go",
    }
    assert decision_summary == {
        "authoritative_artifacts": [
            "go_no_go_assessment",
            "risk_register",
            "decision_summary",
        ],
        "blocking_issue_count": 1,
        "justification_summary": "Proceed if the audit-log dashboard is validated before cutover.",
        "ready_for_packaging": True,
        "recommended_decision": "conditional_go",
    }
    assert decision_receipt == {
        "blocking_issue_count": 1,
        "communications_draft": str(workflow_dir / "release_communications_draft.md"),
        "decision_package": str(workflow_dir / "release_decision_package.md"),
        "decision_summary": str(workflow_dir / "decision_summary.json"),
        "deployment_environment": "production",
        "published": True,
        "recommended_decision": "conditional_go",
        "release_name": "2026.04",
        "release_owner": "Release Captain",
        "target_date": "2026-04-24",
        "workflow_name": "release_candidate_to_go_no_go",
    }

    assert [call.step_name for call in provider.calls] == [
        "frame_release",
        "frame_release",
        "assemble_evidence_pack",
        "assemble_evidence_pack",
        "assess_go_no_go",
        "assess_go_no_go",
        "prepare_decision_package",
        "prepare_decision_package",
    ]
    assert provider.calls[1].available_routes == (
        "release_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert list(provider.calls[7].route_required_writes["decision_package_ready"]) == [
        "prepare_decision_package.release_decision_package",
        "prepare_decision_package.release_communications_draft",
    ]
    assert provider.calls[7].routes["decision_package_ready"].handoff == (
        "Advances the release workflow to deterministic publication of the terminal receipt."
    )
    assert (run_dir / "run.json").exists()


@pytest.mark.parametrize(
    "summary_payload",
    (
        {
            "blocking_issue_count": 1,
            "ready_for_packaging": False,
        },
        {
            "blocking_issue_count": 1,
            "ready_for_packaging": False,
            "recommended_decision": 1,
        },
        {
            "blocking_issue_count": 1,
            "ready_for_packaging": False,
            "recommended_decision": True,
        },
    ),
)
def test_release_go_no_go_publish_decision_rejects_invalid_recommendation(
    tmp_path: Path,
    monkeypatch,
    summary_payload: dict[str, object],
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.release_candidate_to_go_no_go")
    workflow_folder = tmp_path / "task" / "wf_release_candidate_to_go_no_go"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    (workflow_folder / "decision_summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "release_decision_package.md").write_text("# Decision Package\n", encoding="utf-8")
    (workflow_folder / "release_communications_draft.md").write_text("# Communications\n", encoding="utf-8")

    state = workflow_pkg.ReleaseCandidateToGoNoGo.State(
        release_name="2026.04",
        deployment_environment="production",
        release_owner="Release Captain",
    )
    ctx = Context(
        task_id="release-go-no-go-task",
        run_id="run-1",
        workflow_name="release_candidate_to_go_no_go",
        task_folder=tmp_path / "task",
        workflow_folder=workflow_folder,
        run_folder=tmp_path / "task" / "wf_release_candidate_to_go_no_go" / "runs" / "run-1",
        package_folder=REPO_ROOT / "workflows" / "release_candidate_to_go_no_go",
        state=state,
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(ValueError, match="recommended_decision"):
        workflow_pkg.ReleaseCandidateToGoNoGo.on_publish_decision(state, ctx)

    assert not (workflow_folder / "decision_receipt.json").exists()


def _install_repo_release_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    shutil.copytree(
        REPO_ROOT / "workflows" / "release_candidate_to_go_no_go",
        workflows_root / "release_candidate_to_go_no_go",
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
