from __future__ import annotations

import json

import pytest

from botpipe import (
    Artifact,
    Botpipe,
    BotpipeError,
    RunBusy,
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

        def lose_committed_ack(operation_id, value, **kwargs):
            nonlocal lost
            response(operation_id, value, **kwargs)
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


def test_interrupted_restore_keeps_foreign_workspace_fenced_until_resume(
    tmp_path, monkeypatch
):
    import botpipe.artifacts as artifacts

    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first before")
    second.write_text("second before")

    @workflow
    def work():
        with provider_budget(max_turns=1):
            Provider().run("consume budget")
            return Provider().run(
                "denied",
                writes=[
                    Artifact.text(first, required=True),
                    Artifact.text(second, required=True),
                ],
            )

    @workflow
    def unrelated():
        return "unrelated"

    provider = FakeProvider(["first response"])
    link = artifacts.os.link
    interrupted = False

    def interrupt_after_first_link(source, target, **kwargs):
        nonlocal interrupted
        link(source, target, **kwargs)
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt()

    monkeypatch.setattr(artifacts.os, "link", interrupt_after_first_link)
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(work, run_id="restore-pending", task_id="task")
        denied = _provider_operations(client, paused.run_id)[-1]

    assert paused.status == "interrupted"
    assert denied["response"]["not_dispatched"] is True
    assert denied["response"]["restoration_pending"] is True
    assert first.exists() != second.exists()

    with Botpipe(
        tmp_path,
        state_dir=tmp_path / "foreign-state",
        provider=FakeProvider([]),
    ) as foreign:
        with pytest.raises(RunBusy, match="unresolved effects"):
            foreign.run(unrelated, run_id="foreign", task_id="foreign")

    monkeypatch.setattr(artifacts.os, "link", link)
    with Botpipe(tmp_path, provider=provider) as client:
        resumed = client.resume(paused.run_id, workflow=work)
        denied = client.journal.get(denied["id"])

    assert resumed.status == "budget_exceeded"
    assert first.read_text() == "first before"
    assert second.read_text() == "second before"
    assert denied["response"]["restoration_pending"] is False
    assert len(provider.calls) == 1

    with Botpipe(
        tmp_path,
        state_dir=tmp_path / "foreign-state",
        provider=FakeProvider([]),
    ) as foreign:
        assert foreign.run(unrelated, run_id="foreign", task_id="foreign").ok


def test_policy_error_after_dispatch_remains_unknown_and_fenced(tmp_path):
    destination = tmp_path / "result.txt"
    destination.write_text("before")

    def effect_then_policy_error(request):
        request.artifacts["result"].write_text("attempt output")
        raise ProviderPolicyError("policy failure after dispatch")

    @workflow
    def work():
        return Provider().run("work", writes=[Artifact.text(destination, required=True)])

    provider = FakeProvider([effect_then_policy_error])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(work, run_id="post-dispatch-policy", task_id="task")
        operation = _provider_operations(client, paused.run_id)[0]

        assert paused.status == "interrupted"
        assert destination.read_text() == "attempt output"
        assert not operation["response"].get("not_dispatched", False)
        with pytest.raises(BotpipeError, match="reconciliation is blocked"):
            client.resolve(paused.run_id, operation["id"], retry=True)
        replay = client.resume(paused.run_id, workflow=work)

    assert replay.status == "interrupted"
    assert destination.read_text() == "attempt output"
    assert len(provider.calls) == 1
