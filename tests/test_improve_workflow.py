from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from botpipe import Botpipe
from labs.workflows.improve_workflow import ImproveWorkflowParams, improve_workflow
from labs.workflows.improve_workflow.models import EvidenceLink, ScopeAssessment
from tests.improvement_support import (
    ACCEPT,
    REJECT,
    assess,
    evaluation_spec,
    failing_implementation,
    implement,
    no_candidate,
    observed_workflow,
    prompt_input,
    propose,
    validation_argv,
)
from tests.improvement_support import (
    FixtureProvider as FakeProvider,
)


def params(reference, **changes):
    return ImproveWorkflowParams(
        selected_workflow=reference,
        target_test_argv=validation_argv(),
        **changes,
    )


def test_improvement_executes_candidate_behavior_and_preserves_original(tmp_path):
    reference, source = observed_workflow(tmp_path)
    original = source.read_bytes()
    spec, calls = evaluation_spec(tmp_path)
    provider = FakeProvider([assess, propose, ACCEPT, implement, ACCEPT])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            improve_workflow, params(reference, evaluation_spec_path=str(spec))
        )
        assert run.ok, run.error
        assert run.value.outcome == "improved"
        assert run.value.candidate.validation.success
        assert run.value.candidate.evaluation["comparison"]["state"] == "improved"
        assert source.read_bytes() == original
        assert calls.read_text().splitlines() == ["call", "call"]
        replay = client.resume(run.run_id)
        assert replay.ok, replay.error
        assert replay.value == run.value
        assert len(provider.calls) == 5
        assert calls.read_text().splitlines() == ["call", "call"]


def test_checks_and_review_do_not_claim_unmeasured_improvement(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    with Botpipe(
        tmp_path, provider=FakeProvider([assess, propose, ACCEPT, implement, ACCEPT])
    ) as client:
        run = client.run(improve_workflow, params(reference))
    assert run.ok, run.error
    assert run.value.outcome == "candidate_ready"
    assert run.value.candidate.evaluation["comparison"]["state"] == "not_evaluated"


def test_investigation_links_observed_failure_and_assesses_workflow_and_step(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    provider = FakeProvider([assess, no_candidate, ACCEPT])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params(reference))
    assert run.ok, run.error
    assessment = run.value.recommendation.assessment
    assert {
        (item.scope, item.classification) for item in assessment.scope_assessments
    } == {("whole_workflow", "opportunity"), ("step", "failure")}
    observed = assessment.scope_assessments[1].evidence[0]
    assert observed.basis == "observation"
    assert observed.observation_ids[0] in {
        item.observation_id
        for item in run.value.recommendation.evidence_snapshot.observations
    }


def test_model_investigation_receives_neutral_metrics_without_ranked_target(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    seen = []

    def inspect_assessment(request):
        data = prompt_input(request)
        evidence = data["evidence"]
        assert data["baseline_surface_manifest"]["root"] == "."
        assert not Path(
            data["selected_workflow_source_manifest"]["source_path"]
        ).is_absolute()
        seen.append(evidence)
        return assess(request)

    def inspect_proposal(request):
        evidence = prompt_input(request)["evidence"]
        seen.append(evidence)
        return no_candidate(request)

    provider = FakeProvider([inspect_assessment, inspect_proposal, ACCEPT])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params(reference))
    assert run.ok, run.error
    assert len(seen) == 2
    assert all("descriptive_step_metrics" in evidence for evidence in seen)
    assert all(
        not {"shortlist", "selection_basis", "next_action"} & evidence.keys()
        for evidence in seen
    )


def test_source_only_candidate_needs_no_fabricated_observation_id(tmp_path):
    source = tmp_path / "subject.py"
    source.write_text(
        "from botpipe import workflow\n"
        "def behavior(value):\n"
        "    return value\n"
        "@workflow(name='subject')\n"
        "def subject():\n"
        "    return behavior(1)\n",
        encoding="utf-8",
    )
    original = source.read_bytes()

    def source_proposal(request):
        data = prompt_input(request)
        assert not data["evidence"]["observations"]
        source_path = data["assessment"]["intent_evidence"][0]["source_paths"][0]
        return {
            "candidate": {
                "title": "Make the source behavior explicit",
                "targets": ["subject.py"],
                "cited_observation_ids": [],
                "source_evidence_paths": [source_path],
                "proposed_change": "Return the input plus one.",
                "expected_effect": "The source-level behavior becomes an increment.",
                "risks": ["Callers may depend on identity behavior."],
                "validation_plan": {
                    "description": "Exercise the source behavior.",
                    "checks": ["Check positive and negative inputs."],
                    "falsification": "Any input does not increment by one.",
                },
            },
            "next_action": "implement_candidate",
            "reason": None,
        }

    provider = FakeProvider([assess, source_proposal, ACCEPT, implement, ACCEPT])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            improve_workflow,
            params(f"{source}:subject"),
        )
    assert run.ok, run.error
    assert run.value.outcome == "candidate_ready"
    assert (
        run.value.recommendation.candidate_set.candidates[0].cited_observation_ids == []
    )
    assert source.read_bytes() == original


