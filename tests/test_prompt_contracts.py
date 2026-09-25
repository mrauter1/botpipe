"""Behavioral contracts for lab artifacts, verification and materialization."""

from __future__ import annotations

import hashlib
import json
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
from labs.workflows.task_to_candidate_workflow_set import (
    Params as CandidateSetParams,
)
from labs.workflows.task_to_candidate_workflow_set import (
    TaskToCandidateWorkflowSet,
)
from labs.workflows.workflow_idea_to_workflow_package import (
    Params as WorkflowBuilderParams,
)
from labs.workflows.workflow_idea_to_workflow_package import (
    WorkflowIdeaToWorkflowPackage,
)


def _input(request) -> dict:
    return json.loads(request.prompt.split("\n\nInput:\n", 1)[1].split("\n\n", 1)[0])


def _read_artifacts(request) -> dict[str, Path]:
    section = request.prompt.split("\n\nRead these immutable input artifacts:\n", 1)[1]
    return {
        item["name"]: Path(item["path"])
        for item in json.loads(section.split("\n\n", 1)[0])
    }


def _write_artifacts(request) -> dict[str, Path]:
    # Check the actual artifact contract without pinning explanatory wording.
    sections = request.prompt.split("\n\n")
    section = next(part for part in sections if part.startswith("Write the declared artifacts"))
    return {
        item["name"]: Path(item["path"])
        for item in json.loads(section.split("\n", 1)[1])
    }


def _write(request, name: str, value) -> None:
    path = request.artifacts[name]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))


def _accepted(payload: dict, **details) -> dict:
    return {
        "outcome": "accepted",
        "summary": "The declared artifacts satisfy the phase requirements.",
        "authoritative_artifacts": payload["required_artifacts"],
        **details,
    }


def test_lab_prompts_use_typed_producers_and_selective_reviewers():
    workflows = Path("labs/workflows")
    sources = [
        path
        for path in workflows.glob("*/workflow.py")
        if path.parent.name != "improve_workflow"
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)

    assert text.count("run_phase(") == 35
    assert text.count("reviewer_prompt=") == 11
    assert "verifier_prompt=" not in text
    assert not list(workflows.glob("*/prompts/*_verifier.md"))
    assert len(list(workflows.glob("*/prompts/*_reviewer.md"))) == 11
    for prompt in workflows.glob("*/prompts/*_producer.md"):
        contents = prompt.read_text(encoding="utf-8")
        assert "Durable typed phase result" in contents
        assert "phase-specific schema" in contents


def test_candidate_workflow_references_must_exist_in_the_observed_catalog(tmp_path):
    from tests.test_labs import _successful_provider

    def answer(request):
        result = _successful_provider(request)
        payload = _input(request)
        if payload["phase"] == "analyze_candidate_workflows":
            result["compared_workflows"] = ["missing_workflow"]
            result["ranked_candidates"] = ["missing_workflow"]
        return result

    result = Botpipe(tmp_path, provider=FakeProvider([answer] * 3)).run(
        TaskToCandidateWorkflowSet,
        CandidateSetParams(task_title="Find a workflow"),
    )

    assert result.status == "failed"
    assert "unknown workflow" in (result.error or "")


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


def test_investigation_typed_producer_and_review_share_the_artifact_contract(
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
            if phase == "frame_investigation":
                return _accepted(payload, evidence_focus=["release evidence"])
            return _accepted(
                payload,
                evidence_artifacts=payload["required_artifacts"],
                source_count=1,
                unresolved_gaps=[],
                key_findings=["The supplied test report passed."],
                ready_for_downstream_assessment=True,
            )

        reads = _read_artifacts(request)
        assert tuple(reads) == tuple(payload["required_artifacts"])
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
            validation_findings=["Source tracing and gap handling are explicit."],
        )

    result = Botpipe(tmp_path, provider=FakeProvider([answer] * 3)).run(
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
                return _accepted(
                    payload,
                    assessment_artifacts=payload["required_artifacts"],
                    preferred_remediation_option="Add the authorization guard.",
                    exploitability="confirmed",
                )
            if phase == "plan_verified_remediation":
                return _accepted(
                    payload,
                    remediation_artifacts=payload["required_artifacts"],
                    selected_remediation="Add the authorization guard.",
                    verification_ready=True,
                    rollout_ready=True,
                )
            return _accepted(
                payload,
                package_artifacts=payload["required_artifacts"],
                communication_ready=True,
                closure_ready=True,
            )

        reads = _read_artifacts(request)
        assert tuple(reads) == tuple(payload["required_artifacts"])
        common = {"validation_findings": ["The artifacts support the decision."]}
        if phase == "assemble_evidence_pack":
            summary = json.loads(reads["investigation_summary"].read_text())
            assert summary["ready_for_downstream_assessment"] is True
            return _accepted(payload, **common)
        if phase == "assess_security_finding":
            assert set(reads) == {
                "security_assessment",
                "threat_scenario",
                "remediation_acceptance_criteria",
            }
            return _accepted(
                payload,
                **common,
            )
        if phase == "plan_verified_remediation":
            residual = json.loads(reads["residual_risk"].read_text())
            assert residual["selected_remediation"] == "Add the authorization guard."
            return _accepted(
                payload,
                **common,
            )
        summary = json.loads(reads["security_remediation_summary"].read_text())
        assert summary["verification_ready"] and summary["rollout_ready"]
        return _accepted(
            payload,
            **common,
        )

    with Botpipe(tmp_path, provider=FakeProvider([answer] * 9)) as client:
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


def test_workflow_builder_materializes_validates_and_retains_completed_result(tmp_path):
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

    assert changed_replay.ok, changed_replay.error
    assert changed_replay.value == result.value


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


def test_workflow_builder_repairs_recorded_candidate_validation_failure(tmp_path):
    from tests.test_labs import _successful_provider

    (tmp_path / "README.md").write_text("# Candidate source repository\n")
    build_attempts = 0
    saw_runtime_feedback = False

    def answer(request):
        nonlocal build_attempts, saw_runtime_feedback
        payload = _input(request)
        is_build_producer = "workflow_package_manifest" in request.artifacts
        if is_build_producer:
            build_attempts += 1
            saw_runtime_feedback = saw_runtime_feedback or bool(
                payload.get("runtime_validation_feedback")
            )
        result = _successful_provider(request)
        if is_build_producer and build_attempts == 1:
            path = request.artifacts["workflow_package_manifest"]
            manifest = json.loads(path.read_text())
            manifest["files"][0]["content"] = "def broken(:\n"
            path.write_text(json.dumps(manifest))
        return result

    with Botpipe(tmp_path, provider=FakeProvider([answer] * 10)) as client:
        result = client.run(
            WorkflowIdeaToWorkflowPackage,
            WorkflowBuilderParams(
                package_name="repair_fixture",
                workflow_kind="end_to_end",
            ),
            request="Repair a rejected generated candidate.",
            run_id="repaired-generated-candidate",
        )
        replay = client.resume(result.run_id)

    assert result.ok, result.error
    assert replay.ok, replay.error
    assert build_attempts == 2
    assert saw_runtime_feedback is True


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
