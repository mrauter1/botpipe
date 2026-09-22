from __future__ import annotations

import json
from pathlib import Path

import pytest

from botpipe.decisions import (
    Choice,
    ChoiceAnswer,
    Noul,
    NoulAnswer,
    Score,
    ScoreAnswer,
    question_from_record,
)
from botpipe.jev import (
    MAX_JEV_RESPONSE_BYTES,
    DecisionRequest,
    JevAdapter,
    decision_response_from_record,
)
from botpipe.providers import CapabilityError, ProviderError, get_provider
from botpipe.recovery import Completed, Unknown


def questions():
    return {
        "route": Choice(
            instructions="Which route?",
            criteria={"a": "First route", "b": "Second route"},
        ),
        "quality": Score(
            instructions="How good?",
            criteria=("Poor", "Good", "Excellent"),
        ),
        "safe": Noul(instructions="Is it safe?"),
    }


def request(tmp_path: Path) -> DecisionRequest:
    return DecisionRequest(
        operation_id="decision:1",
        state={"evidence": ["one", "two"]},
        questions=questions(),
        receipt_dir=tmp_path / "receipts",
        timeout=2,
    )


def native_response():
    return {
        "model": "jev-1.13.0",
        "answers": {
            "route": {
                "type": "choice",
                "choice": "a",
                "probabilities": {"a": 0.75, "b": 0.25},
                "confidence": 0.5,
            },
            "quality": {
                "type": "score",
                "score": 1.25,
                "legend": {"0": "Poor", "1": "Good", "2": "Excellent"},
                "probabilities": {"0": 0.0, "1": 0.75, "2": 0.25},
                "confidence": 0.5,
            },
            "safe": {"type": "noul", "noul": 0.9},
        },
        "usage": {"input_tokens": 20, "output_tokens": 8},
    }


def test_question_descriptors_round_trip_native_payload() -> None:
    for question in questions().values():
        assert question_from_record(question.to_payload()) == question
    with pytest.raises(ValueError, match="2 to 10"):
        Score("bad", ("only",))
    with pytest.raises(ValueError, match="2 to 255"):
        Choice("bad", {"only": "one"})


def test_jev_preserves_native_typed_answers_and_recovers(tmp_path: Path) -> None:
    calls = []

    def transport(payload, timeout):
        calls.append((payload, timeout))
        return native_response()

    adapter = JevAdapter(transport=transport)
    req = request(tmp_path)
    response = adapter.decide(req)

    assert isinstance(response.answers["route"], ChoiceAnswer)
    assert response.answers["route"].probabilities == {"a": 0.75, "b": 0.25}
    assert isinstance(response.answers["quality"], ScoreAnswer)
    assert response.answers["quality"].legend[2] == "Excellent"
    assert isinstance(response.answers["safe"], NoulAnswer)
    assert response.answers["safe"].noul == 0.9
    assert not hasattr(response.answers["safe"], "confidence")
    assert calls[0][0]["questions"]["safe"] == {
        "type": "noul",
        "instructions": "Is it safe?",
    }
    assert adapter.decide(req) == response
    assert len(calls) == 1
    assert adapter.recover(req) == Completed(response)


def test_decision_response_record_restores_types_without_model_call(
    tmp_path: Path,
) -> None:
    response = JevAdapter(transport=lambda *_: native_response()).decide(request(tmp_path))
    restored = decision_response_from_record(response.to_record(), questions())
    assert restored.answers == response.answers
    assert restored.model == response.model


def test_jev_rejects_mismatched_or_fabricated_native_fields(tmp_path: Path) -> None:
    payload = native_response()
    payload["answers"]["safe"]["confidence"] = 0.8
    with pytest.raises(ProviderError, match="Noul answer"):
        JevAdapter(transport=lambda *_: payload).decide(request(tmp_path))
    outcome = JevAdapter(transport=lambda *_: payload).recover(request(tmp_path))
    assert isinstance(outcome, Unknown)


def test_jev_missing_credentials_fails_before_receipt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    req = request(tmp_path)
    with pytest.raises(CapabilityError, match="TYPESAFE_API_KEY"):
        JevAdapter().decide(req)
    assert not req.receipt_dir.exists()


def test_decision_values_reject_nonfinite_or_invalid_distributions() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        ChoiceAnswer("a", {"a": 0.2, "b": 0.2}, 0.5)
    with pytest.raises(ValueError, match="between 0 and 1"):
        NoulAnswer(float("nan"))


def test_jev_receipt_contains_native_request_without_credentials(tmp_path: Path) -> None:
    req = request(tmp_path)
    JevAdapter(api_key="secret", transport=lambda *_: native_response()).decide(req)
    receipt = next(req.receipt_dir.glob("*.jev.json"))
    durable = json.loads(receipt.read_text())
    assert durable["request"]["model"] == "jev-latest"
    assert "secret" not in receipt.read_text()


def test_provider_registry_selects_session_free_decision_adapter() -> None:
    adapter = get_provider("jev", {"transport": lambda *_: native_response()})
    assert isinstance(adapter, JevAdapter)
    assert adapter.capabilities.decisions is True
    assert adapter.capabilities.sessions is False
    assert not adapter.capabilities.operations


def test_jev_http_rejects_oversized_body_before_json_parse(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, limit):
            assert limit == MAX_JEV_RESPONSE_BYTES + 1
            return b"x" * limit

    monkeypatch.setattr("botpipe.jev.urllib.request.urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(ProviderError, match="transport limit"):
        JevAdapter(api_key="secret")._http({"state": None}, 1)