def test_assessment_cannot_fabricate_observation_links(tmp_path):
    reference, _ = observed_workflow(tmp_path)

    def fabricated(request):
        value = assess(request)
        value["scope_assessments"][1]["evidence"][0]["observation_ids"] = [
            "observation_" + "f" * 64
        ]
        return value

    provider = FakeProvider([fabricated])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params(reference))
    assert not run.ok
    assert "assessment cites unknown observations" in run.error
    assert len(provider.calls) == 1


def test_frozen_analysis_source_tamper_blocks_recommendation(tmp_path):
    reference, source = observed_workflow(tmp_path)
    original = source.read_bytes()

    def tamper(request):
        frozen = Path(request.workspace) / "subject.py"
        assert frozen.read_bytes() == original
        value = assess(request)
        os.chmod(frozen, 0o644)
        frozen.write_text("# changed analysis snapshot\n", encoding="utf-8")
        return value

    provider = FakeProvider([tamper])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params(reference))
    assert not run.ok
    assert "frozen workflow analysis source changed" in run.error
    assert source.read_bytes() == original


def test_resume_rechecks_frozen_analysis_source_before_replaying_model_turns(
    tmp_path,
):
    reference, _ = observed_workflow(tmp_path)

    def interrupt(_request):
        raise KeyboardInterrupt("stop during candidate implementation")

    provider = FakeProvider([assess, propose, ACCEPT, interrupt])
    with Botpipe(tmp_path, provider=provider) as client:
        interrupted = client.run(improve_workflow, params(reference))
        assert interrupted.status == "interrupted", interrupted.error
        frozen = interrupted.folder / "analysis-source" / "baseline" / "subject.py"
        os.chmod(frozen, 0o644)
        frozen.write_text("# changed while suspended\n", encoding="utf-8")
        resumed = client.resume(interrupted.run_id)
    assert not resumed.ok
    assert "ReplayMismatch" in resumed.error
    assert len(provider.calls) == 4


@pytest.mark.parametrize(
    "payload",
    [
        {
            "basis": "observation",
            "statement": "mixed basis",
            "observation_ids": ["observation_" + "a" * 64],
            "source_paths": ["workflow.py"],
        },
        {
            "basis": "inference",
            "statement": "misstated direct evidence",
            "observation_ids": [],
            "source_paths": ["workflow.py"],
        },
    ],
)
def test_assessment_evidence_basis_is_exclusive(payload):
    with pytest.raises(ValidationError):
        EvidenceLink.model_validate(payload)


def test_affirmative_assessment_cannot_omit_evidence_basis():
    with pytest.raises(ValidationError, match="must identify their evidence"):
        ScopeAssessment(
            scope="whole_workflow",
            classification="opportunity",
            dimensions=["accuracy"],
            summary="An unsupported categorical diagnosis.",
            evidence=[],
        )


def test_no_observations_still_gets_qualitative_source_diagnosis(tmp_path):
    provider = FakeProvider([assess, no_candidate, ACCEPT])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params("ralph_loop"))
    assert run.ok, run.error
    assert run.value.outcome == "collect_evidence"
    assert run.value.candidate is None
    assessment = run.value.recommendation.assessment
    assert assessment.workflow_intent
    assert {item.scope for item in assessment.scope_assessments} == {
        "whole_workflow",
        "step",
    }
    assert assessment.scope_assessments[1].classification == "not_assessed"
    assert assessment.rubric[0].falsification
    assert run.value.provider_budget["used_turns"] == 3
    assert len(provider.calls) == 3


def test_rejected_proposal_never_edits_a_candidate(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    provider = FakeProvider([assess, propose, REJECT])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params(reference, max_revisions=0))
    assert run.ok, run.error
    assert run.value.outcome == "rejected"
    assert run.value.candidate is None
    assert run.value.recommendation.receipt is None
    assert len(provider.calls) == 3


