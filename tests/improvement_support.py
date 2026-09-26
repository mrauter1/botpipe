"""Small executable workflow/evaluator fixtures for improvement behavior tests."""

from __future__ import annotations

import json
import sys
from hashlib import sha256

from botpipe import Botpipe
from botpipe.providers import FakeProvider


class FixtureProvider(FakeProvider):
    """Immediate, in-process scripted turns with no asynchronous worker effects."""

    supports_timeout = True


def prompt_input(request):
    return json.JSONDecoder().raw_decode(request.prompt.split("\n\nInput:\n", 1)[1])[0]


def observed_workflow(root):
    source = root / "subject.py"
    source.write_text(
        "from botpipe import activity, workflow\n"
        "def behavior(value):\n"
        "    return value\n"
        "@activity\n"
        "def check():\n"
        "    if behavior(1) != 2:\n"
        "        raise ValueError('the increment operation returned the original input')\n"
        "    return 'ok'\n"
        "@workflow(name='subject')\n"
        "def subject():\n"
        "    return check()\n",
        encoding="utf-8",
    )
    reference = f"{source}:subject"
    with Botpipe(root, provider=FakeProvider([])) as client:
        failed = client.run(reference, run_id="observed", task_id="history")
    assert not failed.ok, "fixture must contain a real recorded failure"
    return reference, source


def assess(request):
    """A semantic diagnosis that works with observed and source-only inputs."""
    data = prompt_input(request)
    evidence = data["evidence"]
    observations = [item["observation_id"] for item in evidence["observations"]]
    source_path = data["baseline_surface_manifest"]["files"][0]["relative_path"]
    links = [
        {
            "basis": "source",
            "statement": "The captured source defines the workflow behavior.",
            "observation_ids": [],
            "source_paths": [source_path],
        }
    ]
    assessments = [
        {
            "scope": "whole_workflow",
            "step_name": None,
            "classification": "opportunity",
            "dimensions": ["behavioral accuracy"],
            "summary": "The workflow should produce its declared behavioral result.",
            "evidence": links,
            "uncertainty": None,
        }
    ]
    if observations:
        observed = {
            "basis": "observation",
            "statement": "A recorded operation did not complete successfully.",
            "observation_ids": [observations[0]],
            "source_paths": [],
        }
        assessments.append(
            {
                "scope": "step",
                "step_name": evidence["observations"][0]["step_id"],
                "classification": "failure",
                "dimensions": ["reliability", "behavioral accuracy"],
                "summary": "The observed step failed its executable behavior.",
                "evidence": [observed],
                "uncertainty": None,
            }
        )
    else:
        assessments.append(
            {
                "scope": "step",
                "step_name": "runtime behavior",
                "classification": "not_assessed",
                "dimensions": [],
                "summary": "No execution trace is available for step behavior.",
                "evidence": [],
                "uncertainty": "No historical operations were captured.",
            }
        )
    return {
        "workflow_intent": "Execute the selected workflow correctly and durably.",
        "intent_evidence": links,
        "scope_assessments": assessments,
        "rubric": [
            {
                "name": "Preserve intended behavior",
                "applies_to": "whole workflow and changed step",
                "description": "The workflow produces the intended result without breaking existing behavior.",
                "evidence_needed": ["Isolated executable checks", "independent review"],
                "falsification": "A representative input produces an incorrect result.",
            }
        ],
        "uncertainties": [] if observations else ["Runtime behavior is unobserved."],
    }


def propose(request):
    data = prompt_input(request)
    evidence = data["evidence"]
    observation = next(
        item["observation_id"]
        for item in evidence["observations"]
        if item["group_id"] == evidence["selected_group_id"]
    )
    return {
        "candidate": {
            "title": "Correct the increment operation",
            "targets": ["subject.py"],
            "cited_observation_ids": [observation],
            "proposed_change": "Return the input plus one.",
            "expected_effect": "The observed increment failure is corrected.",
            "risks": ["Other numeric inputs must still be supported."],
            "validation_plan": {
                "description": "Exercise actual input/output behavior.",
                "checks": ["Increment positive and negative numbers."],
                "falsification": "Any tested value fails to increment by one.",
            },
        },
        "next_action": "implement_candidate",
        "reason": None,
    }


def no_candidate(request):
    return {
        "candidate": None,
        "next_action": "collect_evidence",
        "reason": "Source inspection found no safe change without runtime evidence.",
    }


ACCEPT = {
    "accepted": True,
    "summary": "The change meets the behavioral requirement.",
    "required_changes": [],
}
REJECT = {
    "accepted": False,
    "summary": "The boundary case remains incorrect.",
    "required_changes": ["Support negative numbers too."],
}


def implement(request):
    source = request.workspace / "subject.py"
    source.write_text(
        source.read_text().replace("return value\n", "return value + 1\n")
    )
    return "Corrected the increment."


def failing_implementation(request):
    source = request.workspace / "subject.py"
    source.write_text(
        source.read_text().replace("return value\n", "return value - 1\n")
    )
    return "Changed the increment incorrectly."


def validation_argv():
    return [
        sys.executable,
        "-c",
        "import runpy; f=runpy.run_path('subject.py')['behavior']; assert f(1)==2; assert f(-2)==-1",
    ]


def evaluation_spec(root, *, invalid=False):
    """The score comes from running the staged implementation, never a constant."""
    calls = root / "evaluator-calls.txt"
    evaluator = root / "evaluator.py"
    evaluator.write_text(
        "import json, os, runpy\nfrom pathlib import Path\n"
        f"with Path({str(calls)!r}).open('a') as f: f.write('call\\n')\n"
        "request = json.loads(Path(os.environ['BOTPIPE_EVAL_REQUEST']).read_text())\n"
        "behavior = runpy.run_path('subject.py')['behavior']\n"
        "cases = [{'case_id': case, 'repetition': 1, 'outcome': 'scored', "
        "'metrics': {'quality': float(behavior(int(case)) == int(case) + 1)}, "
        "'evidence_paths': [], 'usage_availability': 'not_attempted', 'elapsed_seconds': 0.01} for case in request['case_ids']]\n"
        "result = {'schema': 'botpipe.optimizer.eval_result/v1', 'execution_id': request['execution_id'], 'surface_id': request['surface_id'], 'spec_id': request['spec_id'], 'cases': cases}\n"
        + ("result['cases'] = []\n" if invalid else "")
        + "Path(os.environ['BOTPIPE_EVAL_RESULT']).write_text(json.dumps(result))\n",
        encoding="utf-8",
    )
    cases = root / "cases.json"
    cases.write_text('{"cases":[{"id":"1"},{"id":"-2"}]}\n')
    spec = root / "evaluation-spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema": "botpipe.optimizer.evaluation_spec/v1",
                "evaluator_argv": [sys.executable, "{evaluator_path}"],
                "evaluator_path": "evaluator.py",
                "evaluator_content_id": sha256(evaluator.read_bytes()).hexdigest(),
                "case_input_path": "cases.json",
                "case_input_content_id": sha256(cases.read_bytes()).hexdigest(),
                "case_ids": ["1", "-2"],
                "metrics": [
                    {
                        "name": "quality",
                        "unit": "score",
                        "direction": "higher_is_better",
                        "minimum_improvement": 0.1,
                    }
                ],
                "primary_metric": "quality",
            }
        )
    )
    return spec, calls
