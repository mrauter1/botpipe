"""Parity gates for the ported labs workflow prompts."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from botpipe import ArtifactHandle, Botpipe
from botpipe.providers import FakeProvider
from labs.workflows._shared import LabWorkflowResult
from labs.workflows.investigation_request_to_evidence_pack import (
    InvestigationRequestToEvidencePack,
)
from labs.workflows.investigation_request_to_evidence_pack import (
    Params as InvestigationParams,
)
from labs.workflows.security_finding_to_verified_remediation import (
    Params as SecurityParams,
)
from labs.workflows.security_finding_to_verified_remediation import (
    SecurityFindingToVerifiedRemediation,
)
from labs.workflows.workflow_idea_to_workflow_package import (
    Params as WorkflowBuilderParams,
)
from labs.workflows.workflow_idea_to_workflow_package import (
    WorkflowIdeaToWorkflowPackage,
)

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / "labs" / "workflows"
EXCLUDED_WORKFLOW = "workflow_run_traces_to_optimization_candidates"
VERIFIER_MARKER = re.compile(
    r"^- Verify the declared phase artifacts—(?P<artifacts>.+)—against the phase "
    r"requirements and require their claims to be internally consistent\.$",
    re.MULTILINE,
)
UNBOUND_INPUT_ALIASES = {
    "invocation_contract",
    "framework_architecture_doc",
    "framework_authoring_doc",
    "workflow_authoring_guidelines",
    "selected_workflow_capability",
    "workflow_capability_snapshot",
    "workflow_portfolio_health_snapshot",
    "company_operation_snapshot",
    "selected_workflow_authoring_surface",
    "baseline_workflow_manifest",
    "baseline_refinement_evidence_summary",
    "selected_workflow_decomposition_surface",
    "baseline_parent_manifest",
    "decomposition_evidence_manifest",
    "selected_workflow_run_history",
    "runtime_cli_module",
}
LEGACY_OUTPUT_ALIASES = {
    "investigation_request_to_evidence_pack": {
        "investigation_objectives",
        "evidence_intake_register",
        "evidence_source_inventory",
        "evidence_coverage_matrix",
        "evidence_findings",
        "evidence_gap_register",
        "evidence_pack_summary",
    },
    "security_finding_to_verified_remediation": {
        "finding_scope_brief",
        "security_evidence_pack_summary",
        "security_evidence_gap_register",
        "security_evidence_pack_receipt",
        "exploit_summary",
        "affected_surface",
        "root_cause_analysis",
        "remediation_options",
        "assessment_summary",
        "selected_remediation_plan",
        "verification_plan",
        "rollout_plan",
        "rollback_safety_plan",
        "remediation_summary",
        "stakeholder_communication_draft",
        "closure_evidence_requirements",
    },
    "task_to_candidate_workflow_set": {
        "candidate_selection_criteria",
        "workflow_candidate_matrix",
        "workflow_gap_analysis",
        "candidate_route_posture",
        "candidate_next_action",
    },
    "workflow_and_eval_to_refined_workflow_package": {
        "refinement_acceptance_criteria",
        "refinement_strategy",
        "workflow_change_plan",
        "regression_guardrails",
        "candidate_workflow_surface",
        "refinement_build_report",
        "candidate_diff_summary",
        "refinement_verification_report",
        "evaluation_delta_report",
        "promotion_record",
        "rollback_plan",
    },
    "workflow_idea_to_workflow_package": {
        "candidate_comparison",
        "selected_workflow_brief",
        "workflow_package_spec",
        "step_contracts",
        "prompt_contract_matrix",
        "verification_plan",
        "generated_package_root",
        "generated_single_file",
        "generated_flow",
        "generated_specs",
        "generated_init",
        "generated_manifest",
        "generated_prompts_dir",
        "generated_assets_dir",
        "generated_prompt_index",
        "generated_layout",
        "generated_doc",
        "generated_test",
        "build_report",
        "verification_report",
        "promotion_record",
        "rollback_plan",
    },
    "workflow_package_to_composable_building_blocks": {
        "decomposition_acceptance_criteria",
        "extraction_strategy",
        "building_block_interface_contracts",
        "parent_rewrite_plan",
        "regression_guardrails",
        "candidate_decomposition_surface",
        "candidate_building_block_index",
        "decomposition_build_report",
        "candidate_diff_summary",
        "composition_migration_guide",
        "promotion_record",
        "rollback_plan",
    },
    "workflow_portfolio_to_operating_system": {
        "portfolio_decision_criteria",
        "workflow_lifecycle_matrix",
        "portfolio_gap_analysis",
    },
}


@dataclass(frozen=True)
class PhasePromptContract:
    workflow: str
    phase: str
    artifacts: tuple[str, ...]
    producer_prompt: Path
    verifier_prompt: Path


def _literal_keyword(call: ast.Call, name: str):
    value = next(item.value for item in call.keywords if item.arg == name)
    return ast.literal_eval(value)


def _phase_contracts() -> list[PhasePromptContract]:
    contracts = []
    for package in sorted(WORKFLOWS.iterdir()):
        source = package / "workflow.py"
        if not source.is_file() or package.name == EXCLUDED_WORKFLOW:
            continue
        for call in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "run_phase"
            ):
                continue
            writes = next(item.value for item in call.keywords if item.arg == "writes")
            assert isinstance(writes, (ast.Tuple, ast.List))
            artifacts = tuple(
                ast.literal_eval(item.args[0]).rsplit(".", 1)[0] for item in writes.elts
            )
            contracts.append(
                PhasePromptContract(
                    workflow=package.name,
                    phase=_literal_keyword(call, "phase"),
                    artifacts=artifacts,
                    producer_prompt=package / _literal_keyword(call, "producer_prompt"),
                    verifier_prompt=package / _literal_keyword(call, "verifier_prompt"),
                )
            )
    return contracts


def _marker_artifacts(pattern: re.Pattern[str], prompt: str) -> tuple[str, ...]:
    match = pattern.search(prompt)
    assert match is not None
    assert len(pattern.findall(prompt)) == 1
    return tuple(re.findall(r"`([^`]+)`", match.group("artifacts")))


def _artifact_handling(prompt: str) -> str:
    return prompt.split("### Artifact handling\n", 1)[1].split(
        "\n### Expected outcome", 1
    )[0]


def _input(request) -> dict:
    return json.loads(request.prompt.split("\n\nInput:\n", 1)[1].split("\n\n", 1)[0])


def _read_artifacts(request) -> dict[str, Path]:
    section = request.prompt.split("\n\nRead these immutable input artifacts:\n", 1)[1]
    return {
        item["name"]: Path(item["path"])
        for item in json.loads(section.split("\n\n", 1)[0])
    }


def _write_artifacts(request) -> dict[str, Path]:
    section = request.prompt.split(
        "\n\nWrite the declared artifacts to these exact paths. "
        "Required files must be created in this turn:\n",
        1,
    )[1]
    return {
        item["name"]: Path(item["path"])
        for item in json.loads(section.split("\n\n", 1)[0])
    }


def _write(request, name: str, value) -> None:
    path = request.artifacts[name]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))


def _producer_result() -> dict:
    return {
        "summary": "Wrote the complete declared artifact set.",
        "evidence_notes": ["Used only the runtime input and declared reads."],
        "candidate_ids": [],
    }


def _accepted(payload: dict, **details) -> dict:
    return {
        "outcome": "accepted",
        "summary": "The declared artifacts satisfy the phase requirements.",
        "authoritative_artifacts": payload["required_artifacts"],
        **details,
    }


def test_all_ported_prompt_artifact_sets_resolve_to_run_phase_declarations():
    contracts = _phase_contracts()
    assert len(contracts) == 46
    assert len({(item.workflow, item.phase) for item in contracts}) == len(contracts)

    for contract in contracts:
        producer = contract.producer_prompt.read_text(encoding="utf-8")
        verifier = contract.verifier_prompt.read_text(encoding="utf-8")
        assert _marker_artifacts(VERIFIER_MARKER, verifier) == contract.artifacts
        handling = _artifact_handling(producer)
        for artifact in contract.artifacts:
            assert f"`{artifact}`" in handling
            assert f"`{artifact}/`" not in producer
            assert f"`{artifact}/`" not in verifier
        for prompt in (producer, verifier):
            assert "## Artifact Contract" not in prompt
            assert "| Artifact | Direction |" not in prompt
            assert "directly in the repository" not in prompt
            assert "repository file creation" not in prompt
            for alias in UNBOUND_INPUT_ALIASES:
                assert f"`{alias}`" not in prompt
            for alias in LEGACY_OUTPUT_ALIASES.get(contract.workflow, set()):
                assert f"`{alias}`" not in prompt


def test_merged_artifact_prompts_retain_the_original_delivery_obligations():
    required_fragments = {
        "workflow_idea_to_workflow_package/prompts/build_producer.md": (
            "complete intended text content",
            "runtime will materialize into a run-owned isolated candidate",
            "`.botpipe/workflows/<package_name>/` with required `flow.py`",
        ),
        "workflow_and_eval_to_refined_workflow_package/prompts/implement_producer.md": (
            "records every candidate file",
            "runtime independently derives `candidate_manifest`",
        ),
        "workflow_package_to_composable_building_blocks/prompts/implement_producer.md": (
            "parent rewrite and building-block inventory",
            "runtime-test footprint",
        ),
        "security_finding_to_verified_remediation/prompts/assessment_producer.md": (
            "affected surfaces",
            "technical-cause analysis",
            "remediation options",
        ),
    }
    for relative, fragments in required_fragments.items():
        prompt = (WORKFLOWS / relative).read_text(encoding="utf-8").lower()
        for fragment in fragments:
            assert fragment in prompt


def test_lab_workflow_result_uses_the_canonical_artifact_handle_json_record(tmp_path):
    snapshot = tmp_path / "snapshots" / "evidence.md"
    source = tmp_path / "evidence.md"
    snapshot.parent.mkdir()
    snapshot.write_text("verified evidence")
    source.write_text("provider output")
    handle = ArtifactHandle(
        name="evidence",
        path=snapshot,
        source_path=source,
        kind="md",
        digest=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
    )
    result = LabWorkflowResult(
        workflow_name="fixture",
        summary="Complete",
        phases=[],
        artifact_names=["evidence"],
        artifacts={"evidence": handle},
        artifact_paths={"evidence": str(snapshot)},
    )

    exported = result.model_dump(mode="json")
    assert exported["artifacts"] == {"evidence": handle.to_record()}
    assert json.loads(result.model_dump_json()) == exported
    restored = LabWorkflowResult.model_validate(exported)
    assert restored.artifacts == {"evidence": handle}


def test_investigation_provider_and_verifier_share_the_runtime_artifact_contract(
    tmp_path,
):
    calls: list[tuple[str, bool]] = []

    def answer(request):
        payload = _input(request)
        phase = payload["phase"]
        producer = bool(request.artifacts)
        calls.append((phase, producer))
        if producer:
            assert tuple(request.artifacts) == tuple(payload["required_artifacts"])
            assert _write_artifacts(request) == {
                name: Path(path) for name, path in request.artifacts.items()
            }
            if phase == "frame_investigation":
                _write(
                    request,
                    "investigation_scope_brief",
                    "# Scope\n\nTrigger: readiness review\n\nObjective: establish release evidence.\n",
                )
                _write(
                    request,
                    "evidence_intake_plan",
                    "# Intake\n\nInspect `test-results.json`; record missing proof.\n",
                )
            else:
                _write(
                    request,
                    "evidence_pack",
                    "# Evidence pack\n\nFinding: the supplied test report passed.\n",
                )
                _write(
                    request,
                    "source_register",
                    {"sources": [{"path": "test-results.json", "confidence": "high"}]},
                )
                _write(request, "evidence_gaps", "# Evidence gaps\n\nNone.\n")
                _write(
                    request,
                    "investigation_summary",
                    {
                        "investigation_kind": "release_readiness",
                        "authoritative_artifacts": payload["required_artifacts"],
                        "ready_for_downstream_assessment": True,
                        "source_count": 1,
                        "finding_count": 1,
                        "unresolved_gap_count": 0,
                        "key_findings": ["The supplied test report passed."],
                    },
                )
            return _producer_result()

        reads = _read_artifacts(request)
        assert tuple(reads) == tuple(payload["required_artifacts"])
        if phase == "frame_investigation":
            assert "Objective:" in reads["investigation_scope_brief"].read_text()
            assert "test-results.json" in reads["evidence_intake_plan"].read_text()
            return _accepted(
                payload,
                evidence_focus=["release evidence"],
            )
        summary = json.loads(reads["investigation_summary"].read_text())
        assert summary["source_count"] == 1
        assert set(reads) == {
            "evidence_pack",
            "source_register",
            "evidence_gaps",
            "investigation_summary",
        }
        return _accepted(
            payload,
            evidence_artifacts=payload["required_artifacts"],
            source_count=1,
            unresolved_gaps=[],
            key_findings=summary["key_findings"],
            ready_for_downstream_assessment=True,
        )

    result = Botpipe(tmp_path, provider=FakeProvider([answer] * 4)).run(
        InvestigationRequestToEvidencePack,
        InvestigationParams(
            investigation_title="Release readiness",
            investigation_kind="release_readiness",
            evidence_paths=["test-results.json"],
        ),
        request="Assemble an evidence pack for the release review.",
    )
    assert result.ok, result.error
    assert calls == [
        ("frame_investigation", True),
        ("frame_investigation", False),
        ("assemble_evidence_pack", True),
        ("assemble_evidence_pack", False),
    ]
    assert set(result.value.artifacts) == {
        "investigation_scope_brief",
        "evidence_intake_plan",
        "evidence_pack",
        "source_register",
        "evidence_gaps",
        "investigation_summary",
    }
    assert set(result.value.artifact_names) == set(result.value.artifacts)


def test_security_artifacts_carry_assessment_remediation_and_closure_evidence(
    tmp_path,
):
    def answer(request):
        payload = _input(request)
        phase = payload["phase"]
        if request.artifacts:
            assert _write_artifacts(request) == {
                name: Path(path) for name, path in request.artifacts.items()
            }
            for name in request.artifacts:
                value = f"# {name}\n\nEvidence-backed content for {phase}.\n"
                if name == "source_register":
                    value = {"sources": [{"path": "finding.md", "confidence": "high"}]}
                elif name == "investigation_summary":
                    value = {
                        "investigation_kind": "security_remediation",
                        "authoritative_artifacts": payload["required_artifacts"],
                        "ready_for_downstream_assessment": True,
                        "source_count": 1,
                        "finding_count": 1,
                        "unresolved_gap_count": 0,
                        "key_findings": [
                            "The missing authorization guard is exploitable."
                        ],
                    }
                elif name == "residual_risk":
                    value = {
                        "authoritative_artifacts": payload["required_artifacts"],
                        "selected_remediation": "Add the authorization guard.",
                        "verification_ready": True,
                        "rollout_ready": True,
                        "summary": "Low residual risk after regression coverage.",
                    }
                elif name == "security_remediation_summary":
                    value = {
                        "selected_remediation": "Add the authorization guard.",
                        "verification_ready": True,
                        "rollout_ready": True,
                        "authoritative_artifacts": payload["required_artifacts"],
                    }
                _write(request, name, value)
            return _producer_result()

        reads = _read_artifacts(request)
        assert tuple(reads) == tuple(payload["required_artifacts"])
        common = {"authoritative_artifacts": payload["required_artifacts"]}
        if phase == "frame_investigation":
            return _accepted(payload, evidence_focus=["authorization boundary"])
        if phase == "assemble_evidence_pack":
            return _accepted(
                payload,
                evidence_artifacts=payload["required_artifacts"],
                source_count=1,
                unresolved_gaps=[],
                key_findings=["The missing authorization guard is exploitable."],
                ready_for_downstream_assessment=True,
            )
        if phase == "assess_security_finding":
            assert set(reads) == {
                "security_assessment",
                "threat_scenario",
                "remediation_acceptance_criteria",
            }
            return _accepted(
                payload,
                assessment_artifacts=payload["required_artifacts"],
                preferred_remediation_option="Add the authorization guard.",
                exploitability="confirmed",
            )
        if phase == "plan_verified_remediation":
            residual = json.loads(reads["residual_risk"].read_text())
            assert residual["selected_remediation"] == "Add the authorization guard."
            return _accepted(
                payload,
                remediation_artifacts=payload["required_artifacts"],
                selected_remediation="Add the authorization guard.",
                verification_ready=True,
                rollout_ready=True,
            )
        summary = json.loads(reads["security_remediation_summary"].read_text())
        assert summary["verification_ready"] and summary["rollout_ready"]
        return _accepted(
            payload,
            package_artifacts=payload["required_artifacts"],
            communication_ready=True,
            closure_ready=True,
            **common,
        )

    with Botpipe(tmp_path, provider=FakeProvider([answer] * 10)) as client:
        result = client.run(
            SecurityFindingToVerifiedRemediation,
            SecurityParams(
                finding_title="Missing authorization guard",
                finding_source="internal_review",
                evidence_paths=["finding.md"],
            ),
            request="Prepare a verified remediation package.",
        )
    assert result.ok, result.error
    assert set(result.value.artifacts) == {
        "security_assessment",
        "threat_scenario",
        "remediation_acceptance_criteria",
        "remediation_plan",
        "verification_evidence",
        "residual_risk",
        "security_remediation_package",
        "security_remediation_summary",
        "security_next_action",
    }
    assert set(result.value.artifact_names) == set(result.value.artifacts)


def test_workflow_builder_materializes_validates_and_rechecks_real_candidate(tmp_path):
    from tests.test_labs import _successful_provider

    (tmp_path / "README.md").write_text("# Candidate source repository\n")
    evaluation_inputs = []

    def answer(request):
        payload = _input(request)
        if payload["phase"] == "evaluate_package" and request.artifacts:
            evaluation_inputs.append(payload)
        return _successful_provider(request)

    with Botpipe(tmp_path, provider=FakeProvider([answer] * 8)) as client:
        result = client.run(
            WorkflowIdeaToWorkflowPackage,
            WorkflowBuilderParams(
                package_name="generated_fixture",
                workflow_kind="end_to_end",
            ),
            request="Build a small durable echo workflow.",
            run_id="generated-real-candidate",
        )
        assert result.ok, result.error
        assert len(evaluation_inputs) == 1
        observed = evaluation_inputs[0]
        candidate = observed["generated_candidate"]
        verified = observed["candidate_manifest"]
        validation = observed["candidate_evaluation"]
        candidate_root = Path(candidate["root"])
        generated = candidate_root / ".botpipe/workflows/generated_fixture/flow.py"
        assert generated.is_file()
        assert validation["success"] is True
        assert [check["kind"] for check in validation["checks"]] == ["compile_probe"]
        assert verified["root"] == str(candidate_root)
        assert verified["changed_paths"] == [
            ".botpipe/workflows/generated_fixture/flow.py"
        ]
        assert verified["files"] == [
            {
                "path": ".botpipe/workflows/generated_fixture/flow.py",
                "sha256": hashlib.sha256(generated.read_bytes()).hexdigest(),
                "size_bytes": generated.stat().st_size,
            }
        ]
        authored = result.value.artifacts["workflow_package_manifest"].read_json()
        assert authored["files"][0]["content"] == generated.read_text()
        clean_replay = client.resume(result.run_id)
        assert clean_replay.ok, clean_replay.error
        generated.write_text("# changed after validation\n")
        changed_replay = client.resume(result.run_id)

    assert changed_replay.status == "failed"
    assert "generated candidate file changed" in (changed_replay.error or "")


def test_workflow_builder_rejects_manifest_that_only_claims_a_file(tmp_path):
    from tests.test_labs import _successful_provider

    (tmp_path / "README.md").write_text("# Candidate source repository\n")

    def answer(request):
        result = _successful_provider(request)
        payload = _input(request)
        if payload["phase"] == "build_package" and request.artifacts:
            path = request.artifacts["workflow_package_manifest"]
            manifest = json.loads(path.read_text())
            manifest["files"][0].pop("content")
            path.write_text(json.dumps(manifest))
        return result

    result = Botpipe(tmp_path, provider=FakeProvider([answer] * 6)).run(
        WorkflowIdeaToWorkflowPackage,
        WorkflowBuilderParams(
            package_name="phantom_fixture",
            workflow_kind="end_to_end",
        ),
        request="Build a workflow whose source must really exist.",
    )
    assert result.status == "failed"
    assert "generated file content must be text" in (result.error or "")


@pytest.mark.parametrize(
    ("authoring_shape", "expected_paths"),
    [
        ("single", {".botpipe/workflows/shaped_fixture.py"}),
        (
            "package",
            {
                "labs/workflows/shaped_fixture/flow.py",
                "labs/workflows/shaped_fixture/specs.py",
                "labs/workflows/shaped_fixture/workflow.toml",
            },
        ),
    ],
)
def test_workflow_builder_preserves_authoring_shape_boundaries(
    tmp_path, authoring_shape, expected_paths
):
    from tests.test_labs import _successful_provider

    workspace = tmp_path / authoring_shape
    workspace.mkdir()
    (workspace / "README.md").write_text("# Candidate source repository\n")
    observed = []

    def answer(request):
        payload = _input(request)
        if payload["phase"] == "evaluate_package" and request.artifacts:
            observed.append(payload["candidate_manifest"])
        return _successful_provider(request)

    result = Botpipe(workspace, provider=FakeProvider([answer] * 8)).run(
        WorkflowIdeaToWorkflowPackage,
        WorkflowBuilderParams(
            package_name="shaped_fixture",
            workflow_kind="end_to_end",
            authoring_shape=authoring_shape,
        ),
        request=f"Build the {authoring_shape} workflow shape.",
    )
    assert result.ok, result.error
    assert set(observed[0]["changed_paths"]) == expected_paths
