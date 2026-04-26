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


def test_repo_workflows_namespace_discovers_incident_hardening_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "incident_to_hardening_program" in discovered
    package = discovered["incident_to_hardening_program"]
    assert package.package_name == "incident_to_hardening_program"
    assert "incident-hardening" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "workflows" / "incident_to_hardening_program" / "workflow.toml"
    )


def test_incident_hardening_package_compiles_with_explicit_control_contracts(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.incident_to_hardening_program")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.IncidentToHardeningProgram)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "frame_incident",
        "assemble_evidence_pack",
        "rank_cause_hypotheses",
        "prepare_hardening_program",
        "publish_incident_package",
    )

    frame_step = compiled.steps["frame_incident"]
    assert frame_step.available_routes == (
        "incident_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert frame_step.route_contracts["incident_framed"]["required_artifacts"] == [
        "incident_scope_brief",
        "response_objectives",
        "evidence_intake_register",
    ]
    assert frame_step.route_contracts["incident_framed"]["work_item_effect"] == (
        "Locks the incident framing so evidence assembly can proceed against a fixed scope and objective set."
    )
    assert frame_step.expected_output_schema is not None

    analysis_step = compiled.steps["rank_cause_hypotheses"]
    assert analysis_step.route_contracts["hypotheses_ranked"]["required_artifacts"] == [
        "cause_hypothesis_ranking",
        "immediate_mitigation_plan",
        "validation_plan",
        "incident_summary",
    ]
    assert analysis_step.expected_output_schema is not None

    package_step = compiled.steps["prepare_hardening_program"]
    assert package_step.route_contracts["hardening_program_ready"]["required_artifacts"] == [
        "hardening_program",
        "hardening_backlog",
        "follow_up_owners",
        "stakeholder_communications_draft",
        "incident_resolution_package",
    ]


def test_incident_hardening_package_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "incident_to_hardening_program.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_incident_to_hardening_program.py",
    ):
        assert required in text


def test_incident_hardening_prompt_readme_uses_shared_contract_sections() -> None:
    text = (REPO_ROOT / "workflows" / "incident_to_hardening_program" / "prompts" / "README.md").read_text(
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
        "`incident_framed`",
        "`evidence_pack_ready`",
        "`hypotheses_ranked`",
        "`hardening_program_ready`",
        "`needs_rework`",
        "`needs_replan`",
        "`frame_producer.md` / `frame_verifier.md`",
        "IncidentHardeningProgramPayload",
        "compact human-readable step contract",
        "Provider raw output is runtime telemetry",
    ):
        assert required in text


def test_incident_hardening_prompt_inventory_matches_expected_contract_surface() -> None:
    prompt_dir = REPO_ROOT / "workflows" / "incident_to_hardening_program" / "prompts"

    assert sorted(path.name for path in prompt_dir.glob("*.md")) == [
        "README.md",
        "analysis_producer.md",
        "analysis_verifier.md",
        "evidence_producer.md",
        "evidence_verifier.md",
        "frame_producer.md",
        "frame_verifier.md",
        "program_producer.md",
        "program_verifier.md",
    ]


@pytest.mark.parametrize(
    ("prompt_name", "required_markers"),
    (
        (
            "frame_producer.md",
            (
                "`incident_scope_brief`",
                "`response_objectives`",
                "`evidence_intake_register`",
                "`incident_framed`",
                "`needs_replan`",
            ),
        ),
        (
            "frame_verifier.md",
            (
                "Required outcome structure",
                "`incident_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "`authoritative_artifacts`",
            ),
        ),
        (
            "evidence_producer.md",
            (
                "`incident_timeline`",
                "`blast_radius`",
                "`evidence_gap_register`",
                "`evidence_pack_ready`",
                "`observability_gaps`",
            ),
        ),
        (
            "evidence_verifier.md",
            (
                "Required outcome structure",
                "`evidence_pack_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`impacted_surfaces`",
            ),
        ),
        (
            "analysis_producer.md",
            (
                "`cause_hypothesis_ranking`",
                "`validation_plan`",
                "`incident_summary`",
                "`hypotheses_ranked`",
                "`recommended_posture`",
            ),
        ),
        (
            "analysis_verifier.md",
            (
                "Required outcome structure",
                "`hypotheses_ranked`",
                "`needs_rework`",
                "`needs_replan`",
                "`primary_hypothesis`",
            ),
        ),
        (
            "program_producer.md",
            (
                "`hardening_program`",
                "`hardening_backlog`",
                "`incident_resolution_package`",
                "`hardening_program_ready`",
                "`recommended_posture`",
            ),
        ),
        (
            "program_verifier.md",
            (
                "Required outcome structure",
                "`hardening_program_ready`",
                "`needs_rework`",
                "`needs_replan`",
                "`owner_ready`",
            ),
        ),
    ),
)
def test_incident_hardening_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (REPO_ROOT / "workflows" / "incident_to_hardening_program" / "prompts" / prompt_name).read_text(
        encoding="utf-8"
    )

    _assert_compact_prompt_contract(prompt_name, text, required_markers)


