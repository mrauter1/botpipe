"""Acceptance tests use actual provider-calling workflows in trial subprocesses."""

from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from botpipe import Botpipe, activity, current_run, workflow
from botpipe.providers import ProviderResponse
from botpipe_optimizer.trial_models import TrialCase, TrialSettings
from labs.workflows.improve_workflow import (
    ImproveWorkflowParams,
    evaluation,
    improve_workflow,
)
from labs.workflows.improve_workflow.models import DiagnosticAssessment
from tests.improvement_support import ACCEPT, FixtureProvider, assess, prompt_input


class ReportProvider:
    name = "report-fixture"
    supports_timeout = True

    def run(self, request):
        if "Review the draft" in request.prompt:
            text = (
                "approved"
                if "[source two]" in request.prompt
                else "cite at least two sources"
            )
        elif "Write the report" in request.prompt:
            text = (
                "Supported answer. [source one] [source two]"
                if "two sources" in request.prompt
                else "Unsupported answer."
            )
        else:
            text = "The correct answer."
        return ProviderResponse(
            text, usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}
        )


def report_provider(config):
    return ReportProvider()


def _source(root, purpose):
    source = root / "subject.py"
    common = "from botpipe import workflow, Provider\n@workflow(name='subject')\ndef subject(topic: str):\n"
    if purpose == "quality":
        body = (
            "    draft = Provider().generate('Write the report', input=topic).value\n"
            "    review = Provider().generate('Review the draft', input=draft).value\n"
            "    return {'draft': draft, 'review': review}\n"
        )
    else:
        body = (
            "    for _ in range(3):\n"
            "        result = Provider().generate('Answer accurately', input=topic).value\n"
            "    return result\n"
        )
    source.write_text(common + body)
    return source


def _assessment(purpose):
    def answer(request):
        value = assess(request)
        value["workflow_intent"] = (
            "Write a supported report."
            if purpose == "quality"
            else "Answer correctly with economical provider usage."
        )
        value["rubric"] = [
            {
                "name": "Cited support" if purpose == "quality" else "Correct answer",
                "applies_to": "returned result",
                "description": "Draft cites two sources and review approves."
                if purpose == "quality"
                else "Return The correct answer.",
                "evidence_needed": ["actual trial result"],
                "falsification": "Required result is absent.",
                "must_preserve": True,
            }
        ]
        value["comparison_rule"] = (
            "Prefer the approved report with two sources."
            if purpose == "quality"
            else "Preserve the correct answer and prefer lower total token usage."
        )
        value["trial_cases"] = [
            {
                "case_id": "representative",
                "description": "A representative writing request",
                "args": ["Summarize the topic."],
            }
        ]
        return value

    return answer


def _proposal(request):
    path = prompt_input(request)["assessment"]["intent_evidence"][0]["source_paths"][0]
    return {
        "candidate": {
            "title": "Improve the observed behavior",
            "targets": ["subject.py"],
            "source_evidence_paths": [path],
            "proposed_change": "Meet the frozen objective.",
            "expected_effect": "Better result on representative inputs.",
            "risks": ["Other inputs remain unassessed."],
            "validation_plan": {
                "description": "Run the workflow.",
                "checks": ["Execute frozen cases."],
                "falsification": "The candidate loses or violates an obligation.",
            },
        },
        "next_action": "implement_candidate",
        "reason": None,
    }


def _implementation(purpose):
    def answer(request):
        source = request.workspace / "subject.py"
        text = source.read_text()
        text = (
            text.replace("Write the report", "Write the report with two sources")
            if purpose == "quality"
            else text.replace("range(3)", "range(1)")
        )
        source.write_text(text)
        return "Implemented the requested change."

    return answer


def _judge(purpose, packets):
    def answer(request):
        assert request.preset == "generate"
        assert request.tools == ()
        assert request.session_id is None
        raw = request.prompt.split("BEGIN ANONYMOUS PACKET\n", 1)[1].split(
            "\nEND ANONYMOUS PACKET", 1
        )[0]
        packet = json.loads(raw)
        packets.append(packet)
        if purpose == "quality":
            passed = {
                label: packet[label]["value"]["review"] == "approved"
                for label in ("A", "B")
            }
            preferred = next(label for label, okay in passed.items() if okay)
            quote = "[source two]"
        else:
            passed = {
                label: packet[label]["value"] == "The correct answer."
                for label in ("A", "B")
            }
            preferred = min(
                ("A", "B"), key=lambda label: packet[label]["usage"]["total_tokens"]
            )
            quote = "The correct answer."
        return {
            "preference": preferred,
            "criteria": [
                {
                    "criterion": packet["rubric"][0]["name"],
                    "a": "met" if passed["A"] else "not_met",
                    "b": "met" if passed["B"] else "not_met",
                    "explanation": "The recorded outputs support this assessment.",
                }
            ],
            "explanation": "The preferred output meets the frozen comparison rule.",
            "evidence_quotes": [quote],
        }

    return answer


