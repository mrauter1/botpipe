"""Clarifications and independent review participate in the same bounded loop."""

from __future__ import annotations

from pathlib import Path

from botpipe import Botpipe
from botpipe.providers import FakeProvider
from botpipe.workflows.workflow_author import Params, workflow_author
from tests.test_workflow_author import _answer, _brief, _input, _write_package


def test_initial_question_answer_reaches_author_and_independent_reviewer(tmp_path):
    seen = {"understand": [], "review": []}

    def answer(request):
        if "Write the brief" in request.prompt:
            context = _input(request)
            seen["understand"].append((request, context))
            if len(seen["understand"]) == 1:
                return _brief(questions=["What input should this workflow accept?"])
            return _brief()
        if request.preset == "query":
            seen["review"].append((request, _input(request)))
            return {"ship": True, "findings": []}
        return _answer(request)

    provider = FakeProvider([answer] * 5)
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(
            workflow_author, Params(package_name="clarified", max_rounds=2),
            request="Make a reusable echo workflow.",
        )
        assert paused.status == "awaiting_input"
        resumed = client.resume(paused.run_id, answer="Accept and echo text.")
        assert resumed.ok, resumed.error
        assert resumed.value.shipped and resumed.value.rounds == 1
        assert seen["understand"][0][0].session_key == seen["understand"][1][0].session_key
        assert seen["understand"][1][1]["request"] == "Make a reusable echo workflow."
        assert seen["understand"][1][1]["answers"][0]["answer"] == "Accept and echo text."
        review, context = seen["review"][0]
        assert context["request"] == "Make a reusable echo workflow."
        assert context["answers"][0]["answer"] == "Accept and echo text."
        assert review.session_key != seen["understand"][0][0].session_key
        assert Path(resumed.value.candidate_root).is_dir()


def test_reviewer_rejection_repairs_in_same_candidate_and_author_session(tmp_path):
    builds = []
    reviews = []

    def answer(request):
        if request.preset == "query":
            reviews.append(request)
            if len(reviews) == 1:
                return {"ship": False, "findings": ["A missing handoff changes the answer."]}
            return {"ship": True, "findings": []}
        if "Write the brief" in request.prompt:
            return _brief()
        builds.append(request)
        return {"reference": _write_package(request)}

    run = Botpipe(tmp_path, provider=FakeProvider([answer] * 6)).run(
        workflow_author, Params(package_name="reviewed", max_rounds=2), request="Echo text."
    )
    assert run.ok, run.error
    assert run.value.shipped and run.value.rounds == 2
    assert len(builds) == len(reviews) == 2
    assert builds[0].session_key == builds[1].session_key
    assert reviews[0].session_key == reviews[1].session_key != builds[0].session_key
    assert builds[0].workspace == builds[1].workspace == Path(run.value.candidate_root)
    assert _input(builds[1])["feedback"] == ["A missing handoff changes the answer."]
    assert _input(reviews[0])["request"] == "Echo text."
    assert _input(reviews[0])["builder_notes"] == ""


def test_revised_brief_question_consumes_round_and_answer_affects_next_build(tmp_path):
    builds = []
    understands = []

    def answer(request):
        if "Write the brief" in request.prompt:
            understands.append(_input(request))
            return _brief()
        if request.preset == "query":
            return {"ship": True, "findings": []}
        builds.append(request)
        if len(builds) == 1:
            return {"reference": _write_package(request),
                    "brief": _brief(questions=["Should the result keep the input text?"])}
        return {"reference": _write_package(request)}

    with Botpipe(tmp_path, provider=FakeProvider([answer] * 6)) as client:
        paused = client.run(workflow_author, Params(package_name="revised", max_rounds=2),
                            request="Echo a request.")
        assert paused.status == "awaiting_input"
        resumed = client.resume(paused.run_id, answer="Yes, exactly.")
        assert resumed.ok, resumed.error
        assert resumed.value.shipped and resumed.value.rounds == 2
        assert len(builds) == 2
        assert understands[-1]["answers"][0]["answer"] == "Yes, exactly."
        assert _input(builds[1])["answers"][0]["answer"] == "Yes, exactly."
        assert all(call.session_key == builds[0].session_key for call in builds)


def test_unresolved_questions_never_ship_and_exhaust_the_cycle_budget(tmp_path):
    understands = []

    def answer(request):
        assert "Write the brief" in request.prompt
        understands.append(request)
        return _brief(questions=["Which person's records may this process modify?"])

    with Botpipe(tmp_path, provider=FakeProvider([answer] * 4)) as client:
        paused = client.run(workflow_author, Params(package_name="unresolved", max_rounds=2))
        assert paused.status == "awaiting_input"
        paused = client.resume(paused.run_id, answer="I cannot specify yet.")
        assert paused.status == "awaiting_input"
        result = client.resume(paused.run_id, answer="Still unknown.")
        assert result.ok, result.error
        assert not result.value.shipped and result.value.rounds == 2
        assert result.value.findings == ["Which person's records may this process modify?"]
        assert result.value.reference is None and result.value.validation is None
        assert len(understands) == 3


def test_rejected_review_exhausts_with_exact_findings(tmp_path):
    builds = []

    def answer(request):
        if "Write the brief" in request.prompt:
            return _brief()
        if request.preset == "query":
            return {"ship": False, "findings": ["No evidence that the human answer changes execution."]}
        builds.append(request)
        return {"reference": _write_package(request)}

    run = Botpipe(tmp_path, provider=FakeProvider([answer] * 4)).run(
        workflow_author, Params(package_name="exhausted", max_rounds=1)
    )
    assert run.ok, run.error
    assert run.value.shipped is False and run.value.rounds == 1
    assert run.value.findings == ["No evidence that the human answer changes execution."]
    assert run.value.validation.success and len(builds) == 1


def test_inconsistent_review_is_corrected_before_shipping(tmp_path):
    reviews = []

    def answer(request):
        if request.preset == "query":
            reviews.append(request)
            if len(reviews) == 1:
                return {"ship": True, "findings": ["The test omits the human gate."]}
            return {"ship": False, "findings": ["The test omits the human gate."]}
        return _answer(request)

    run = Botpipe(tmp_path, provider=FakeProvider([answer] * 5)).run(
        workflow_author, Params(package_name="review_correction", max_rounds=1)
    )
    assert run.ok, run.error
    assert len(reviews) == 2
    assert not run.value.shipped
    assert run.value.findings == ["The test omits the human gate."]
