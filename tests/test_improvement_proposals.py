from __future__ import annotations

from types import SimpleNamespace

from botpipe import Botpipe
from labs.workflows.improve_workflow import ImproveWorkflowParams, improve_workflow
from labs.workflows.improve_workflow.models import DiagnosticAssessment
from labs.workflows.improve_workflow.proposals import (
    Proposal,
    _validate_proposal_grounding,
)
from tests.improvement_support import (
    ACCEPT,
    REJECT,
    FixtureProvider,
    assess,
    observed_workflow,
    prompt_input,
    propose,
    validation_argv,
)


def _params(reference: str, **changes) -> ImproveWorkflowParams:
    return ImproveWorkflowParams(
        selected_workflow=reference,
        target_test_argv=validation_argv(),
        **changes,
    )


def test_unassessed_source_citation_gets_bounded_proposal_repair(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    frozen_assessment = None

    def observation_only_assessment(request):
        nonlocal frozen_assessment
        value = assess(request)
        observation_id = prompt_input(request)["evidence"]["observations"][0][
            "observation_id"
        ]
        observation = {
            "basis": "observation",
            "statement": "The recorded operation failed.",
            "observation_ids": [observation_id],
            "source_paths": [],
        }
        value["intent_evidence"] = [observation]
        value["scope_assessments"][0]["evidence"] = [observation]
        return value

    def unassessed_source(request):
        nonlocal frozen_assessment
        frozen_assessment = prompt_input(request)["assessment"]
        value = propose(request)
        value["candidate"]["source_evidence_paths"] = ["subject.py"]
        return value

    feedback = []

    def repaired(request):
        data = prompt_input(request)
        feedback.append(data["review_feedback"])
        assert data["assessment"] == frozen_assessment
        return propose(request)

    provider = FixtureProvider(
        [
            observation_only_assessment,
            unassessed_source,
            repaired,
            ACCEPT,
            "No changes made.",
        ]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, _params(reference))

    assert run.ok, run.error
    assert "not established by the frozen assessment" in feedback[0]["grounding_error"]
    assert len(provider.calls) == 5


def test_source_backing_does_not_restrict_cross_file_edit_targets():
    assessment = DiagnosticAssessment.model_validate(
        {
            "workflow_intent": "Keep the workflow behavior correct.",
            "intent_evidence": [
                {
                    "basis": "source",
                    "statement": "The entry point establishes the intended behavior.",
                    "source_paths": ["entry.py"],
                }
            ],
            "scope_assessments": [
                {
                    "scope": "whole_workflow",
                    "classification": "opportunity",
                    "dimensions": ["accuracy"],
                    "summary": "A helper edit can implement the assessed behavior.",
                    "evidence": [
                        {
                            "basis": "source",
                            "statement": "The entry point establishes the behavior.",
                            "source_paths": ["entry.py"],
                        }
                    ],
                }
            ],
            "rubric": [
                {
                    "name": "Correct behavior",
                    "applies_to": "workflow",
                    "description": "The behavior remains correct.",
                    "evidence_needed": ["checks"],
                    "falsification": "A check fails.",
                }
            ],
        }
    )
    proposal = Proposal.model_validate(
        {
            "candidate": {
                "title": "Update the helper",
                "targets": ["helper.py"],
                "source_evidence_paths": ["entry.py"],
                "proposed_change": "Implement the assessed behavior in the helper.",
                "expected_effect": "The entry point returns the intended result.",
                "risks": ["Other helper callers may be affected."],
                "validation_plan": {
                    "description": "Run behavior checks.",
                    "checks": ["Exercise the entry point."],
                    "falsification": "The entry point returns a wrong result.",
                },
            },
            "next_action": "implement_candidate",
        }
    )

    _validate_proposal_grounding(
        proposal,
        assessment=assessment,
        snapshot=SimpleNamespace(citable_observation_ids=lambda: set()),
        baseline_manifest={
            "files": [
                {"relative_path": "entry.py"},
                {"relative_path": "helper.py"},
            ]
        },
    )


def test_exact_duplicates_are_stably_deduplicated_without_repair(tmp_path):
    reference, _ = observed_workflow(tmp_path)

    def duplicated_proposal(request):
        value = propose(request)
        candidate = value["candidate"]
        candidate["targets"] = ["subject.py", "subject.py"]
        candidate["cited_observation_ids"] *= 2
        candidate["risks"] *= 2
        candidate["validation_plan"]["checks"] *= 2
        return value

    def duplicated_review(request):
        candidate = prompt_input(request)["candidate_set"]["candidates"][0]
        assert candidate["targets"] == ["subject.py"]
        assert len(candidate["cited_observation_ids"]) == 1
        assert len(candidate["risks"]) == 1
        assert len(candidate["validation_plan"]["checks"]) == 1
        value = dict(REJECT)
        value["required_changes"] *= 2
        return value

    provider = FixtureProvider([assess, duplicated_proposal, duplicated_review])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, _params(reference, max_revisions=0))

    assert run.ok, run.error
    assert run.value.outcome == "rejected"
    assert len(run.value.recommendation.review.findings) == 1
    assert len(provider.calls) == 3