@pytest.mark.parametrize("purpose", ["quality", "efficiency"])
def test_real_trials_apply_task_specific_rubric_without_evaluator_script(
    tmp_path, monkeypatch, purpose
):
    source = _source(tmp_path, purpose)
    original = source.read_bytes()
    packets = []
    provider = FixtureProvider(
        [
            _assessment(purpose),
            _proposal,
            ACCEPT,
            _implementation(purpose),
            ACCEPT,
            _judge(purpose, packets),
        ]
    )
    monkeypatch.setattr(
        evaluation, "_TRIAL_PROVIDER_FACTORY", f"{__file__}:report_provider"
    )
    params = ImproveWorkflowParams(
        selected_workflow=f"{source}:subject",
        execute_trials=True,
        target_test_argv=[
            sys.executable,
            "-c",
            "import runpy; runpy.run_path('subject.py')",
        ],
        trial_settings=TrialSettings(timeout_seconds=10, max_elapsed_seconds=60),
    )
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params)
        assert run.ok, run.error
        assert run.value.outcome == "improved", run.value.candidate.evaluation
        replay = client.resume(run.run_id, workflow=improve_workflow)
        assert replay.ok, replay.error
        assert replay.value == run.value
    assert len(provider.calls) == 6
    assert source.read_bytes() == original
    assert not (run.folder / "optimization_publication_receipt.json").exists()
    pair = run.value.candidate.evaluation["trials"][0]["results"]
    assert all(item["execution"] == "complete" for item in pair.values())
    assert pair["baseline"]["run_id"] != pair["candidate"]["run_id"]
    assert len(packets) == 1
    assert "Write the report" not in json.dumps(packets[0])
    if purpose == "efficiency":
        assert pair["baseline"]["usage"]["total_tokens"] == 15
        assert pair["candidate"]["usage"]["total_tokens"] == 5


@activity(retry_safe=True)
def _capture_hashes(captured: str):
    root = Path(captured)
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


@workflow
def _freeze_cases(params: ImproveWorkflowParams, assessment: dict, captured: str):
    root = Path(captured)
    hashes = _capture_hashes(captured)
    plan = evaluation.freeze_trial_plan(
        params=params,
        assessment=DiagnosticAssessment.model_validate(assessment),
        analysis_root=root,
        analysis_hashes=hashes,
        source_manifest={"surface_id": "test-surface"},
    )
    if not (current_run().workspace / "finish").exists():
        raise KeyboardInterrupt("pause after freezing")
    return plan


def _minimal_assessment():
    return {
        "workflow_intent": "Read inputs.",
        "intent_evidence": [{"basis": "inference", "statement": "Test fixture."}],
        "scope_assessments": [
            {
                "scope": "whole_workflow",
                "classification": "uncertain",
                "summary": "Requires trials.",
                "uncertainty": "No history.",
            }
        ],
        "rubric": [
            {
                "name": "Behavior",
                "applies_to": "output",
                "description": "Read the supplied inputs.",
                "evidence_needed": ["result"],
                "falsification": "Input differs.",
            }
        ],
    }


@pytest.mark.parametrize("tamper", [False, True])
def test_case_input_bytes_are_frozen_before_edits_and_rechecked_on_resume(
    tmp_path, tamper
):
    source = _source(tmp_path, "quality")
    captured = tmp_path / "captured"
    captured.mkdir()
    (captured / "input.txt").write_text("original captured bytes")
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "repository.txt").write_text("original workspace")
    params = ImproveWorkflowParams(
        selected_workflow=f"{source}:subject",
        execute_trials=True,
        trial_fixture_path=str(fixture),
        trial_cases=[
            TrialCase(
                case_id="fixture",
                description="Use frozen inputs",
                args=["topic"],
                workspace="fixture",
                assets={"input.txt": "input.txt"},
            )
        ],
    )
    with Botpipe(tmp_path, provider=FixtureProvider([])) as client:
        paused = client.run(_freeze_cases, params, _minimal_assessment(), str(captured))
        assert paused.status == "interrupted", paused.error
        frozen = paused.folder / "rubric-trial-plan/inputs/fixture/input.txt"
        (captured / "input.txt").write_text("changed capture")
        (fixture / "repository.txt").write_text("changed workspace")
        if tamper:
            frozen.chmod(0o644)
            frozen.write_text("tampered bytes")
        (tmp_path / "finish").touch()
        resumed = client.resume(paused.run_id, workflow=_freeze_cases)
    if tamper:
        assert not resumed.ok
        assert "frozen trial input bytes changed" in resumed.error
    else:
        assert resumed.ok, resumed.error
        assert frozen.read_text() == "original captured bytes"
        assert (frozen.parent / "repository.txt").read_text() == "original workspace"


