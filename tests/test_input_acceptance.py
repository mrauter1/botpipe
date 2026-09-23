"""Human answers become durable only after their declared contract accepts them."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, Field, field_validator

from botpipe import Botpipe, ask_human, codec, parallel, workflow
from botpipe.providers import FakeProvider


def test_invalid_custom_validator_answer_can_be_corrected(tmp_path):
    validations = []

    class Approval(BaseModel):
        decision: str

        @field_validator("decision")
        @classmethod
        def known_decision(cls, value):
            validations.append(value)
            if value not in {"approve", "reject"}:
                raise ValueError("choose approve or reject")
            return value

    @workflow
    def gate():
        return ask_human("Decision?", returns=Approval)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(gate)
        operation_id = paused.pending_input["operation_id"]
        rejected = client.resume(
            paused.run_id, workflow=gate, answer={"decision": "typo"}
        )

        assert rejected.status == "awaiting_input"
        assert rejected.pending_input["operation_id"] == operation_id
        assert rejected.pending_input["question"] == "Decision?"
        assert rejected.pending_input["diagnostic"]["type"] == "validation_error"
        assert (
            "choose approve or reject"
            in rejected.pending_input["diagnostic"]["details"][0]["ctx"]["error"]
        )
        assert client.journal.get(operation_id)["status"] == "waiting"

        accepted = client.resume(
            paused.run_id, workflow=gate, answer={"decision": "approve"}
        )
        assert accepted.ok, accepted.error
        assert accepted.value == Approval(decision="approve")
        assert validations == ["typo", "approve", "approve"]

        replayed = client.resume(paused.run_id, workflow=gate)
        assert replayed.value == accepted.value
        assert validations == ["typo", "approve", "approve"]


@dataclass
class DataclassAnswer:
    approved: bool


class AliasedAnswer(BaseModel):
    value: int = Field(alias="answerValue")


@pytest.mark.parametrize(
    ("contract", "answer"),
    [
        (DataclassAnswer, DataclassAnswer(True)),
        (datetime, datetime(2026, 1, 1, tzinfo=UTC)),
        (tuple[int, ...], (1, 2)),
        (AliasedAnswer, AliasedAnswer(answerValue=7)),
    ],
)
def test_sdk_accepts_typed_python_answers(tmp_path, contract, answer):
    @workflow
    def gate():
        return ask_human("Answer?", returns=contract)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(gate)
        result = client.resume(paused.run_id, workflow=gate, answer=answer)

        assert result.ok, result.error
        assert result.value == answer
        assert client.resume(paused.run_id, workflow=gate).value == answer


def test_answer_that_cannot_be_encoded_stays_waiting(tmp_path):
    @workflow
    def gate():
        return ask_human("Durable value?", returns=Any)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(gate)
        operation_id = paused.pending_input["operation_id"]
        rejected = client.resume(paused.run_id, workflow=gate, answer=object())

        assert rejected.status == "awaiting_input"
        assert rejected.pending_input["diagnostic"]["type"] == "encoding_error"
        assert client.journal.get(operation_id)["status"] == "waiting"
        corrected = client.resume(paused.run_id, workflow=gate, answer="safe")
        assert corrected.value == "safe"


def test_unexpected_validator_bug_is_not_reported_as_bad_input(tmp_path):
    class Broken(BaseModel):
        value: int

        @field_validator("value")
        @classmethod
        def broken_validator(cls, value):
            raise RuntimeError("validator bug")

    @workflow
    def gate():
        return ask_human("Value?", returns=Broken)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(gate)
        result = client.resume(paused.run_id, workflow=gate, answer={"value": 1})

        assert result.status == "failed"
        assert result.pending_input is None
        assert "RuntimeError: validator bug" in result.error


def test_nested_answer_candidate_reaches_only_target_ask(tmp_path):
    @workflow
    def child():
        return ask_human("Nested?", returns=int)

    @workflow
    def parent():
        return child()

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(parent)
        completed = client.resume(paused.run_id, workflow=parent, answer="4")

        assert completed.value == 4


def test_parallel_answers_are_keyed_to_the_pending_operation(tmp_path):
    def left():
        return ask_human("Left?", returns=int)

    def right():
        return ask_human("Right?", returns=int)

    @workflow
    def both():
        return parallel(left, right)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        first = client.run(both)
        assert first.pending_input["question"] == "Left?"

        second = client.resume(first.run_id, workflow=both, answer="1")
        assert second.status == "awaiting_input"
        assert second.pending_input["question"] == "Right?"

        completed = client.resume(first.run_id, workflow=both, answer="2")
        assert completed.value == [1, 2]


def test_answer_can_be_resubmitted_when_acceptance_did_not_commit(
    tmp_path, monkeypatch
):
    @workflow
    def gate():
        return ask_human("Approve?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(gate)
        response = client.journal.response

        def fail_before_commit(*args, **kwargs):
            raise OSError("checkpoint unavailable")

        monkeypatch.setattr(client.journal, "response", fail_before_commit)
        interrupted = client.resume(paused.run_id, workflow=gate, answer="yes")
        assert interrupted.status == "interrupted"
        assert interrupted.pending_input == paused.pending_input

        monkeypatch.setattr(client.journal, "response", response)
        assert client.resume(paused.run_id, workflow=gate, answer="yes").value == "yes"


def test_interruption_before_acceptance_keeps_answer_target(tmp_path):
    class InterruptOnce(BaseModel):
        value: int

        @field_validator("value")
        @classmethod
        def interrupt(cls, value):
            if value == 1:
                raise KeyboardInterrupt
            return value

    @workflow
    def gate():
        return ask_human("Value?", returns=InterruptOnce)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(gate)
        interrupted = client.resume(paused.run_id, workflow=gate, answer={"value": 1})

        assert interrupted.status == "interrupted"
        assert interrupted.pending_input == paused.pending_input
        corrected = client.resume(paused.run_id, workflow=gate, answer={"value": 2})
        assert corrected.value == InterruptOnce(value=2)


def test_accepted_answer_survives_finish_crash_without_revalidation(
    tmp_path, monkeypatch
):
    validations = []

    class Answer(BaseModel):
        number: int

        @field_validator("number")
        @classmethod
        def observe(cls, value):
            validations.append(value)
            return value

    @workflow
    def gate():
        return ask_human("Number?", returns=Answer)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(gate)
        finish = client.journal.finish

        def crash_after_acceptance(*args, **kwargs):
            raise SystemExit("crash after accepted response")

        monkeypatch.setattr(client.journal, "finish", crash_after_acceptance)
        with pytest.raises(SystemExit):
            client.resume(paused.run_id, workflow=gate, answer={"number": 3})
        assert validations == [3]

        monkeypatch.setattr(client.journal, "finish", finish)
        completed = client.resume(paused.run_id, workflow=gate)
        assert completed.value == Answer(number=3)
        assert validations == [3, 3]


def test_lost_acceptance_ack_uses_committed_answer(tmp_path, monkeypatch):
    @workflow
    def gate():
        return ask_human("Approve?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(gate)
        response = client.journal.response

        def lose_ack(*args, **kwargs):
            response(*args, **kwargs)
            raise OSError("lost acknowledgement")

        monkeypatch.setattr(client.journal, "response", lose_ack)
        completed = client.resume(paused.run_id, workflow=gate, answer="yes")

        assert completed.value == "yes"


def test_stale_pending_metadata_cannot_replace_accepted_answer(tmp_path):
    @workflow
    def gate():
        return ask_human("Approve?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(gate)
        operation_id = paused.pending_input["operation_id"]
        client.journal.response(
            operation_id, {"validated_answer": codec.encode("first")}
        )

        with pytest.raises(ValueError, match="no longer waiting"):
            client.resume(paused.run_id, workflow=gate, answer="second")
        assert client.resume(paused.run_id, workflow=gate).value == "first"


def test_unvalidated_answer_checkpoint_is_rejected_without_revalidation(tmp_path):
    @workflow
    def gate():
        return ask_human("Approve?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(gate)
        operation_id = paused.pending_input["operation_id"]
        client.journal.response(operation_id, {"answer": codec.encode("legacy")})

        result = client.resume(paused.run_id, workflow=gate)

        assert result.status == "failed"
        assert "missing its validated answer" in result.error
        assert client.journal.get(operation_id)["status"] == "response"


def test_cli_rejected_answer_is_actionable_and_correctable(tmp_path):
    source = tmp_path / "approval.py"
    source.write_text(
        "from typing import Literal\n"
        "from botpipe import ask_human, workflow\n"
        "@workflow\n"
        "def gate():\n"
        "    return ask_human('Decision?', returns=Literal['approve', 'reject'])\n"
    )
    state = tmp_path / "state"
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            filter(
                None,
                (
                    str(Path(__file__).resolve().parents[1]),
                    os.environ.get("PYTHONPATH"),
                ),
            )
        ),
    }

    def cli(*args):
        return subprocess.run(
            [
                str(Path(os.environ.get("VIRTUAL_ENV", "")) / "bin" / "python")
                if os.environ.get("VIRTUAL_ENV")
                else os.sys.executable,
                "-m",
                "botpipe.cli",
                *args,
                "--workspace",
                str(tmp_path),
                "--state-dir",
                str(state),
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    started = cli("run", f"{source}:gate")
    run_id = json.loads(started.stdout)["run_id"]
    rejected = cli("resume", run_id, "--workflow", f"{source}:gate", "--answer", "typo")
    rejected_body = json.loads(rejected.stdout)

    assert rejected.returncode == 2, rejected.stderr
    assert rejected_body["status"] == "awaiting_input"
    assert rejected_body["pending_input"]["diagnostic"]["type"] == "validation_error"

    corrected = cli(
        "resume", run_id, "--workflow", f"{source}:gate", "--answer", "approve"
    )
    assert corrected.returncode == 0, corrected.stderr
    assert json.loads(corrected.stdout)["value"] == "approve"
