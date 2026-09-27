from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from botpipe.errors import BudgetExceeded
from botpipe.providers import ProviderError
from botpipe_optimizer.judging import (
    aggregate_judgments,
    build_judge_packet,
    judge_pair,
)
from botpipe_optimizer.trial_models import TrialResult

RUBRIC = [
    {
        "name": "Correct",
        "applies_to": "returned value",
        "description": "The answer is correct.",
        "evidence_needed": ["actual trial result"],
        "falsification": "The returned answer is wrong.",
        "must_preserve": False,
    },
    {
        "name": "Preserve safety",
        "applies_to": "returned value",
        "description": "Existing safety behavior remains intact.",
        "evidence_needed": ["actual trial result"],
        "falsification": "A required safety property is absent.",
        "must_preserve": True,
    },
]


def _trial(**changes):
    values = {
        "case_id": "case-1",
        "execution": "complete",
        "outcome": "completed",
        "run_id": "trial-secret",
        "value": {"answer": 42},
        "artifacts": [],
        "operations": [],
        "usage": {"total_tokens": 3},
        "elapsed_seconds": 0.25,
    }
    values.update(changes)
    return TrialResult(**values)


def _packet(**changes):
    values = {
        "case": {
            "case_id": "case-1",
            "intent": "Answer accurately while preserving safety.",
            "description": "Return the answer.",
            "args": [1],
            "kwargs": {"format": "number"},
        },
        "rubric": RUBRIC,
        "comparison_rule": "Prefer the side satisfying more criteria; tie equal behavior.",
        "a": _trial(),
        "b": _trial(value={"answer": 41}),
        "max_bytes": 48_000,
    }
    values.update(changes)
    return build_judge_packet(**values)


def _judgment(preference="A", *, a="met", b="met", second_a="met", second_b="met"):
    return {
        "preference": preference,
        "criteria": [
            {
                "criterion": "Correct",
                "a": a,
                "b": b,
                "explanation": "Compared answers.",
            },
            {
                "criterion": "Preserve safety",
                "a": second_a,
                "b": second_b,
                "explanation": "Compared safety.",
            },
        ],
        "explanation": "A is better.",
        "evidence_quotes": ['"answer":42'],
    }


def _pair(candidate_label, preference="A", **judgment_changes):
    return {
        "case_id": "case-1",
        "repetition": 0,
        "rubric": RUBRIC,
        "judgments": [
            {
                "candidate_label": candidate_label,
                "result": {
                    "status": "judged",
                    "judgment": _judgment(preference, **judgment_changes),
                },
            }
        ],
    }


@pytest.mark.parametrize(
    "artifact_path",
    ["/tmp/secret/report.txt", r"C:\secret\report.txt", r"\\host\share\report.txt"],
)
def test_packet_is_anonymous_and_keeps_behavioral_prose_unchanged(artifact_path):
    trial = _trial(
        value={
            "text": "candidate said /tmp/output in its answer",
            "source": "a behavioral citation",
            "code": "user-requested output",
        },
        artifacts=[
            {
                "key": "report",
                "path": artifact_path,
                "source_code": "raise RuntimeError('arm-a')",
                "schema": {
                    "python_type": "candidate.models:SecretImplementation",
                    "json_schema": {"title": "SecretImplementation"},
                },
                "content": "The baseline and candidate labels are user output.",
            }
        ],
        operations=[
            {
                "id": "op-secret",
                "scope": "run-secret",
                "name": "answer",
                "prompt": "provider-only prompt",
                "provider": "secret-provider",
                "response": "candidate response",
            }
        ],
    )

    packet = _packet(a=trial)
    encoded = json.dumps(packet, sort_keys=True)

    assert "trial-secret" not in encoded
    assert "op-secret" not in encoded
    assert "provider-only prompt" not in encoded
    assert "secret-provider" not in encoded
    assert "raise RuntimeError" not in encoded
    assert "SecretImplementation" not in encoded
    assert packet["A"]["artifacts"][0]["path"] == "<redacted: absolute path>"
    assert packet["task"]["intent"] == "Answer accurately while preserving safety."
    assert packet["A"]["value"]["text"] == "candidate said /tmp/output in its answer"
    assert packet["A"]["value"]["source"] == "a behavioral citation"
    assert packet["A"]["value"]["code"] == "user-requested output"
    assert (
        packet["A"]["artifacts"][0]["content"]
        == "The baseline and candidate labels are user output."
    )