def test_missing_fixture_is_unavailable_instead_of_invented_historical_state(tmp_path):
    source = _source(tmp_path, "quality")
    captured = tmp_path / "captured"
    captured.mkdir()
    (tmp_path / "finish").touch()
    params = ImproveWorkflowParams(
        selected_workflow=f"{source}:subject",
        execute_trials=True,
        trial_cases=[
            TrialCase(
                case_id="repository",
                description="Needs repository",
                args=["topic"],
                workspace="fixture",
            )
        ],
    )
    with Botpipe(tmp_path, provider=FixtureProvider([])) as client:
        run = client.run(_freeze_cases, params, _minimal_assessment(), str(captured))
    assert run.ok, run.error
    assert run.value["cases"][0]["available"] is False
    assert "initial workspace" in run.value["cases"][0]["reason"]


def test_requested_trials_with_no_executable_cases_are_inconclusive(tmp_path):
    source = _source(tmp_path, "quality")
    provider = FixtureProvider(
        [_assessment("quality"), _proposal, ACCEPT, _implementation("quality"), ACCEPT]
    )
    params = ImproveWorkflowParams(
        selected_workflow=f"{source}:subject",
        execute_trials=True,
        trial_cases=[
            TrialCase(
                case_id="repository",
                description="Requires an explicit initial workspace",
                args=["topic"],
                workspace="fixture",
            )
        ],
        target_test_argv=[
            sys.executable,
            "-c",
            "import runpy; runpy.run_path('subject.py')",
        ],
    )
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(improve_workflow, params)
    assert run.ok, run.error
    assert run.value.outcome == "inconclusive"
    measured = run.value.candidate.evaluation
    assert measured["evaluation"] == "rubric_trials"
    assert measured["comparison"]["state"] == "inconclusive"
    assert "initial workspace" in measured["comparison"]["reason"]
    assert measured["trials"] == []
    assert len(provider.calls) == 5  # No trial or judge is dispatched.


@workflow
def _paused_pair_admission():
    run = current_run()
    deadline = evaluation._trial_deadline(10)
    assert evaluation._admit_pair(deadline, 6)
    if not (run.workspace / "finish").exists():
        initialized = run.folder / "unstarted-trial"
        initialized.mkdir()
        (initialized / "execution-state.json").write_text(
            '{"started_at": 100, "deadline": 103}'
        )
        raise KeyboardInterrupt("paused after pair admission")
    return evaluation._execute_trial(
        code_root=str(run.workspace),
        reference="subject.py:subject",
        case=TrialCase(case_id="case", description="An admitted case").model_dump(
            mode="json"
        ),
        fixture_root=str(run.workspace),
        output_root=str(run.folder / "unstarted-trial"),
        settings=TrialSettings(timeout_seconds=3).model_dump(mode="json"),
        provider_config={},
        policy={},
        provider_factory=None,
        phase_deadline=deadline,
    )


def test_resume_does_not_launch_an_unstarted_arm_after_global_deadline(
    tmp_path, monkeypatch
):
    from botpipe_optimizer import trials

    now = [100.0]
    monkeypatch.setattr(evaluation, "time", SimpleNamespace(time=lambda: now[0]))

    def forbidden(**kwargs):
        raise AssertionError("An expired admission must not dispatch a new trial")

    monkeypatch.setattr(trials, "run_trial", forbidden)
    with Botpipe(tmp_path, provider=FixtureProvider([])) as client:
        paused = client.run(_paused_pair_admission)
        assert paused.status == "interrupted", paused.error
        now[0] = 111
        (tmp_path / "finish").touch()
        resumed = client.resume(paused.run_id, workflow=_paused_pair_admission)
    assert resumed.ok, resumed.error
    assert resumed.value.execution == "infrastructure_error"
    assert resumed.value.outcome == "phase_budget_exhausted"


def test_interrupted_input_capture_discards_partial_generation_before_resume(
    tmp_path, monkeypatch
):
    source = _source(tmp_path, "quality")
    captured = tmp_path / "captured"
    captured.mkdir()
    (captured / "input.txt").write_text("the captured input")
    (tmp_path / "finish").touch()
    params = ImproveWorkflowParams(
        selected_workflow=f"{source}:subject",
        execute_trials=True,
        trial_cases=[
            TrialCase(
                case_id="case",
                description="Use captured bytes",
                args=["topic"],
                assets={"input.txt": "input.txt"},
            )
        ],
    )
    original_inventory = evaluation._inventory
    interrupted = []

    def interrupt_after_copy(root, *args, **kwargs):
        files = original_inventory(root, *args, **kwargs)
        if root.name == "case" and "input.txt" in files and not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt("lost after copying the last input")
        return files

    monkeypatch.setattr(evaluation, "_inventory", interrupt_after_copy)
    with Botpipe(tmp_path, provider=FixtureProvider([])) as client:
        paused = client.run(_freeze_cases, params, _minimal_assessment(), str(captured))
        assert paused.status == "interrupted", paused.error
        assert not (paused.folder / "rubric-trial-plan").exists()
        resumed = client.resume(paused.run_id, workflow=_freeze_cases)
    assert resumed.ok, resumed.error
    assert (
        Path(resumed.value["root"]) / "inputs/case/input.txt"
    ).read_text() == "the captured input"
