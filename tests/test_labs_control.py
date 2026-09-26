"""Exercise lab rejection branches against the real durable provider journal."""

from __future__ import annotations

import json
from collections import Counter

import pytest

from botpipe import Botpipe
from botpipe.providers import FakeProvider
from labs.workflows.release_candidate_to_go_no_go import (
    Params,
    ReleaseCandidateToGoNoGo,
)


def _input(request):
    return json.JSONDecoder().raw_decode(request.prompt.split("\n\nInput:\n", 1)[1])[0]


def _release_answer(request, *, outcome="accepted", invalid=False):
    payload = _input(request)
    phase = payload["phase"]
    names = payload["required_artifacts"]
    if request.artifacts:
        for name, path in request.artifacts.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            value = {
                "decision": "go",
                "recommended_decision": "go",
                "blocking_issue_count": 0,
                "executed_checks": ["pytest"],
                "unexecuted_checks": [],
                "communication_ready": True,
            }
            path.write_text(
                json.dumps(value)
                if path.suffix == ".json"
                else f"# {name}\nAccepted evidence."
            )
    producer = bool(request.artifacts)
    common = {
        "outcome": outcome,
        "summary": "Repair the rollout boundary."
        if outcome != "accepted"
        else "Ready for the next phase.",
        "authoritative_artifacts": names,
        "replan_reason": "The rollout boundary changed."
        if outcome == "needs_replan"
        else None,
    }
    if not producer:
        common["validation_findings"] = ["The evidence supports the decision."]
        return common
    if phase == "frame_release":
        common["evidence_focus"] = ["tests", "rollback"]
    elif phase == "assemble_evidence_pack":
        common["evidence_artifacts"] = names
    elif phase == "assess_go_no_go":
        common.update(
            evidence_artifacts=names, recommended_decision="maybe" if invalid else "go"
        )
    elif phase == "prepare_decision_package":
        common.update(package_artifacts=names, decision="go", communication_ready=True)
    return common


def _provider_operations(client, run_id):
    return [
        row for row in client.inspect(run_id)["operations"] if row["kind"] == "provider"
    ]


def test_local_rework_and_backward_replan_preserve_history_and_replay(tmp_path):
    seen = Counter()
    produced = []
    inputs = []

    def provider_response(request):
        payload = _input(request)
        phase = payload["phase"]
        role = "producer" if request.artifacts else "reviewer"
        seen[phase, role] += 1
        if role == "producer":
            produced.append(phase)
            inputs.append(payload)
        outcome = "accepted"
        if (
            role == "reviewer"
            and seen[phase, role] == 1
            and phase == "assemble_evidence_pack"
        ):
            outcome = "needs_rework"
        if (
            role == "producer"
            and phase == "prepare_decision_package"
            and seen[phase, role] == 1
        ):
            outcome = "needs_replan"
        return _release_answer(request, outcome=outcome)

    provider = FakeProvider([provider_response] * 20)
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(ReleaseCandidateToGoNoGo, Params(release_name="release"))
        assert result.ok, result.error
        assert produced == [
            "frame_release",
            "assemble_evidence_pack",
            "assemble_evidence_pack",
            "assess_go_no_go",
            "prepare_decision_package",
            "assess_go_no_go",
            "prepare_decision_package",
        ]
        assert inputs[2]["rework_feedback"]["outcome"] == "needs_rework"
        assert inputs[5]["replan_feedback"]["details"]["outcome"] == "needs_replan"
        assert "prior_phases" not in inputs[5]
        assert len(result.value.phases) == 4
        assert result.value.phases[-1].details["decision"] == "go"
        operations = _provider_operations(client, result.run_id)
        assert len(operations) == len(provider.calls)
        assert all(row["status"] == "completed" for row in operations)
        before = len(provider.calls)
        replayed = client.resume(result.run_id)
        assert replayed.ok, replayed.error
        assert replayed.value == result.value
        assert len(provider.calls) == before


def test_replan_to_outer_framing_restarts_evidence_and_drops_stale_logical_phases(
    tmp_path,
):
    count = Counter()
    produced = []

    def answer(request):
        phase = _input(request)["phase"]
        if request.artifacts:
            produced.append(phase)
        else:
            count[phase] += 1
        outcome = (
            "needs_replan"
            if not request.artifacts
            and phase == "assess_go_no_go"
            and count[phase] == 1
            else "accepted"
        )
        return _release_answer(request, outcome=outcome)

    with Botpipe(tmp_path, provider=FakeProvider([answer] * 20)) as client:
        result = client.run(ReleaseCandidateToGoNoGo, Params(release_name="release"))
        assert result.ok, result.error
        assert produced == [
            "frame_release",
            "assemble_evidence_pack",
            "assess_go_no_go",
            "frame_release",
            "assemble_evidence_pack",
            "assess_go_no_go",
            "prepare_decision_package",
        ]
        assert len(result.value.phases) == 4
        assert len({phase.name for phase in result.value.phases}) == 4


