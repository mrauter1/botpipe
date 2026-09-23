from __future__ import annotations

from pathlib import Path

import pytest

from botpipe import Botpipe
from labs.workflows.improve_workflow import ImproveWorkflowParams, improve_workflow
from tests.improvement_support import (
    ACCEPT,
    REJECT,
    evaluation_spec,
    failing_implementation,
    implement,
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
    provider = FakeProvider([propose, ACCEPT, implement, ACCEPT])
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
        assert len(provider.calls) == 4
        assert calls.read_text().splitlines() == ["call", "call"]


def test_checks_and_review_do_not_claim_unmeasured_improvement(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    with Botpipe(
        tmp_path, provider=FakeProvider([propose, ACCEPT, implement, ACCEPT])
    ) as client:
        run = client.run(improve_workflow, params(reference))
    assert run.ok, run.error
    assert run.value.outcome == "candidate_ready"
    assert run.value.candidate.evaluation["comparison"]["state"] == "not_evaluated"


def test_no_observations_returns_collect_evidence_without_dispatch(tmp_path):
    provider = FakeProvider([])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params("ralph_loop"))
    assert run.ok, run.error
    assert run.value.outcome == "collect_evidence"
    assert run.value.candidate is None
    assert run.value.provider_budget["used_turns"] == 0
    assert not provider.calls


def test_rejected_proposal_never_edits_a_candidate(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    provider = FakeProvider([propose, REJECT])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params(reference, max_revisions=0))
    assert run.ok, run.error
    assert run.value.outcome == "rejected"
    assert run.value.candidate is None
    assert run.value.recommendation.receipt is None
    assert len(provider.calls) == 2


def test_failed_executable_checks_feed_a_bounded_revision(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    feedback = []

    def fix(request):
        feedback.append(prompt_input(request)["feedback"])
        return implement(request)

    provider = FakeProvider([propose, ACCEPT, failing_implementation, fix, ACCEPT])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params(reference, max_revisions=1))
    assert run.ok, run.error
    assert run.value.outcome == "candidate_ready"
    assert feedback[0]["validation"]["success"] is False
    assert len(provider.calls) == 5


def test_failed_checks_exhaust_revision_limit_without_model_review(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    spec, calls = evaluation_spec(tmp_path)
    provider = FakeProvider([propose, ACCEPT, failing_implementation])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            improve_workflow,
            params(reference, max_revisions=0, evaluation_spec_path=str(spec)),
        )
    assert run.ok, run.error
    assert run.value.outcome == "rejected"
    assert not run.value.candidate.validation.success
    assert run.value.candidate.review is None
    assert len(provider.calls) == 3
    assert not calls.exists()


def test_unchanged_source_does_not_launch_evaluators(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    spec, calls = evaluation_spec(tmp_path)
    provider = FakeProvider([propose, ACCEPT, "No changes made."])
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
    provider = FakeProvider([propose, ACCEPT, implement, REJECT])
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

    provider = FakeProvider([propose, ACCEPT, implement, review_with_concurrent_edit])
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
    provider = FakeProvider([propose, ACCEPT])
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
        tmp_path, provider=FakeProvider([propose, ACCEPT, implement, ACCEPT])
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
        tmp_path, provider=FakeProvider([propose, ACCEPT, interrupt])
    ) as client:
        interrupted = client.run(improve_workflow, params(reference))
        assert interrupted.status == "interrupted", interrupted.error
    provider = FakeProvider([implement, ACCEPT])
    with Botpipe(tmp_path, provider=provider) as client:
        # A new fake backend has no native turn history. Resolve that uncertainty
        # explicitly; the two committed proposal turns must still replay.
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
