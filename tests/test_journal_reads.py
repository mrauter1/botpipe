from __future__ import annotations

import pytest

from botpipe import Botpipe
from botpipe.journal import Journal, JournalSnapshot
from botpipe.providers import FakeProvider
from botpipe.read_projection import _inspection_value, project_run


def _run_record(run_id="run", **updates):
    return {
        "run_id": run_id,
        "task_id": "task",
        "args": {"$botpipe": "tuple", "value": []},
        "kwargs": {"$botpipe": "dict", "value": {}},
        "status": "running",
        "error": None,
        **updates,
    }


def _begin(journal, *, run_id="run", operation_id="op", kind="activity"):
    journal.begin(
        operation_id=operation_id,
        run_id=run_id,
        scope="root",
        ordinal=0,
        kind=kind,
        name="effect",
        fingerprint="fingerprint",
        inputs={"$botpipe": "dict", "value": {}},
        limit=10,
    )


def test_snapshot_reads_run_operations_and_events_as_one_projection(tmp_path):
    journal = Journal(tmp_path)
    try:
        journal.create_run(_run_record(error="root orchestration failed"))
        _begin(journal)
        journal.event("run", "root_failure", {"message": "retained"})

        snapshot = journal.snapshot("run")

        assert snapshot.run["error"] == "root orchestration failed"
        assert [row["id"] for row in snapshot.operations] == ["op"]
        assert snapshot.events[-1]["data"] == {"message": "retained"}
    finally:
        journal.close()


def test_snapshot_is_a_bounded_prefix_and_ignores_incomplete_tail(tmp_path):
    journal = Journal(tmp_path)
    try:
        journal.create_run(_run_record(status="running"))
        ledger = tmp_path / "tasks" / "task" / "runs" / "run" / "ledger.jsonl"
        with ledger.open("ab") as stream:
            stream.write(b'{"seq":2,"event":"run_updated"')
        snapshot = journal.snapshot("run")
        assert snapshot.run["status"] == "running"
        assert snapshot.run["error"] is None
        assert snapshot.last_seq == 1
        assert ledger.read_bytes().endswith(b'"run_updated"')
    finally:
        journal.close()


def test_read_only_snapshot_does_not_create_or_mutate_foreign_journal(tmp_path):
    path = tmp_path / "foreign"
    journal = Journal(path)
    journal.create_run(_run_record())
    _begin(journal)
    journal.close()
    ledger = path / "tasks" / "task" / "runs" / "run" / "ledger.jsonl"
    before = ledger.read_bytes()

    snapshot = Journal.read_only_snapshot(path, "run")

    assert snapshot.run["run_id"] == "run"
    assert ledger.read_bytes() == before


@pytest.mark.parametrize(
    "encoded",
    [
        {"$botpipe": "capsule", "version": 2, "sources": {}, "value": None},
        {
            "$botpipe": "capsule",
            "version": 1,
            "sources": {},
            "value": None,
            "extra": True,
        },
        {"$botpipe": "dict", "value": {1: "not a durable key"}},
    ],
)
def test_artifact_inspection_rejects_malformed_plain_wrappers(encoded):
    with pytest.raises(TypeError):
        _inspection_value(encoded)


def test_plain_value_inspection_does_not_resolve_types(monkeypatch):
    from botpipe import codec
    from botpipe.read_projection import _inspection_value

    record = codec.encode({"name": "report"})

    def no_import(*args, **kwargs):
        pytest.fail("Inspection attempted application type resolution")

    monkeypatch.setattr(codec, "resolve_type", no_import)
    assert _inspection_value(record) == {"name": "report"}


def test_projection_uses_physical_dispatch_events_not_response_claims():
    operation = {
        "id": "op",
        "run_id": "run",
        "scope": "root",
        "ordinal": 0,
        "kind": "provider",
        "name": "turn",
        "fingerprint": "fingerprint",
        "inputs": {},
        "status": "response",
        "result": None,
        "error": None,
        "response": {"usage": {"total_tokens": 999}},
        "started_at": "2020-01-01T00:00:00+00:00",
        "finished_at": None,
    }
    events = (
        {
            "seq": 1,
            "run_id": "run",
            "operation_id": "op",
            "event": "provider_dispatch_reserved",
            "data": {"dispatch_id": "first", "provider": "fake"},
            "at": "2020-01-01T00:00:01+00:00",
        },
        {
            "seq": 2,
            "run_id": "run",
            "operation_id": "op",
            "event": "provider_dispatch_finished",
            "data": {
                "dispatch_id": "first",
                "usage_availability": "partial",
                "usage": {"input_tokens": 3},
                "outcome": "failed",
            },
            "at": "2020-01-01T00:00:02+00:00",
        },
        {
            "seq": 3,
            "run_id": "run",
            "operation_id": "op",
            "event": "provider_dispatch_reserved",
            "data": {"dispatch_id": "second", "provider": "fake"},
            "at": "2020-01-01T00:00:03+00:00",
        },
    )
    snapshot = JournalSnapshot(_run_record(), (operation,), events)

    projection = project_run(snapshot)
    record = projection.operations[0]

    assert len(record["dispatches"]) == 2
    assert record["usage"] == {"input_tokens": 3}
    assert record["usage_availability"] == "partial"
    assert projection.usage == {"input_tokens": 3}


def test_response_claim_does_not_replace_missing_dispatch_evidence():
    operation = {
        "id": "op",
        "run_id": "run",
        "scope": "root",
        "ordinal": 0,
        "kind": "provider",
        "name": "turn",
        "fingerprint": "fingerprint",
        "inputs": {},
        "status": "response",
        "result": None,
        "error": None,
        "response": {"usage": {"total_tokens": 999}},
        "started_at": "2020-01-01T00:00:00+00:00",
        "finished_at": None,
    }

    projection = project_run(JournalSnapshot(_run_record(), (operation,), ()))

    assert projection.operations[0]["usage"] == {}
    assert "dispatches" not in projection.operations[0]
    assert projection.usage == {}


def test_inspect_consumes_exactly_one_journal_snapshot(tmp_path, monkeypatch):
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        snapshot = JournalSnapshot(
            _run_record(status="failed", error="root failure"), (), ()
        )
        calls = []

        def once(run_id):
            calls.append(run_id)
            if len(calls) > 1:
                pytest.fail("inspect opened more than one journal snapshot")
            return snapshot

        monkeypatch.setattr(client.journal, "snapshot", once)

        inspected = client.inspect("run")

    assert calls == ["run"]
    assert inspected["run"]["error"] == "root failure"
    assert inspected["operations"] == []
    assert inspected["events"] == []