@pytest.mark.parametrize("defect", ["invalid_enum", "missing_required_field"])
def test_domain_producer_contract_repairs_invalid_payload_in_the_same_operation(
    tmp_path,
    defect,
):
    assessment_turns = 0

    def answer(request):
        nonlocal assessment_turns
        assessment = (
            bool(request.artifacts) and _input(request)["phase"] == "assess_go_no_go"
        )
        if assessment:
            assessment_turns += 1
        first_assessment = assessment and assessment_turns == 1
        result = _release_answer(
            request, invalid=first_assessment and defect == "invalid_enum"
        )
        if first_assessment and defect == "missing_required_field":
            del result["evidence_artifacts"]
        return result

    provider = FakeProvider([answer] * 12)
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(ReleaseCandidateToGoNoGo, Params(release_name="release"))
        assert result.ok, result.error
        assert result.value.phases[2].details["recommended_decision"] == "go"
        assert len([request for request in provider.calls if request.artifacts]) == 5
        assert assessment_turns == 2
        assert len(provider.calls) == 7
        operations = _provider_operations(client, result.run_id)
        assert sum(row["status"] == "failed" for row in operations) == 1


@pytest.mark.parametrize("pause_outcome", ["blocked", "question"])
def test_missing_prerequisite_pauses_then_resumes_same_phase_with_answer(
    tmp_path, pause_outcome
):
    frame_turns = 0
    producer_inputs = []

    def answer(request):
        nonlocal frame_turns
        payload = _input(request)
        if request.artifacts:
            producer_inputs.append(payload)
        if request.artifacts and payload["phase"] == "frame_release":
            frame_turns += 1
        outcome = (
            pause_outcome
            if request.artifacts
            and payload["phase"] == "frame_release"
            and frame_turns == 1
            else "accepted"
        )
        result = _release_answer(request, outcome=outcome)
        if outcome != "accepted":
            result["question"] = "Where is the production rollback evidence?"
        return result

    provider = FakeProvider([answer] * 12)
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(ReleaseCandidateToGoNoGo, Params(release_name="release"))
        assert paused.status == "awaiting_input", paused.error
        assert len(provider.calls) == 1
        assert (
            "Where is the production rollback evidence?"
            in paused.pending_input["question"]
        )
        result = client.resume(
            paused.run_id, answer="Production rollback evidence is in rollback.json."
        )
        assert result.ok, result.error
        assert len(provider.calls) == 7
        assert "rollback.json" in json.dumps(producer_inputs[1])
        assert len(result.value.phases) == 4


