from __future__ import annotations

import json

import pytest

from botpipe import codec
from botpipe.journal import Journal


def run_record(run_id="run", task_id="task"):
    return {
        "run_id": run_id,
        "task_id": task_id,
        "workflow": "work",
        "args": {"$botpipe": "tuple", "value": [1]},
        "kwargs": {"$botpipe": "dict", "value": {"label": "plain"}},
        "status": "created",
        "created_at": "2026-09-24T00:00:00+00:00",
    }


def begin(journal, run_id="run", operation_id="op", kind="activity"):
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


def ledger(root, run_id="run", task_id="task"):
    return root / "tasks" / task_id / "runs" / run_id / "ledger.jsonl"


def test_run_starts_with_readable_input_reference_and_exact_fold(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run({**run_record(), "request_text": "Please do the work.\n"})

    first = json.loads(ledger(tmp_path).read_text().splitlines()[0])
    assert first["seq"] == 1
    assert first["event"] == "run_created"
    assert first["data"]["format_version"] == 1
    assert first["data"]["input"]["path"] == "input.json"
    assert first["data"]["request"]["path"] == "request.md"
    assert (ledger(tmp_path).parent / "request.md").read_text() == (
        "Please do the work.\n"
    )
    assert "request_text" not in first["data"]["run"]
    assert json.loads((ledger(tmp_path).parent / "input.json").read_text()) == {
        "args": {"$botpipe": "tuple", "value": [1]},
        "kwargs": {"$botpipe": "dict", "value": {"label": "plain"}},
    }
    assert journal.run("run")["args"]["value"] == [1]


def test_run_ids_are_unique_across_tasks_and_ambiguous_history_is_rejected(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record(task_id="first"))
    with pytest.raises(ValueError, match="already exists"):
        journal.create_run(run_record(task_id="second"))

    source = ledger(tmp_path, task_id="first").parent
    duplicate = tmp_path / "tasks" / "second" / "runs" / "run"
    duplicate.mkdir(parents=True)
    for name in ("input.json", "ledger.jsonl"):
        (duplicate / name).write_bytes((source / name).read_bytes())
    with pytest.raises(ValueError, match="Ambiguous run"):
        Journal.read_only_snapshot(tmp_path, "run")


def test_append_handles_short_writes_without_rereading_whole_ledger(
    tmp_path, monkeypatch
):
    import botpipe.journal as journal_module

    journal = Journal(tmp_path)
    journal.create_run(run_record())
    original_write = journal_module.os.write
    monkeypatch.setattr(
        journal_module.os,
        "write",
        lambda descriptor, content: original_write(descriptor, content[:7]),
    )
    monkeypatch.setattr(
        journal,
        "_read_path",
        lambda *_args, **_kwargs: pytest.fail("append reread the ledger"),
    )

    begin(journal)
    journal.finish("op", {"$botpipe": "str", "value": "done"})

    fresh = Journal.read_only_snapshot(tmp_path, "run")
    assert fresh.operations[0]["status"] == "completed"


def test_ambiguous_append_requires_successful_resync(tmp_path, monkeypatch):
    import botpipe.journal as journal_module

    journal = Journal(tmp_path)
    journal.create_run(run_record())
    real_fsync = journal_module.os.fsync
    calls = 0

    def fail_once(descriptor):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("ack lost")
        return real_fsync(descriptor)

    monkeypatch.setattr(journal_module.os, "fsync", fail_once)
    journal.event("run", "segment_started")
    assert journal.events("run")[-1]["event"] == "segment_started"
    assert calls >= 2


def test_failed_resync_poison_stops_later_effects(tmp_path, monkeypatch):
    import botpipe.journal as journal_module

    journal = Journal(tmp_path)
    journal.create_run(run_record())
    begin(journal)
    monkeypatch.setattr(
        journal_module.os,
        "fsync",
        lambda _descriptor: (_ for _ in ()).throw(OSError("disk")),
    )
    with pytest.raises(OSError, match="disk"):
        journal.event("run", "will_not_be_acknowledged")
    monkeypatch.undo()
    begin_record = Journal(tmp_path)
    # A fresh reader may observe bytes, but the writer that lost its durable
    # acknowledgement must never upgrade them to a confirmed checkpoint.
    assert begin_record.snapshot("run").last_seq == 3
    with pytest.raises(RuntimeError, match="not confirmed"):
        journal.confirmed("op")
    with pytest.raises(RuntimeError, match="unusable"):
        journal.event("run", "must_not_append")


def test_readers_ignore_tail_and_reopened_writer_reports_repair(tmp_path):
    first = Journal(tmp_path)
    first.create_run(run_record())
    path = ledger(tmp_path)
    with path.open("ab") as stream:
        stream.write(b'{"seq":2')

    assert Journal.read_only_snapshot(tmp_path, "run").last_seq == 1
    reopened = Journal(tmp_path)
    reopened.event("run", "segment_started")
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert [record["event"] for record in records] == [
        "run_created",
        "ledger_tail_repaired",
        "segment_started",
    ]


def test_complete_corruption_and_missing_payload_fail_with_context(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    path = ledger(tmp_path)
    with path.open("a") as stream:
        stream.write(
            '{"seq":3,"at":"2026-09-24T00:00:01+00:00",'
            '"event":"run_updated","run_id":"run","data":{}}\n'
        )
    with pytest.raises(ValueError, match="sequence 3.*sequence gap"):
        Journal.read_only_snapshot(tmp_path, "run")

    other = tmp_path / "other"
    journal = Journal(other)
    journal.create_run(run_record())
    (ledger(other).parent / "input.json").unlink()
    with pytest.raises(ValueError, match="Missing journal payload"):
        Journal.read_only_snapshot(other, "run")


def test_large_result_uses_digest_checked_sidecar(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    begin(journal)
    result = {"$botpipe": "str", "value": "x" * 9000}
    journal.finish("op", result)

    completed = json.loads(ledger(tmp_path).read_text().splitlines()[-1])
    reference = completed["data"]["result"]["$ledger_payload"]
    payload = ledger(tmp_path).parent / reference["path"]
    assert payload.is_file()
    assert journal.get("op")["result"] == result

    payload.write_text("tampered")
    with pytest.raises(ValueError, match="payload (size|digest) mismatch"):
        Journal.read_only_snapshot(tmp_path, "run")


def test_large_workflow_result_uses_sidecar_without_bloating_listing(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    value = {"$botpipe": "str", "value": "x" * 9000}
    journal.update_run("run", status="completed", value=value)

    updated = json.loads(ledger(tmp_path).read_text().splitlines()[-1])
    assert set(updated["data"]["value"]) == {"$ledger_payload"}
    assert journal.run("run")["value"] == value
    assert journal.runs()[0]["value"] == updated["data"]["value"]


def test_attempt_files_are_immutable_and_dispatch_reservation_folds(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    begin(journal, kind="provider")
    request = {"prompt": "exact prompt\n", "policy": {"sandbox": "read-only"}}
    prepared = journal.prepare_attempt("op", 1, request)
    assert prepared == journal.prepare_attempt("op", 1, request)

    journal.reserve_budgets(
        "run",
        "op",
        [],
        1.0,
        {},
        30.0,
        {"dispatch_id": "dispatch", "attempt": 1, "provider": "fake"},
    )
    journal.attempt_checkpoint(
        "op",
        1,
        {
            "status": "completed",
            "response": {
                "text": "exact response\n",
                "session_id": "thread",
                "metadata": {"turn_id": "turn"},
            },
        },
    )

    attempt = journal.attempt("op", 1)
    assert attempt["dispatch_authorized"] is True
    assert attempt["status"] == "completed"
    directory = ledger(tmp_path).parent / "operations" / "op" / "attempts" / "1"
    assert (directory / "prompt.md").read_text() == "exact prompt\n"
    assert (directory / "response.md").read_text() == "exact response\n"
    assert "prompt" not in json.loads((directory / "request.json").read_text())
    assert "exact response" not in ledger(tmp_path).read_text()
    assert journal.get("op")["thread_id"] == "thread"
    assert journal.get("op")["turn_id"] == "turn"

    with pytest.raises(ValueError, match="differs"):
        journal.prepare_attempt("op", 1, {**request, "prompt": "different"})


def test_interrupted_sidecar_publish_never_leaves_a_partial_final_file(
    tmp_path, monkeypatch
):
    import botpipe.journal as journal_module

    journal = Journal(tmp_path)
    journal.create_run(run_record())
    begin(journal, kind="provider")
    real_write = journal_module.os.write
    calls = 0

    def partial_then_crash(descriptor, content):
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(descriptor, content[:3])
        raise OSError("process lost")

    monkeypatch.setattr(journal_module.os, "write", partial_then_crash)
    with pytest.raises(OSError, match="process lost"):
        journal.prepare_attempt("op", 1, {"prompt": "complete prompt"})
    attempt_dir = ledger(tmp_path).parent / "operations" / "op" / "attempts" / "1"
    assert not (attempt_dir / "prompt.md").exists()

    monkeypatch.undo()
    journal.prepare_attempt("op", 1, {"prompt": "complete prompt"})
    assert (attempt_dir / "prompt.md").read_text() == "complete prompt"


def test_run_owned_reference_cannot_escape_through_symlink(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    run_dir = ledger(tmp_path).parent
    outside = tmp_path / "outside.json"
    outside.write_bytes((run_dir / "input.json").read_bytes())
    (run_dir / "input.json").unlink()
    (run_dir / "input.json").symlink_to(outside)

    with pytest.raises(ValueError, match="escapes its run directory"):
        Journal.read_only_snapshot(tmp_path, "run")


def test_unreferenced_attempt_files_do_not_pin_a_later_preparation(
    tmp_path, monkeypatch
):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    begin(journal, kind="provider")
    append = journal._append_locked

    def lose_attempt_record(run_id, event, data, operation_id=None):
        if event == "attempt_prepared":
            raise OSError("ledger unavailable")
        return append(run_id, event, data, operation_id)

    monkeypatch.setattr(journal, "_append_locked", lose_attempt_record)
    with pytest.raises(OSError, match="ledger unavailable"):
        journal.prepare_attempt("op", 1, {"prompt": "orphaned"})
    monkeypatch.setattr(journal, "_append_locked", append)

    journal.prepare_attempt("op", 1, {"prompt": "authoritative"})
    directory = ledger(tmp_path).parent / "operations" / "op" / "attempts" / "1"
    assert (directory / "prompt.md").read_text() == "authoritative"


def test_run_listing_folds_status_without_opening_input_payload(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    journal.update_run("run", status="completed")
    (ledger(tmp_path).parent / "input.json").unlink()

    assert journal.runs()[0]["status"] == "completed"


def test_returned_values_cannot_mutate_cached_authority(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    begin(journal)
    before = journal.get("op")["inputs"]

    journal.get("op")["inputs"]["value"]["injected"] = True
    journal.run("run")["kwargs"]["value"]["injected"] = True
    journal.events("run")[1]["data"]["operation"]["name"] = "changed"

    assert journal.get("op")["inputs"] == before
    assert "injected" not in journal.run("run")["kwargs"]["value"]
    assert journal.events("run")[1]["data"]["operation"]["name"] == "effect"


def test_ledger_identity_must_match_task_and_run_path(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record(run_id="a"))
    source = ledger(tmp_path, run_id="a").parent
    copied = tmp_path / "tasks" / "task" / "runs" / "b"
    copied.mkdir()
    for name in ("input.json", "ledger.jsonl"):
        (copied / name).write_bytes((source / name).read_bytes())

    with pytest.raises(ValueError, match="task/run path"):
        Journal.read_only_snapshot(tmp_path, "b")


def test_cached_writer_refreshes_after_another_process_appends(tmp_path):
    first = Journal(tmp_path)
    first.create_run(run_record())
    second = Journal(tmp_path)
    second.update_run("run", status="running")
    first.update_run("run", status="failed")

    snapshot = Journal.read_only_snapshot(tmp_path, "run")
    assert snapshot.last_seq == 3
    assert snapshot.run["status"] == "failed"


def test_terminal_attempt_cannot_regress_and_invalid_update_is_not_appended(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    begin(journal, kind="provider")
    journal.prepare_attempt("op", 1, {"prompt": "prompt"})
    journal.attempt_checkpoint(
        "op", 1, {"status": "completed", "response": {"text": "done"}}
    )
    before = ledger(tmp_path).read_bytes()

    with pytest.raises(ValueError, match="invalid attempt status"):
        journal.attempt_checkpoint("op", 1, {"status": "prepared"})
    assert ledger(tmp_path).read_bytes() == before


def test_missing_attempt_file_fails_selected_run_read(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    begin(journal, kind="provider")
    journal.prepare_attempt("op", 1, {"prompt": "prompt"})
    directory = ledger(tmp_path).parent / "operations" / "op" / "attempts" / "1"
    (directory / "prompt.md").unlink()

    with pytest.raises(ValueError, match="Missing journal payload"):
        Journal.read_only_snapshot(tmp_path, "run")


def test_user_mapping_keys_cannot_collide_with_ledger_reference_tags(tmp_path):
    journal = Journal(tmp_path)
    journal.create_run(run_record())
    value = {
        "nested": {
            "$ledger_payload": {"path": "ordinary user data"},
            "$ledger_text": {"path": "also ordinary"},
        }
    }
    encoded = codec.encode(value)
    journal.begin(
        operation_id="op",
        run_id="run",
        scope="root",
        ordinal=0,
        kind="activity",
        name="effect",
        fingerprint="fingerprint",
        inputs=encoded,
        limit=10,
    )
    journal.finish("op", encoded)

    fresh = Journal.read_only_snapshot(tmp_path, "run")
    assert codec.decode(fresh.operations[0]["inputs"]) == value
    assert codec.decode(fresh.operations[0]["result"]) == value

    provider = Journal(tmp_path / "provider")
    provider.create_run(run_record())
    begin(provider, kind="provider")
    provider.prepare_attempt("op", 1, {"prompt": "prompt"})
    literal = {"$ledger_payload": {"path": "ordinary user data"}}
    provider.attempt_checkpoint("op", 1, {"audit": literal})
    assert provider.attempt("op", 1)["audit"] == literal

    journal.event("run", "user_fact", literal)
    assert journal.events("run")[-1]["data"] == literal
