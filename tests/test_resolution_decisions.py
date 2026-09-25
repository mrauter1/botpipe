"""Operator choices survive a crash before their effects are recorded."""

import json

import pytest

from botpipe import Artifact, Botpipe, BotpipeError, Provider, Session, workflow
from botpipe.providers import FakeProvider
from botpipe.recovery import Running


def _provider_operation(client, run_id):
    return next(
        row for row in client.journal.operations(run_id) if row["kind"] == "provider"
    )


@pytest.mark.parametrize("choice", ["retry", "accept", "fail"])
def test_resume_finishes_selected_resolution_after_lost_ack(
    tmp_path, monkeypatch, choice
):
    def interrupted(request):
        raise SystemExit("lost turn")

    @workflow
    def work():
        return Provider(session=Session.task("shared")).run("work").value

    provider = FakeProvider([interrupted, "retried", "next"])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="original", task_id="task")
        operation = _provider_operation(client, "original")
        event = client.journal.event

        def lost_ack(run_id, kind, data=None, operation_id=None):
            result = event(run_id, kind, data, operation_id)
            if kind == "resolution_selected":
                raise SystemExit("selection committed")
            return result

        with monkeypatch.context() as patch:
            patch.setattr(client.journal, "event", lost_ack)
            with pytest.raises(SystemExit, match="selection committed"):
                client.resolve("original", operation["id"], **{choice: True})
        other = "retry" if choice != "retry" else "fail"
        with pytest.raises(ValueError, match="recorded resolution"):
            client.resolve("original", operation["id"], **{other: True})

        resumed = client.resume("original", workflow=work)
        assert resumed.status == ("failed" if choice == "fail" else "completed"), (
            resumed.error
        )
        assert len(provider.calls) == (2 if choice == "retry" else 1)
        binding = json.loads(
            next((client.state_dir / "sessions").glob("*.json")).read_text()
        )
        assert binding["pending"] is None
        events = client.journal.events("original")
        assert sum(row["event"] == "resolution_selected" for row in events) == 1
        assert sum(row["event"] == "operation_reconciled" for row in events) == 1
        assert client.run(work, task_id="task").ok


@pytest.mark.parametrize("choice", ["retry", "accept", "fail"])
def test_running_turn_never_records_a_resolution_choice(tmp_path, choice):
    class LiveProvider(FakeProvider):
        def recover(self, request):
            return Running("still running")

    @workflow
    def work():
        return Provider().run("work")

    with Botpipe(tmp_path, provider=LiveProvider([SystemExit()])) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="live")
        operation = _provider_operation(client, "live")
        with pytest.raises(BotpipeError, match="still running"):
            client.resolve("live", operation["id"], **{choice: True})
        assert not any(
            row["event"] == "resolution_selected"
            for row in client.journal.events("live")
        )


def test_selected_accept_keeps_original_artifact_digest_before_response_commit(
    tmp_path, monkeypatch
):
    destination = tmp_path / "report.txt"

    def interrupted(request):
        destination.write_text("approved")
        raise SystemExit()

    @workflow
    def work():
        return Provider().run(
            "report", writes=(Artifact.text(destination, required=True),)
        )

    with Botpipe(tmp_path, provider=FakeProvider([interrupted])) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="original")
        operation = _provider_operation(client, "original")
        event = client.journal.event

        def crash_after_selection(run_id, kind, data=None, operation_id=None):
            result = event(run_id, kind, data, operation_id)
            if kind == "resolution_selected":
                raise SystemExit()
            return result

        with monkeypatch.context() as patch:
            patch.setattr(client.journal, "event", crash_after_selection)
            with pytest.raises(SystemExit):
                client.resolve("original", operation["id"], accept=True)
        destination.write_text("changed after approval")
        with pytest.raises(Exception, match="digest|changed"):
            client.resume("original", workflow=work)
        assert destination.read_text() == "changed after approval"
        assert len(client.provider.calls) == 1