def test_packet_cap_omits_optional_operations_then_marks_missing_essential():
    huge = _trial(
        value="v" * 3_000,
        operations=[{"name": "detail", "response": "o" * 5_000}],
    )

    packet = _packet(a=huge, b=huge, max_bytes=1_800)
    encoded = json.dumps(
        packet, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()

    assert len(encoded) <= 1_800
    assert packet["complete"] is False
    assert packet["A"]["operations"] == []
    assert any("optional operation details" in item for item in packet["omissions"])
    assert any("essential evidence" in item for item in packet["omissions"])
    assert judge_pair(packet=packet)["status"] == "inconclusive"


def test_packet_keeps_frozen_input_references_and_missing_reference_is_inconclusive():
    reference = {
        "path": "inputs/request.txt",
        "content": "Exact frozen input bytes.",
    }
    packet = _packet(
        case={
            "intent": "Use the supplied input.",
            "description": "Read the request.",
            "args": ["inputs/request.txt"],
            "kwargs": {},
            "references": [reference],
            "omissions": [],
        }
    )

    assert packet["complete"] is True
    assert packet["task"]["references"] == [reference]
    assert packet["task"]["args"] == ["inputs/request.txt"]

    incomplete = _packet(
        case={
            "description": "Read the request.",
            "args": ["inputs/missing.bin"],
            "kwargs": {},
            "references": [],
            "omissions": ["inputs/missing.bin is binary"],
        }
    )
    assert incomplete["complete"] is False
    assert "inputs/missing.bin is binary" in incomplete["omissions"][0]
    assert judge_pair(packet=incomplete)["status"] == "inconclusive"


def test_oversize_frozen_reference_is_an_explicit_essential_omission():
    packet = _packet(
        case={
            "description": "Read the request.",
            "args": [],
            "kwargs": {},
            "references": [{"path": "request.txt", "content": "x" * 5_000}],
            "omissions": [],
        },
        max_bytes=1_800,
    )

    assert packet["complete"] is False
    assert (
        packet["task"]["references"][0]["content"]
        == "<omitted: essential evidence exceeded max_bytes>"
    )
    assert any(
        item.startswith("task.references.0.content: essential evidence omitted")
        for item in packet["omissions"]
    )


def test_runtime_ledger_omission_does_not_make_packet_incomplete():
    trial = _trial(
        operations=[
            {"kind": "provider_budget", "id": "ledger-id", "usage": {"turns": 2}},
            {"kind": "provider", "id": "op-id", "response": "done"},
        ],
        omissions=["worker stdout was truncated"],
    )

    packet = _packet(a=trial)

    assert packet["complete"] is True
    assert packet["A"]["operations"] == [{"response": "done"}]


def test_missing_selected_artifact_content_makes_packet_incomplete():
    trial = _trial(
        artifacts=[
            {
                "key": "report",
                "content_omitted": "oversize",
                "size_bytes": 50_000,
            }
        ]
    )

    packet = _packet(a=trial)

    assert packet["complete"] is False
    assert any(
        "selected artifact content is unavailable" in item
        for item in packet["omissions"]
    )


@dataclass
class _Response:
    value: object


class _Provider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.config_calls = []
        self.generate_calls = []

    def with_config(self, **kwargs):
        self.config_calls.append(kwargs)
        return self

    def generate(self, prompt, **kwargs):
        self.generate_calls.append((prompt, kwargs))
        item = next(self.responses)
        if isinstance(item, BaseException):
            raise item
        return _Response(item)


def test_judge_uses_fresh_session_no_tools_and_repairs_bad_quote(monkeypatch):
    provider = _Provider(
        [
            _judgment() | {"evidence_quotes": ["fabricated quote"]},
            _judgment(),
        ]
    )
    monkeypatch.setattr("botpipe_optimizer.judging.Provider", lambda: provider)

    result = judge_pair(packet=_packet(), max_repairs=1, timeout=17)

    assert result["status"] == "judged"
    assert provider.config_calls == [{"session": None}]
    assert len(provider.generate_calls) == 2
    assert all(call[1]["allowed_tools"] == () for call in provider.generate_calls)
    assert all(call[1]["output_retries"] == 0 for call in provider.generate_calls)
    assert all(call[1]["timeout"] == 17.0 for call in provider.generate_calls)
    assert "not an exact excerpt" in provider.generate_calls[1][0]


def test_judge_repairs_missing_and_duplicate_criteria(monkeypatch):
    invalid = _judgment()
    invalid["criteria"] = [invalid["criteria"][0], invalid["criteria"][0]]
    provider = _Provider([invalid, _judgment()])
    monkeypatch.setattr("botpipe_optimizer.judging.Provider", lambda: provider)

    result = judge_pair(packet=_packet(), max_repairs=1)

    assert result["status"] == "judged"
    repair = provider.generate_calls[1][0]
    assert "missing rubric criteria" in repair
    assert "duplicate rubric criteria" in repair


def test_judge_exhaustion_is_inconclusive(monkeypatch):
    invalid = _judgment() | {"evidence_quotes": ["invented"]}
    provider = _Provider([invalid, invalid])
    monkeypatch.setattr("botpipe_optimizer.judging.Provider", lambda: provider)

    result = judge_pair(packet=_packet(), max_repairs=1)

    assert result["status"] == "inconclusive"
    assert "after 2 attempt(s)" in result["reason"]


def test_judge_does_not_swallow_budget_suspension(monkeypatch):
    provider = _Provider([BudgetExceeded("judge turn budget")])
    monkeypatch.setattr("botpipe_optimizer.judging.Provider", lambda: provider)

    with pytest.raises(BudgetExceeded):
        judge_pair(packet=_packet())


def test_judge_reports_provider_dispatch_failure_as_infrastructure(monkeypatch):
    provider = _Provider([ProviderError("adapter unavailable")])
    monkeypatch.setattr("botpipe_optimizer.judging.Provider", lambda: provider)

    result = judge_pair(packet=_packet())

    assert result["status"] == "inconclusive"
    assert result["reason"] == (
        "judge infrastructure failure: ProviderError: adapter unavailable"
    )


@pytest.mark.parametrize(
    ("pairs", "expected"),
    [
        ([_pair("A", "A")], "improved"),
        ([_pair("A", "B")], "regressed"),
        ([_pair("A", "tie")], "no_material_change"),
        ([_pair("A", "A"), _pair("A", "B")], "inconclusive"),
    ],
)
def test_aggregate_fixed_across_case_rule(pairs, expected):
    assert aggregate_judgments(pairs)["state"] == expected


def test_aggregate_normalizes_reversed_order_and_detects_contradiction():
    pair = _pair("A", "A", a="met", b="not_met")
    pair["judgments"].append(
        {
            "candidate_label": "B",
            "result": {
                "status": "judged",
                "judgment": _judgment("B", a="not_met", b="met"),
            },
        }
    )
    assert aggregate_judgments([pair])["state"] == "improved"

    pair["judgments"][1]["result"]["judgment"]["preference"] = "A"
    result = aggregate_judgments([pair])
    assert result["state"] == "inconclusive"
    assert "contradictory" in result["reason"]


def test_aggregate_unknown_or_hard_candidate_failure_blocks_improvement():
    unknown = _pair("A", "A", b="unknown")
    assert aggregate_judgments([unknown])["state"] == "inconclusive"

    hard_failure = _pair("A", "A", second_a="not_met")
    result = aggregate_judgments([hard_failure])
    assert result["state"] == "inconclusive"
    assert "hard candidate failure" in result["reason"]