def test_blank_proposal_field_exhausts_only_grounding_repairs(tmp_path):
    reference, _ = observed_workflow(tmp_path)

    def blank_title(request):
        value = propose(request)
        value["candidate"]["title"] = "   "
        return value

    provider = FixtureProvider([assess, blank_title, blank_title])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            improve_workflow,
            _params(reference, max_grounding_repairs=1),
        )

    assert not run.ok
    assert "proposal output remained malformed after 1 repair" in run.error
    assert len(provider.calls) == 3


def test_blank_review_change_exhausts_only_grounding_repairs(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    blank_review = {
        "accepted": False,
        "summary": "A correction is required.",
        "required_changes": ["   "],
    }
    provider = FixtureProvider([assess, propose, blank_review, blank_review])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            improve_workflow,
            _params(reference, max_grounding_repairs=1),
        )

    assert not run.ok
    assert "proposal review output remained malformed after 1 repair" in run.error
    assert len(provider.calls) == 4


def test_oversized_candidate_receives_bounded_grounding_feedback(tmp_path):
    reference, _ = observed_workflow(tmp_path)

    def oversized(request):
        value = propose(request)
        value["candidate"]["title"] = "x" * 4096
        return value

    feedback = []

    def repaired(request):
        feedback.append(prompt_input(request)["review_feedback"])
        return propose(request)

    provider = FixtureProvider(
        [assess, oversized, repaired, ACCEPT, "No changes made."]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            improve_workflow,
            _params(reference, max_output_bytes=2048),
        )

    assert run.ok, run.error
    assert "CandidateSet exceeds max_output_bytes" in feedback[0]["grounding_error"]
    assert len(provider.calls) == 5


def test_oversized_review_receives_bounded_grounding_feedback(tmp_path):
    reference, _ = observed_workflow(tmp_path)
    oversized = {
        "accepted": False,
        "summary": "The candidate needs a correction.",
        "required_changes": ["x" * 4096],
    }
    feedback = []

    def repaired(request):
        feedback.append(prompt_input(request)["grounding_feedback"])
        return ACCEPT

    provider = FixtureProvider(
        [assess, propose, oversized, repaired, "No changes made."]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            improve_workflow,
            _params(reference, max_output_bytes=2048),
        )

    assert run.ok, run.error
    assert "candidate review exceeds max_output_bytes" in feedback[0]
    assert len(provider.calls) == 5


def test_candidate_path_escape_is_terminal_without_repair(tmp_path):
    reference, _ = observed_workflow(tmp_path)

    def escaping_proposal(request):
        value = propose(request)
        value["candidate"]["targets"] = ["../subject.py"]
        return value

    provider = FixtureProvider([assess, escaping_proposal, propose])
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, _params(reference))

    assert not run.ok
    assert "escapes the captured workflow boundary" in run.error
    assert len(provider.calls) == 2


def test_reviewer_receives_validated_source_evidence_paths(tmp_path):
    source = tmp_path / "subject.py"
    source.write_text(
        "from botpipe import workflow\n"
        "@workflow(name='subject')\n"
        "def subject():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    reference = f"{source}:subject"

    def source_proposal(request):
        source_path = prompt_input(request)["assessment"]["intent_evidence"][0][
            "source_paths"
        ][0]
        return {
            "candidate": {
                "title": "Clarify the result",
                "targets": [source_path],
                "source_evidence_paths": [source_path],
                "proposed_change": "Return the intended result explicitly.",
                "expected_effect": "The source behavior is clearer.",
                "risks": ["Callers may depend on the current result."],
                "validation_plan": {
                    "description": "Check the returned value.",
                    "checks": ["Call the workflow."],
                    "falsification": "The workflow returns the wrong value.",
                },
            },
            "next_action": "implement_candidate",
            "reason": None,
        }

    def inspect_review(request):
        data = prompt_input(request)
        candidate_id = data["candidate_set"]["candidates"][0]["candidate_id"]
        expected = data["assessment"]["intent_evidence"][0]["source_paths"]
        assert data["candidate_source_evidence_paths"] == {candidate_id: expected}
        return ACCEPT

    provider = FixtureProvider(
        [assess, source_proposal, inspect_review, "No changes made."]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, _params(reference))

    assert run.ok, run.error
    assert len(provider.calls) == 4
