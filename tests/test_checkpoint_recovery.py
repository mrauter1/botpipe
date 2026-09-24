from __future__ import annotations

import json

import pytest

from botpipe import (
    Artifact,
    Botpipe,
    Provider,
    provider_budget,
    workflow,
)
from botpipe.providers import FakeProvider, ProviderPolicyError


def _provider_operations(client: Botpipe, run_id: str) -> list[dict]:
    return [
        row for row in client.journal.operations(run_id) if row["kind"] == "provider"
    ]


def test_committed_finish_with_lost_ack_remains_completed(tmp_path, monkeypatch):
    destination = tmp_path / "result.txt"

    def write(request):
        request.artifacts["result"].write_text("provider result")
        return "done"

    @workflow
    def work():
        return Provider().run(
            "write", writes=[Artifact.text(destination, required=True)]
        )

    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        finish = client.journal.finish
        lost = False

        def lose_committed_ack(operation_id, result):
            nonlocal lost
            finish(operation_id, result)
            if client.journal.get(operation_id)["kind"] == "provider" and not lost:
                lost = True
                raise OSError("lost finish acknowledgement")

        monkeypatch.setattr(client.journal, "finish", lose_committed_ack)
        result = client.run(work, run_id="finish-ack", task_id="task")

    assert result.ok, result.error
    assert result.value.artifacts.result.read_text() == "provider result"
    assert len(provider.calls) == 1

    with Botpipe(tmp_path, provider=provider) as client:
        replay = client.resume("finish-ack", workflow=work)
    assert replay.ok, replay.error
    assert len(provider.calls) == 1


def test_committed_provider_response_with_lost_ack_is_not_failed(tmp_path, monkeypatch):
    destination = tmp_path / "result.txt"

    def write(request):
        request.artifacts["result"].write_text("provider result")
        return "done"

    @workflow
    def work():
        return Provider().run(
            "write", writes=[Artifact.text(destination, required=True)]
        )

    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        response = client.journal.response
        lost = False

        def lose_committed_ack(operation_id, value, session_key=None):
            nonlocal lost
            response(operation_id, value, session_key)
            if "text" in value and "validated_value" not in value and not lost:
                lost = True
                raise OSError("lost response acknowledgement")

        monkeypatch.setattr(client.journal, "response", lose_committed_ack)
        result = client.run(work, run_id="response-ack", task_id="task")

    assert result.ok, result.error
    assert result.value.artifacts.result.read_text() == "provider result"
    assert len(provider.calls) == 1

    with Botpipe(tmp_path, provider=provider) as client:
        replay = client.resume("response-ack", workflow=work)
    assert replay.ok, replay.error
    assert len(provider.calls) == 1


def test_uncommitted_finish_is_not_confirmed_from_writer_connection(
    tmp_path, monkeypatch
):
    @workflow
    def work():
        return Provider().run("work").value

    provider = FakeProvider(["done"])
    with Botpipe(tmp_path, provider=provider) as client:
        finish = client.journal.finish
        interrupted = False

        def leave_uncommitted_result(operation_id, result):
            nonlocal interrupted
            if (
                client.journal.get(operation_id)["kind"] == "provider"
                and not interrupted
            ):
                interrupted = True
                client.journal.db.execute("BEGIN IMMEDIATE")
                client.journal.db.execute(
                    "UPDATE operations SET status='completed',result=? WHERE id=?",
                    (json.dumps(result), operation_id),
                )
                raise OSError("commit failed with transaction still open")
            return finish(operation_id, result)

        monkeypatch.setattr(client.journal, "finish", leave_uncommitted_result)
        paused = client.run(work, run_id="uncommitted-finish", task_id="task")
        operation = _provider_operations(client, paused.run_id)[0]

        assert paused.status == "interrupted"
        assert operation["status"] == "response"
        assert not client.journal.db.in_transaction
        monkeypatch.setattr(client.journal, "finish", finish)
        resumed = client.resume(paused.run_id, workflow=work)

    assert resumed.ok, resumed.error
    assert resumed.value == "done"
    assert len(provider.calls) == 1


def test_budget_rejection_preserves_all_existing_outputs(tmp_path):
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    first.write_text("first before")
    second.write_text("second before")

    @workflow
    def work():
        with provider_budget(max_turns=1):
            Provider().run("consume budget")
            return Provider().run(
                "denied", writes=[Artifact.text(first), Artifact.text(second)]
            )

    provider = FakeProvider(["first response"])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work)
        assert result.status == "budget_exceeded"
        assert client.resume(result.run_id, workflow=work).status == "budget_exceeded"
    assert first.read_text() == "first before"
    assert second.read_text() == "second before"
    assert len(provider.calls) == 1


def test_policy_error_after_dispatch_requires_explicit_retry(tmp_path):
    destination = tmp_path / "result.txt"
    destination.write_text("before")

    def effect_then_policy_error(request):
        request.artifacts["result"].write_text("attempt output")
        raise ProviderPolicyError("policy failure after dispatch")

    def retry(request):
        assert request.artifacts["result"].read_text() == "attempt output"
        request.artifacts["result"].write_text("retry output")
        return "retry complete"

    @workflow
    def work():
        return Provider().run("work", writes=[Artifact.text(destination, required=True)])

    provider = FakeProvider([effect_then_policy_error, retry])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(work, run_id="post-dispatch-policy", task_id="task")
        operation = _provider_operations(client, paused.run_id)[0]

        assert paused.status == "interrupted"
        assert destination.read_text() == "attempt output"
        assert not operation["response"].get("not_dispatched", False)
        silent = client.resume(paused.run_id, workflow=work)
        assert silent.status == "interrupted"
        assert len(provider.calls) == 1
        client.resolve(paused.run_id, operation["id"], retry=True)
        replay = client.resume(paused.run_id, workflow=work)

    assert replay.ok, replay.error
    assert destination.read_text() == "retry output"
    assert len(provider.calls) == 2