def test_incident_hardening_package_rejects_blank_incident_title(tmp_path: Path) -> None:
    _install_repo_incident_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "incident_to_hardening_program").parameters_cls

    with pytest.raises(WorkflowParameterError, match="incident_title"):
        coerce_workflow_parameter_mapping(parameters_cls, {"incident_title": "   "})


def test_incident_hardening_package_normalizes_repeatable_evidence_paths(tmp_path: Path) -> None:
    _install_repo_incident_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "incident_to_hardening_program").parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "incident_title": " Payments API 500 spike ",
            "incident_window": " ",
            "affected_system": " payments-api ",
            "severity": " sev1 ",
            "incident_commander": " Incident Lead ",
            "evidence_paths": [
                " incidents/2026-04-22-payments.md ",
                "",
                "incidents/2026-04-22-payments.md",
                "dashboards/payments-api-errors.md",
            ],
        },
    )

    assert normalized == {
        "affected_system": "payments-api",
        "evidence_paths": [
            "incidents/2026-04-22-payments.md",
            "dashboards/payments-api-errors.md",
        ],
        "incident_commander": "Incident Lead",
        "incident_title": "Payments API 500 spike",
        "incident_window": None,
        "severity": "sev1",
    }


def test_incident_hardening_package_runs_and_emits_terminal_receipt(tmp_path: Path) -> None:
    _install_repo_incident_package(tmp_path)

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.incident_scope_brief.write_text(
                    "\n".join(
                        (
                            "# Incident Scope Brief",
                            "",
                            "Incident: `Payments API 500 spike`.",
                            "Window: `2026-04-22T03:11Z/2026-04-22T03:58Z`.",
                            "Affected system: `payments-api`.",
                            "Current framing: elevated 500s during a retry storm impacted payment captures.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.response_objectives.write_text(
                    "\n".join(
                        (
                            "# Response Objectives",
                            "",
                            "- Stabilize payment capture and verify customer impact bounds.",
                            "- Produce a ranked cause hypothesis set and immediate mitigation plan.",
                            "- Publish a hardening backlog and communication draft leadership can use directly.",
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
                            "- incidents/2026-04-22-payments.md",
                            "- dashboards/payments-api-errors.md",
                            "- runbooks/payments-rollback.md",
                            "",
                        )
                    )
                    + "\n"
                ),
                "framed incident\n",
            )[3],
            lambda request: (
                request.artifacts.incident_timeline.write_text(
                    "\n".join(
                        (
                            "# Incident Timeline",
                            "",
                            "- 03:11Z: alerts fired for elevated 500s on `payments-api`.",
                            "- 03:17Z: retry storm observed from checkout workers.",
                            "- 03:31Z: connection pool settings were increased and queue depth began falling.",
                            "- 03:58Z: error rate returned to baseline.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.affected_surface.write_text(
                    "\n".join(
                        (
                            "# Affected Surface",
                            "",
                            "- Payment capture requests returned 500s.",
                            "- Checkout retries amplified queue pressure.",
                            "- No evidence of broader auth or reporting failures.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.blast_radius.write_text(
                    "\n".join(
                        (
                            "# Blast Radius",
                            "",
                            "- Duration: 47 minutes.",
                            "- Impact: delayed and failed captures for a subset of checkout traffic.",
                            "- Containment: limited to the payments path; no data-loss evidence found.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.observability_gaps.write_text(
                    "\n".join(
                        (
                            "# Observability Gaps",
                            "",
                            "- Queue saturation alerts fired late.",
                            "- No dashboard linked connection pool exhaustion to retry volume.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.evidence_gap_register.write_text(
                    "\n".join(
                        (
                            "# Evidence Gap Register",
                            "",
                            "- Need better correlation between retry volume and pool saturation.",
                            "- Customer-impact count is estimated, not yet exact.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "assembled evidence\n",
            )[5],
            lambda request: (
                request.artifacts.cause_hypothesis_ranking.write_text(
                    "\n".join(
                        (
                            "# Cause Hypothesis Ranking",
                            "",
                            "1. Connection pool exhaustion under retry storm pressure.",
                            "2. Slow downstream dependency amplified queue depth.",
                            "3. Alert thresholds were too insensitive to rising saturation.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.immediate_mitigation_plan.write_text(
                    "\n".join(
                        (
                            "# Immediate Mitigation Plan",
                            "",
                            "- Keep the pool-size override in place until retry throttling is deployed.",
                            "- Add temporary queue-depth monitoring to on-call handoff.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.validation_plan.write_text(
                    "\n".join(
                        (
                            "# Validation Plan",
                            "",
                            "- Re-run load tests with retry amplification enabled.",
                            "- Verify queue saturation alerts fire before customer-visible 500s.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.incident_summary.write_text(
                    json.dumps(
                        {
                            "authoritative_artifacts": [
                                "cause_hypothesis_ranking",
                                "immediate_mitigation_plan",
                                "validation_plan",
                                "incident_summary",
                            ],
                            "executive_summary": (
                                "Stabilize with temporary pool headroom, then ship retry controls and better saturation telemetry."
                            ),
                            "hardening_backlog_items": 3,
                            "primary_hypothesis": "Connection pool exhaustion under retry storm pressure.",
                            "recommended_posture": "urgent",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                "ranked hypotheses\n",
            )[4],
            lambda request: (
                request.artifacts.hardening_program.write_text(
                    "\n".join(
                        (
                            "# Hardening Program",
                            "",
                            "Posture: `urgent`.",
                            "Workstreams: retry control, saturation telemetry, queue safety validation.",
                            "Milestones: stabilize, prove under load, then codify alerts and ownership.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.hardening_backlog.write_text(
                    "\n".join(
                        (
                            "# Hardening Backlog",
                            "",
                            "1. Add retry throttling to checkout workers.",
                            "2. Add connection-pool saturation dashboards and alerts.",
                            "3. Add a load-test scenario for retry storms before release.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.follow_up_owners.write_text(
                    "\n".join(
                        (
                            "# Follow-Up Owners",
                            "",
                            "- Payments platform lead: retry throttling.",
                            "- SRE lead: saturation dashboard and alerting.",
                            "- QA lead: retry-storm validation scenario.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.stakeholder_communications_draft.write_text(
                    "\n".join(
                        (
                            "# Stakeholder Communications Draft",
                            "",
                            "The incident has been stabilized, and the leading hypothesis is connection pool exhaustion during a retry storm.",
                            "We are treating the follow-up as urgent and have a three-item hardening program in motion.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.incident_resolution_package.write_text(
                    "\n".join(
                        (
                            "# Incident Resolution Package",
                            "",
                            "Summary: payments 500 spike stabilized after expanding pool headroom.",
                            "Primary hypothesis: connection pool exhaustion under retry storm pressure.",
                            "Next actions: ship retry controls, alert earlier on saturation, and prove the fix under load.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "prepared hardening package\n",
            )[5],
        ],
        verifier_turns=[
            Outcome(
                raw_output="incident framed\n",
                tag="incident_framed",
                payload={
                    "summary": "The incident boundary, response goals, and evidence intake plan are explicit.",
                    "authoritative_artifacts": [
                        "incident_scope_brief",
                        "response_objectives",
                        "evidence_intake_register",
                    ],
                    "evidence_focus": ["timeline", "blast radius", "observability gaps"],
                },
            ),
            Outcome(
                raw_output="evidence ready\n",
                tag="evidence_pack_ready",
                payload={
                    "summary": "The evidence pack covers the timeline, affected surface, blast radius, and key evidence gaps.",
                    "evidence_artifacts": [
                        "incident_timeline",
                        "affected_surface",
                        "blast_radius",
                        "observability_gaps",
                        "evidence_gap_register",
                    ],
                    "unresolved_gaps": [
                        "customer-impact count is estimated",
                    ],
                    "impacted_surfaces": ["payments-api", "checkout retries"],
                },
            ),
            Outcome(
                raw_output="hypotheses ranked\n",
                tag="hypotheses_ranked",
                payload={
                    "summary": "The analysis supports an urgent hardening posture with one leading hypothesis.",
                    "analysis_artifacts": [
                        "cause_hypothesis_ranking",
                        "immediate_mitigation_plan",
                        "validation_plan",
                        "incident_summary",
                    ],
                    "recommended_posture": "urgent",
                    "primary_hypothesis": "Connection pool exhaustion under retry storm pressure.",
                },
            ),
            Outcome(
                raw_output="hardening program ready\n",
                tag="hardening_program_ready",
                payload={
                    "summary": "The hardening package is complete, aligned, and ready for publication.",
                    "package_artifacts": [
                        "hardening_program",
                        "hardening_backlog",
                        "follow_up_owners",
                        "stakeholder_communications_draft",
                        "incident_resolution_package",
                    ],
                    "recommended_posture": "urgent",
                    "owner_ready": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "incident_to_hardening_program",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="incident-hardening-task",
            message="Payments API returned 500s for 47 minutes last night.",
            workflow_params={
                "incident_title": "Payments API 500 spike",
                "incident_window": "2026-04-22T03:11Z/2026-04-22T03:58Z",
                "affected_system": "payments-api",
                "severity": "sev1",
                "incident_commander": "A. Operator",
                "evidence_paths": [
                    "incidents/2026-04-22-payments.md",
                    "dashboards/payments-api-errors.md",
                ],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "incident-hardening-task" / "wf_incident_to_hardening_program"
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    incident_summary = json.loads((workflow_dir / "incident_summary.json").read_text(encoding="utf-8"))
    incident_receipt = json.loads((workflow_dir / "incident_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "SUCCESS"
    assert (workflow_dir / "incident_scope_brief.md").exists()
    assert (workflow_dir / "response_objectives.md").exists()
    assert (workflow_dir / "incident_timeline.md").exists()
    assert (workflow_dir / "cause_hypothesis_ranking.md").exists()
    assert (workflow_dir / "hardening_program.md").exists()
    assert (workflow_dir / "hardening_backlog.md").exists()
    assert (workflow_dir / "follow_up_owners.md").exists()
    assert (workflow_dir / "stakeholder_communications_draft.md").exists()
    assert (workflow_dir / "incident_resolution_package.md").exists()
    assert (workflow_dir / "incident_receipt.json").exists()
    assert invocation_contract == {
        "affected_system": "payments-api",
        "evidence_paths": [
            "incidents/2026-04-22-payments.md",
            "dashboards/payments-api-errors.md",
        ],
        "incident_commander": "A. Operator",
        "incident_title": "Payments API 500 spike",
        "incident_window": "2026-04-22T03:11Z/2026-04-22T03:58Z",
        "message": "Payments API returned 500s for 47 minutes last night.\n",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "severity": "sev1",
        "task_id": "incident-hardening-task",
        "workflow_name": "incident_to_hardening_program",
    }
    assert incident_summary == {
        "authoritative_artifacts": [
            "cause_hypothesis_ranking",
            "immediate_mitigation_plan",
            "validation_plan",
            "incident_summary",
        ],
        "executive_summary": (
            "Stabilize with temporary pool headroom, then ship retry controls and better saturation telemetry."
        ),
        "hardening_backlog_items": 3,
        "primary_hypothesis": "Connection pool exhaustion under retry storm pressure.",
        "recommended_posture": "urgent",
    }
    assert incident_receipt == {
        "affected_system": "payments-api",
        "follow_up_owners": str(workflow_dir / "follow_up_owners.md"),
        "hardening_backlog": str(workflow_dir / "hardening_backlog.md"),
        "hardening_backlog_items": 3,
        "hardening_program": str(workflow_dir / "hardening_program.md"),
        "incident_commander": "A. Operator",
        "incident_resolution_package": str(workflow_dir / "incident_resolution_package.md"),
        "incident_summary": str(workflow_dir / "incident_summary.json"),
        "incident_title": "Payments API 500 spike",
        "incident_window": "2026-04-22T03:11Z/2026-04-22T03:58Z",
        "primary_hypothesis": "Connection pool exhaustion under retry storm pressure.",
        "published": True,
        "recommended_posture": "urgent",
        "severity": "sev1",
        "stakeholder_communications_draft": str(workflow_dir / "stakeholder_communications_draft.md"),
        "workflow_name": "incident_to_hardening_program",
    }

    assert [call.step_name for call in provider.calls] == [
        "frame_incident",
        "frame_incident",
        "assemble_evidence_pack",
        "assemble_evidence_pack",
        "rank_cause_hypotheses",
        "rank_cause_hypotheses",
        "prepare_hardening_program",
        "prepare_hardening_program",
    ]
    assert provider.calls[1].available_routes == (
        "incident_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert provider.calls[7].route_contracts["hardening_program_ready"]["required_artifacts"] == [
        "hardening_program",
        "hardening_backlog",
        "follow_up_owners",
        "stakeholder_communications_draft",
        "incident_resolution_package",
    ]
    assert provider.calls[7].route_contracts["hardening_program_ready"]["work_item_effect"] == (
        "Advances the incident workflow to deterministic publication of the terminal receipt."
    )
    assert (run_dir / "run.json").exists()


@pytest.mark.parametrize(
    ("summary_payload", "match"),
    (
        (
            {
                "authoritative_artifacts": ["incident_summary"],
                "hardening_backlog_items": 3,
                "primary_hypothesis": "Connection pool exhaustion under retry storm pressure.",
            },
            "recommended_posture",
        ),
        (
            {
                "authoritative_artifacts": ["incident_summary"],
                "hardening_backlog_items": 3,
                "primary_hypothesis": "Connection pool exhaustion under retry storm pressure.",
                "recommended_posture": 1,
            },
            "recommended_posture",
        ),
        (
            {
                "authoritative_artifacts": ["incident_summary"],
                "hardening_backlog_items": 3,
                "primary_hypothesis": "Connection pool exhaustion under retry storm pressure.",
                "recommended_posture": True,
            },
            "recommended_posture",
        ),
        (
            {
                "authoritative_artifacts": ["incident_summary"],
                "hardening_backlog_items": 3,
                "recommended_posture": "urgent",
            },
            "primary_hypothesis",
        ),
        (
            {
                "authoritative_artifacts": ["incident_summary"],
                "hardening_backlog_items": 3,
                "primary_hypothesis": 2,
                "recommended_posture": "urgent",
            },
            "primary_hypothesis",
        ),
        (
            {
                "authoritative_artifacts": ["incident_summary"],
                "hardening_backlog_items": 3,
                "primary_hypothesis": False,
                "recommended_posture": "urgent",
            },
            "primary_hypothesis",
        ),
        (
            {
                "authoritative_artifacts": ["incident_summary"],
                "hardening_backlog_items": -1,
                "primary_hypothesis": "Connection pool exhaustion under retry storm pressure.",
                "recommended_posture": "urgent",
            },
            "hardening_backlog_items",
        ),
    ),
)
def test_incident_hardening_publish_rejects_invalid_summary_fields(
    tmp_path: Path,
    monkeypatch,
    summary_payload: dict[str, object],
    match: str,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.incident_to_hardening_program")
    workflow_folder = tmp_path / "task" / "wf_incident_to_hardening_program"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    (workflow_folder / "incident_summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (workflow_folder / "hardening_program.md").write_text("# Hardening Program\n", encoding="utf-8")
    (workflow_folder / "hardening_backlog.md").write_text("# Hardening Backlog\n", encoding="utf-8")
    (workflow_folder / "follow_up_owners.md").write_text("# Follow-Up Owners\n", encoding="utf-8")
    (workflow_folder / "stakeholder_communications_draft.md").write_text("# Communications\n", encoding="utf-8")
    (workflow_folder / "incident_resolution_package.md").write_text("# Incident Resolution Package\n", encoding="utf-8")

    state = workflow_pkg.IncidentToHardeningProgram.State(
        incident_title="Payments API 500 spike",
        affected_system="payments-api",
        severity="sev1",
    )
    ctx = Context(
        task_id="incident-hardening-task",
        run_id="run-1",
        workflow_name="incident_to_hardening_program",
        task_folder=tmp_path / "task",
        workflow_folder=workflow_folder,
        run_folder=tmp_path / "task" / "wf_incident_to_hardening_program" / "runs" / "run-1",
        package_folder=REPO_ROOT / "workflows" / "incident_to_hardening_program",
        state=state,
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(ValueError, match=match):
        workflow_pkg.IncidentToHardeningProgram.on_publish_incident_package(state, ctx)

    assert not (workflow_folder / "incident_receipt.json").exists()


def _install_repo_incident_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    shutil.copytree(
        REPO_ROOT / "workflows" / "incident_to_hardening_program",
        workflows_root / "incident_to_hardening_program",
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
