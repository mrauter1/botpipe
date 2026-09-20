from __future__ import annotations

import json

import pytest

from botpipe import Botpipe
from botpipe.journal import Journal, JournalSnapshot
from botpipe.providers import FakeProvider
from botpipe.read_projection import _inspection_value, project_run


def _run_record(run_id="run", **updates):
    return {
        "run_id": run_id,
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


def _provider_journal(tmp_path, response, *, writes, capsule=False):
    path = tmp_path / "provider.sqlite3"
    inputs = {"$botpipe": "dict", "value": {"writes": writes}}
    if capsule:
        inputs = {
            "$botpipe": "capsule",
            "version": 1,
            "sources": {},
            "value": inputs,
        }
    journal = Journal(path)
    journal.create_run(_run_record())
    journal.begin(
        operation_id="op",
        run_id="run",
        scope="root",
        ordinal=0,
        kind="provider",
        name="turn",
        fingerprint="fingerprint",
        inputs=inputs,
        limit=10,
    )
    journal.response("op", response)
    journal.close()
    return path


def test_snapshot_reads_run_operations_and_events_as_one_projection(tmp_path):
    journal = Journal(tmp_path / "state.sqlite3")
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


def test_snapshot_never_exposes_uncommitted_writer_state(tmp_path):
    journal = Journal(tmp_path / "state.sqlite3")
    try:
        journal.create_run(_run_record(status="running"))
        with journal.transaction() as db:
            changed = _run_record(status="failed", error="not committed")
            db.execute(
                "UPDATE runs SET metadata=? WHERE id=?",
                (json.dumps(changed), "run"),
            )
            snapshot = journal.snapshot("run")
            assert snapshot.run["status"] == "running"
            assert snapshot.run["error"] is None
    finally:
        journal.close()


def test_read_only_snapshot_does_not_create_or_mutate_foreign_journal(tmp_path):
    path = tmp_path / "foreign.sqlite3"
    journal = Journal(path)
    journal.create_run(_run_record())
    _begin(journal)
    journal.close()
    before = path.read_bytes()

    snapshot = Journal.read_only_snapshot(path, "run")

    assert snapshot.run["run_id"] == "run"
    assert path.read_bytes() == before
    missing = tmp_path / "missing.sqlite3"
    assert Journal.foreign_has_unresolved_effects(missing, "run") is True
    assert not missing.exists()


def test_foreign_malformed_journal_is_conservatively_fenced(tmp_path):
    path = tmp_path / "malformed.sqlite3"
    path.write_bytes(b"not a sqlite database")

    assert Journal.foreign_has_unresolved_effects(path, "run") is True
    assert path.read_bytes() == b"not a sqlite database"


@pytest.mark.parametrize(
    "metadata",
    [[], {"run_id": "different", "status": "running"}],
)
def test_foreign_run_metadata_must_match_journal_identity(tmp_path, metadata):
    path = tmp_path / "foreign.sqlite3"
    journal = Journal(path)
    journal.create_run(_run_record())
    with journal.transaction() as db:
        db.execute("UPDATE runs SET metadata=? WHERE id='run'", (json.dumps(metadata),))
    journal.close()

    assert Journal.foreign_has_unresolved_effects(path, "run") is True


def test_unknown_effect_checkpoint_status_is_conservatively_fenced():
    assert Journal._has_unresolved_effects(
        ({"kind": "provider", "status": "future-checkpoint"},)
    )


def test_provider_writes_are_read_through_tagged_and_capsule_inputs():
    without_writes = {"$botpipe": "dict", "value": {"writes": []}}
    with_writes = {
        "$botpipe": "capsule",
        "version": 1,
        "sources": {},
        "value": {"$botpipe": "dict", "value": {"writes": [{}]}},
    }

    assert Journal._provider_has_writes(without_writes) is False
    assert Journal._provider_has_writes(with_writes) is True
    with pytest.raises(ValueError, match="writes declaration"):
        Journal._provider_has_writes({"$botpipe": "dict", "value": {}})


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


def test_unfinished_activity_remains_fenced_regardless_of_provider_flags(tmp_path):
    path = tmp_path / "activity.sqlite3"
    journal = Journal(path)
    journal.create_run(_run_record())
    _begin(journal)
    journal.response("op", {"not_dispatched": True, "restoration_pending": True})
    journal.close()
    assert Journal.foreign_has_unresolved_effects(path, "run") is True

    journal = Journal(path)
    journal.response("op", {"not_dispatched": True, "restoration_pending": False})
    journal.close()
    assert Journal.foreign_has_unresolved_effects(path, "run") is True


def test_responded_provider_without_writes_releases_foreign_fence(tmp_path):
    path = _provider_journal(
        tmp_path,
        {
            "text": "done",
            "session_id": None,
            "usage": {},
            "metadata": {},
            "request": {},
            "generation": 0,
        },
        writes=[],
    )

    assert Journal.foreign_has_unresolved_effects(path, "run") is False


def test_responded_provider_with_capsuled_writes_remains_fenced(tmp_path):
    path = _provider_journal(
        tmp_path,
        {
            "text": "done",
            "session_id": None,
            "usage": {},
            "metadata": {},
            "request": {},
            "generation": 0,
        },
        writes=[{"name": "report"}],
        capsule=True,
    )

    assert Journal.foreign_has_unresolved_effects(path, "run") is True


@pytest.mark.parametrize(
    "response",
    [
        {"request": {}, "generation": 0, "unknown": True},
        {"not_dispatched": False, "request": {}, "generation": 0},
    ],
)
def test_malformed_provider_checkpoint_remains_fenced(tmp_path, response):
    path = _provider_journal(tmp_path, response, writes=[])

    assert Journal.foreign_has_unresolved_effects(path, "run") is True


def test_missing_provider_writes_declaration_remains_fenced(tmp_path):
    path = _provider_journal(
        tmp_path,
        {"request": {}, "generation": 0},
        writes=[],
    )
    journal = Journal(path)
    with journal.transaction() as db:
        db.execute(
            "UPDATE operations SET inputs=? WHERE id='op'",
            (json.dumps({"$botpipe": "dict", "value": {}}),),
        )
    journal.close()

    assert Journal.foreign_has_unresolved_effects(path, "run") is True


def test_restored_nondispatched_provider_releases_foreign_fence(tmp_path):
    path = _provider_journal(
        tmp_path,
        {
            "request": {},
            "generation": 0,
            "not_dispatched": True,
            "restoration_pending": False,
            "budget_error": "budget exhausted",
        },
        writes=[{"name": "report"}],
    )

    assert Journal.foreign_has_unresolved_effects(path, "run") is False


@pytest.mark.parametrize("writes", [[], [{"name": "report"}]])
def test_foreign_provider_reads_portable_owner_capsules(tmp_path, writes):
    from botpipe import codec

    path = _provider_journal(
        tmp_path,
        {"request": {}, "generation": 0, "text": "done"},
        writes=writes,
    )
    with codec.source_identity(tmp_path):
        inputs = codec.encode({"writes": writes}, record_owners=True)
    assert inputs["owners"]["schema"] == "botpipe.source-owners.v1"
    journal = Journal(path)
    try:
        with journal.transaction() as db:
            db.execute(
                "UPDATE operations SET inputs=? WHERE id='op'",
                (json.dumps(inputs),),
            )
    finally:
        journal.close()

    assert Journal.foreign_has_unresolved_effects(path, "run") is bool(writes)


def test_portable_owner_inspection_does_not_resolve_source(tmp_path, monkeypatch):
    from botpipe import codec
    from botpipe.read_projection import _inspection_value

    with codec.source_identity(tmp_path):
        record = codec.encode({"name": "report"}, record_owners=True)

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


def test_legacy_response_usage_is_preserved_without_dispatch_evidence():
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

    assert projection.operations[0]["usage"] == {"total_tokens": 999}
    assert "dispatches" not in projection.operations[0]
    assert projection.usage == {"total_tokens": 999}


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