def test_failed_executable_checks_feed_a_bounded_revision(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    feedback = []

    def fix(request):
        feedback.append(prompt_input(request)["feedback"])
        return implement(request)

    provider = FakeProvider(
        [assess, propose, ACCEPT, failing_implementation, fix, ACCEPT]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params(reference, max_revisions=1))
    assert run.ok, run.error
    assert run.value.outcome == "candidate_ready"
    assert feedback[0]["validation"]["success"] is False
    assert len(provider.calls) == 6


def test_failed_checks_exhaust_revision_limit_without_model_review(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    spec, calls = evaluation_spec(tmp_path)
    provider = FakeProvider([assess, propose, ACCEPT, failing_implementation])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            improve_workflow,
            params(reference, max_revisions=0, evaluation_spec_path=str(spec)),
        )
    assert run.ok, run.error
    assert run.value.outcome == "rejected"
    assert not run.value.candidate.validation.success
    assert run.value.candidate.review is None
    assert len(provider.calls) == 4
    assert not calls.exists()


def test_unchanged_source_does_not_launch_evaluators(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    spec, calls = evaluation_spec(tmp_path)
    provider = FakeProvider([assess, propose, ACCEPT, "No changes made."])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            improve_workflow, params(reference, evaluation_spec_path=str(spec))
        )
    assert run.ok, run.error
    assert run.value.outcome == "no_change"
    assert run.value.candidate.changed_paths == []
    assert not calls.exists()


def test_independent_review_can_reject_a_candidate_that_passes_checks(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    provider = FakeProvider([assess, propose, ACCEPT, implement, REJECT])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params(reference, max_revisions=0))
    assert run.ok, run.error
    assert run.value.outcome == "rejected"
    assert run.value.candidate.validation.success
    assert not run.value.candidate.review.accepted


@pytest.mark.parametrize("evaluate", [False, True])
def test_candidate_drift_during_review_cannot_claim_success(tmp_path, evaluate):
    reference, _ = observed_workflow(tmp_path)
    spec, calls = evaluation_spec(tmp_path)

    def review_with_concurrent_edit(request):
        source = Path(request.workspace) / "subject.py"
        source.write_text(
            source.read_text().replace("return value + 1", "return value + 99"),
            encoding="utf-8",
        )
        return ACCEPT

    provider = FakeProvider(
        [assess, propose, ACCEPT, implement, review_with_concurrent_edit]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            improve_workflow,
            params(reference, evaluation_spec_path=str(spec) if evaluate else None),
        )
    assert not run.ok
    assert "candidate surface is stale" in run.error
    if evaluate:
        assert calls.read_text().splitlines() == ["call", "call"]
    else:
        assert not calls.exists()


def test_shared_budget_stops_before_implementation(tmp_path):
    reference, source = observed_workflow(tmp_path)
    original = source.read_bytes()
    provider = FakeProvider([assess, propose, ACCEPT])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params(reference, max_provider_turns=2))
    assert not run.ok
    assert "budget" in run.error.lower()
    assert source.read_bytes() == original
    assert len(provider.calls) == 2


def test_malformed_evaluator_results_are_inconclusive(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    spec, calls = evaluation_spec(tmp_path, invalid=True)
    with Botpipe(
        tmp_path,
        provider=FakeProvider([assess, propose, ACCEPT, implement, ACCEPT]),
    ) as client:
        run = client.run(
            improve_workflow, params(reference, evaluation_spec_path=str(spec))
        )
    assert run.ok, run.error
    assert run.value.outcome == "inconclusive"
    assert calls.read_text().splitlines() == ["call", "call"]


def test_completed_model_turns_replay_after_interruption(tmp_path):
    reference, _ = observed_workflow(tmp_path)

    def interrupt(request):
        raise KeyboardInterrupt("crash after proposal review")

    with Botpipe(
        tmp_path, provider=FakeProvider([assess, propose, ACCEPT, interrupt])
    ) as client:
        interrupted = client.run(improve_workflow, params(reference))
        assert interrupted.status == "interrupted", interrupted.error
    provider = FakeProvider([implement, ACCEPT])
    with Botpipe(tmp_path, provider=provider) as client:
        # A new fake backend has no native turn history. Resolve that uncertainty
        # explicitly; the three committed investigation/proposal/review
        # turns must still replay.
        operation = next(
            item
            for item in client.inspect(interrupted.run_id)["operations"]
            if item["kind"] == "provider" and item["status"] != "completed"
        )
        client.resolve(interrupted.run_id, operation["id"], retry=True)
        resumed = client.resume(interrupted.run_id)
    assert resumed.ok, resumed.error
    assert resumed.value.outcome == "candidate_ready"
    assert len(provider.calls) == 2