def test_security_child_passes_immutable_handles_with_external_state_directory(
    tmp_path,
):
    from pathlib import Path

    from test_labs import _successful_provider

    from labs.workflows.security_finding_to_verified_remediation import (
        Params as SecurityParams,
    )
    from labs.workflows.security_finding_to_verified_remediation import (
        SecurityFindingToVerifiedRemediation,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "external-state"
    child_reads = []

    def answer(request):
        payload = _input(request)
        if payload["phase"] == "assess_security_finding" and request.artifacts:
            child = payload["security_evidence_pack"]
            expected_paths = {
                Path(item["path"]) for item in child["artifacts"].values()
            }
            assert expected_paths
            assert all(path.is_relative_to(state) for path in expected_paths)
            assert expected_paths.issubset(set(request.reads))
            child_reads.extend(expected_paths)
        response = _successful_provider(request)
        if not request.artifacts:
            for key in (
                "ready_for_downstream_assessment",
                "verification_ready",
                "rollout_ready",
                "closure_ready",
                "communication_ready",
            ):
                if key in (request.output_schema or {}).get("properties", {}):
                    response[key] = True
        return response

    provider = FakeProvider([answer] * 12)
    with Botpipe(workspace, state_dir=state, provider=provider) as client:
        result = client.run(
            SecurityFindingToVerifiedRemediation,
            SecurityParams(
                finding_title="Authorization check", finding_source="internal_review"
            ),
        )
        assert result.ok, result.error
        assert len(child_reads) == 6
        assert result.value.artifacts
        assert all(
            handle.path.is_relative_to(state)
            for handle in result.value.artifacts.values()
        )
        replayed = client.resume(result.run_id)
        assert replayed.ok, replayed.error
        assert len(provider.calls) == 8
        assert replayed.value.artifacts == result.value.artifacts


@pytest.mark.parametrize("repeat", ["rework", "replan"])
def test_provider_budget_bounds_all_rework_and_replanning(tmp_path, repeat):
    def answer(request):
        phase = _input(request)["phase"]
        outcome = "accepted"
        if repeat == "rework" and phase == "frame_release":
            outcome = "needs_rework"
        if repeat == "replan" and phase == "assess_go_no_go" and not request.artifacts:
            outcome = "needs_replan"
        return _release_answer(request, outcome=outcome)

    provider = FakeProvider([answer] * 20)
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(
            ReleaseCandidateToGoNoGo,
            Params(release_name="bounded", max_provider_turns=7),
        )
        assert result.status == "budget_exceeded", result.error
        assert len(provider.calls) == 7
        replayed = client.resume(result.run_id)
        assert replayed.status == "budget_exceeded", replayed.error
        assert len(provider.calls) == 7


def test_producer_cannot_hide_uncaptured_citations_behind_a_reviewer(tmp_path):
    reviewed = []

    def answer(request):
        result = _release_answer(request)
        phase = _input(request)["phase"]
        if not request.artifacts:
            reviewed.append(phase)
        if phase == "assemble_evidence_pack" and request.artifacts:
            result["authoritative_artifacts"] = ["invented_verification"]
        return result

    result = Botpipe(tmp_path, provider=FakeProvider([answer] * 8)).run(
        ReleaseCandidateToGoNoGo, Params(release_name="citation-integrity")
    )
    assert result.status == "failed"
    assert "producer cited uncaptured artifacts: invented_verification" in result.error
    assert reviewed == []


def test_run_phase_preserves_explicit_no_output_repair(tmp_path):
    from pathlib import Path

    from botpipe import Provider, workflow
    from labs.workflows._shared import LabPhaseOutcome, artifact, run_phase

    @workflow
    def one_phase():
        return run_phase(
            phase="fixture",
            producer=Provider(output_retries=0),
            producer_prompt=str(
                Path(__file__).parent.parent
                / "labs/workflows/release_candidate_to_go_no_go/prompts/frame_producer.md"
            ),
            input={},
            writes=(artifact("fixture.md"),),
            returns=LabPhaseOutcome,
        ).value

    def invalid(request):
        for path in request.artifacts.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Evidence.")
        return {"outcome": "invalid"}

    provider = FakeProvider([invalid] * 4)
    result = Botpipe(tmp_path, provider=provider).run(one_phase)
    assert result.status == "failed"
    assert len(provider.calls) == 1


@pytest.mark.parametrize("outcome", ["blocked", "question"])
def test_missing_prerequisite_can_pause_without_fabricated_artifacts(tmp_path, outcome):
    def unavailable(_request):
        return {
            "outcome": outcome,
            "summary": "The release scope has not been supplied.",
            "question": "What release is under review?",
            "authoritative_artifacts": [],
        }

    provider = FakeProvider([unavailable, *([_release_answer] * 6)])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(ReleaseCandidateToGoNoGo, Params(release_name="unknown"))
        assert paused.status == "awaiting_input", paused.error
        assert len(provider.calls) == 1
        assert not client.inspect(paused.run_id)["artifacts"]
        result = client.resume(paused.run_id, answer="Release 2026.09.")
        assert result.ok, result.error
        assert set(result.value.artifact_names) == set(result.value.artifacts)
        assert all(handle.read_bytes() for handle in result.value.artifacts.values())


def test_accepted_phase_still_requires_all_declared_artifacts(tmp_path):
    def incomplete(_request):
        return {
            "outcome": "accepted",
            "summary": "Claiming completion without evidence.",
            "evidence_focus": ["tests"],
            "authoritative_artifacts": ["release_scope_brief"],
        }

    result = Botpipe(tmp_path, provider=FakeProvider([incomplete])).run(
        ReleaseCandidateToGoNoGo, Params(release_name="incomplete")
    )
    assert result.status == "failed"
    assert "did not capture required artifacts" in result.error


def test_replay_cannot_redirect_a_producer_workspace_to_authoritative_source(tmp_path):
    from botpipe.providers import ProviderError

    source = tmp_path / "authoritative.txt"
    source.write_text("Original source.")
    provider = FakeProvider([ProviderError("interrupted"), _release_answer])
    with Botpipe(tmp_path, provider=provider) as client:
        first = client.run(ReleaseCandidateToGoNoGo, Params(release_name="isolated"))
        assert first.status == "interrupted", first.error
        working = provider.calls[0].workspace
        assert not list(working.iterdir())
        working.rmdir()
        working.symlink_to(tmp_path, target_is_directory=True)
        resumed = client.resume(first.run_id)
        assert resumed.status == "failed", resumed.error
        # Replay may surface the unconsumed provider operation as ReplayMismatch;
        # the security contract is rejection before another write-capable turn.
        assert resumed.error
        assert len(provider.calls) == 1
        assert source.read_text() == "Original source."
