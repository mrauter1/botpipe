from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from botpipe.errors import RunBusy, WorkspaceBusy, WorkspaceUnresolved
from botpipe.journal import Journal
from botpipe.locks import run_lock, workspace_turn
from botpipe.processes import ProcessContainment
from botpipe.runtime import _async_call


def _coordination(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BOTPIPE_COORDINATION_DIR", str(tmp_path / "coordination"))


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists()


def test_v2_journal_rejects_v1_without_migrating_it(tmp_path):
    path = tmp_path / "state.sqlite3"
    db = sqlite3.connect(path)
    db.execute("PRAGMA user_version=1")
    db.execute("CREATE TABLE existing(value TEXT)")
    db.commit()
    db.close()

    with pytest.raises(ValueError, match="1.x journals"):
        Journal(path)

    db = sqlite3.connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    assert db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall() == [("existing",)]
    db.close()


def test_provider_journal_columns_retain_requested_and_adapter_evidence(tmp_path):
    journal = Journal(tmp_path / "state.sqlite3")
    try:
        journal.create_run({"run_id": "run"})
        journal.begin(
            operation_id="op",
            run_id="run",
            scope="root",
            ordinal=0,
            kind="provider",
            name="review",
            fingerprint="fingerprint",
            inputs={
                "$botpipe": "dict",
                "value": {
                    "operation": "query",
                    "policy": {"sandbox_mode": "read_only"},
                    "tools": [],
                    "settings": {},
                },
            },
            limit=10,
        )
        requested = journal.get("op")
        assert requested["preset"] == "query"
        assert requested["enforcement"]["status"] == "requested"

        journal.provider_metadata(
            "op",
            thread_id="thread",
            turn_id="turn",
            probe_hash="probe",
            enforcement={"approval_policy": "never", "sandbox": "read-only"},
        )
        recorded = journal.get("op")
        assert recorded["thread_id"] == "thread"
        assert recorded["turn_id"] == "turn"
        assert recorded["probe_hash"] == "probe"
        assert recorded["enforcement"]["approval_policy"] == "never"

        journal.fail("op", {"message": "turn failed"})
        failed = journal.get("op")
        assert failed["status"] == "failed"
        assert failed["thread_id"] == "thread"
        assert failed["enforcement"]["sandbox"] == "read-only"
    finally:
        journal.close()


def test_run_lock_is_fail_fast_and_reusable(monkeypatch, tmp_path):
    _coordination(monkeypatch, tmp_path)
    journal = tmp_path / "journal.sqlite3"

    with (
        run_lock(journal, "run-1"),
        pytest.raises(RunBusy, match="already executing"),
        run_lock(journal, "run-1"),
    ):
        pass

    with run_lock(journal, "run-1"):
        pass


def test_run_lock_is_fail_fast_across_processes(monkeypatch, tmp_path):
    _coordination(monkeypatch, tmp_path)
    journal, ready = tmp_path / "journal.sqlite3", tmp_path / "ready"
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from botpipe.locks import run_lock\n"
        "with run_lock(sys.argv[1], 'shared'):\n"
        " Path(sys.argv[2]).write_text('ready')\n"
        " sys.stdin.read(1)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(journal), str(ready)],
        stdin=subprocess.PIPE,
    )
    try:
        _wait_for(ready)
        with pytest.raises(RunBusy), run_lock(journal, "shared"):
            pass
    finally:
        assert process.stdin is not None
        process.stdin.write(b"x")
        process.stdin.flush()
        process.wait(timeout=5)


def test_unresolved_fence_blocks_other_operations_but_not_readers(
    monkeypatch, tmp_path
):
    _coordination(monkeypatch, tmp_path)
    journal = tmp_path / "journal.sqlite3"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with workspace_turn(
        workspace,
        journal=journal,
        run_id="run-1",
        operation_id="op-1",
        timeout=0,
    ) as turn:
        assert turn is not None
        turn.mark_unresolved("op-1")

    with workspace_turn(
        workspace,
        journal=journal,
        run_id="another-run",
        operation_id="op-2",
        timeout=0,
        writable=False,
    ) as reader:
        assert reader is None

    with pytest.raises(WorkspaceUnresolved, match="run-1"), workspace_turn(
        workspace,
        journal=journal,
        run_id="run-1",
        operation_id="op-2",
        timeout=0,
    ):
        pass

    with workspace_turn(
        workspace,
        journal=journal,
        run_id="run-1",
        operation_id="op-1",
        timeout=0,
    ) as owner:
        assert owner is not None and owner.clear("op-1")


def test_workspace_fence_is_shared_across_journals(monkeypatch, tmp_path):
    _coordination(monkeypatch, tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first = tmp_path / "first" / "state.sqlite3"
    second = tmp_path / "second" / "state.sqlite3"

    with workspace_turn(
        workspace,
        journal=first,
        run_id="first",
        operation_id="effect",
        timeout=0,
    ) as turn:
        assert turn is not None
        turn.mark_unresolved("effect")

    with pytest.raises(WorkspaceUnresolved, match="first"), workspace_turn(
        workspace,
        journal=second,
        run_id="second",
        operation_id="write",
        timeout=0,
    ):
        pass


def test_workspace_writer_timeout_is_bounded_across_processes(monkeypatch, tmp_path):
    _coordination(monkeypatch, tmp_path)
    workspace, ready = tmp_path / "workspace", tmp_path / "ready"
    workspace.mkdir()
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from botpipe.locks import workspace_turn\n"
        "with workspace_turn(sys.argv[1], journal=sys.argv[2], run_id='held', "
        "operation_id='held-op', timeout=0):\n"
        " Path(sys.argv[3]).write_text('ready')\n"
        " sys.stdin.read(1)\n"
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            script,
            str(workspace),
            str(tmp_path / "held.sqlite3"),
            str(ready),
        ],
        stdin=subprocess.PIPE,
    )
    try:
        _wait_for(ready)
        started = time.monotonic()
        with pytest.raises(WorkspaceBusy), workspace_turn(
            workspace,
            journal=tmp_path / "waiting.sqlite3",
            run_id="waiting",
            operation_id="waiting-op",
            timeout=0.05,
        ):
            pass
        assert time.monotonic() - started < 1
    finally:
        assert process.stdin is not None
        process.stdin.write(b"x")
        process.stdin.flush()
        process.wait(timeout=5)


def test_workspace_fence_survives_hard_process_exit(monkeypatch, tmp_path):
    _coordination(monkeypatch, tmp_path)
    workspace, ready = tmp_path / "workspace", tmp_path / "ready"
    workspace.mkdir()
    first = tmp_path / "first.sqlite3"
    script = (
        "import sys,time\n"
        "from pathlib import Path\n"
        "from botpipe.locks import workspace_turn\n"
        "with workspace_turn(sys.argv[1], journal=sys.argv[2], run_id='crashed', "
        "operation_id='effect', timeout=0) as turn:\n"
        " turn.mark_unresolved('effect')\n"
        " Path(sys.argv[3]).write_text('ready')\n"
        " time.sleep(60)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(workspace), str(first), str(ready)]
    )
    try:
        _wait_for(ready)
        process.kill()
        process.wait(timeout=5)
        with pytest.raises(WorkspaceUnresolved, match="crashed"), workspace_turn(
            workspace,
            journal=tmp_path / "second.sqlite3",
            run_id="second",
            operation_id="write",
            timeout=0.2,
        ):
            pass
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_process_containment_cleans_up_descendants_after_leader_exit(tmp_path):
    marker = tmp_path / "escaped"
    child = (
        "import time\n"
        "from pathlib import Path\n"
        "time.sleep(0.5)\n"
        f"Path({str(marker)!r}).write_text('escaped')\n"
    )
    parent = (
        "import subprocess,sys\n"
        f"subprocess.Popen([sys.executable, '-c', {child!r}])\n"
    )
    containment = ProcessContainment.create()
    process = subprocess.Popen(
        [sys.executable, "-c", parent], **containment.creation_kwargs
    )
    try:
        containment.attach_and_start(process)
        process.wait(timeout=5)
        containment.ensure_tree_exited(process, grace_seconds=0.05)
        time.sleep(0.6)
        assert not marker.exists()
    finally:
        if process.poll() is None:
            containment.terminate(process, grace_seconds=0)
        containment.close()


@pytest.mark.asyncio
async def test_async_cancellation_joins_worker_cleanup_under_repeated_cancel():
    import asyncio

    started, release, finished = (threading.Event() for _ in range(3))

    def worker():
        started.set()
        release.wait()
        finished.set()

    task = asyncio.create_task(_async_call(worker))
    await asyncio.to_thread(started.wait)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    asyncio.get_running_loop().call_later(0.05, release.set)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


@pytest.mark.asyncio
async def test_outer_cancellation_reaches_nested_provider_worker(tmp_path):
    import asyncio

    from botpipe import Botpipe, Provider, workflow
    from botpipe.providers import FakeProvider, ProviderInterruptedError

    entered, cleaned = threading.Event(), threading.Event()

    def blocking(request):
        entered.set()
        deadline = time.monotonic() + 5
        while not request.cancel_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert request.cancel_event.is_set()
        cleaned.set()
        raise ProviderInterruptedError("cancelled after cleanup", process_alive=False)

    @workflow
    async def work():
        await Provider().arun("wait")

    with Botpipe(tmp_path, provider=FakeProvider([blocking])) as client:
        task = asyncio.create_task(client.arun(work))
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert cleaned.is_set()


@pytest.mark.parametrize("mutate_after_accept", [False, True])
def test_accept_inventories_current_declared_outputs(
    tmp_path, monkeypatch, mutate_after_accept
):
    from botpipe import Artifact, Botpipe, Provider, workflow
    from botpipe.artifacts import ArtifactStore
    from botpipe.providers import FakeProvider

    destination = tmp_path / "accepted.txt"

    def write(request):
        next(iter(request.artifacts.values())).write_text(
            "accepted", encoding="utf-8"
        )
        return "done"

    @workflow
    def work():
        return Provider().run(
            "write", writes=[Artifact.text(destination, required=True)]
        )

    original_capture = ArtifactStore.capture
    monkeypatch.setattr(
        ArtifactStore,
        "capture",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            KeyboardInterrupt("before capture inventory")
        ),
    )
    with Botpipe(tmp_path, provider=FakeProvider([write])) as client:
        first = client.run(work, run_id=f"accept-{mutate_after_accept}")
        assert first.status == "interrupted"
        monkeypatch.setattr(ArtifactStore, "capture", original_capture)

        operation = next(
            row
            for row in client.journal.operations(first.run_id)
            if row["kind"] == "provider"
        )
        client.resolve(first.run_id, operation["id"], accept=True)
        saved = client.journal.get(operation["id"])["response"]
        assert saved["artifact_resolution"] == {
            "source": "operator",
            "digests": {
                "accepted": hashlib.sha256(b"accepted").hexdigest(),
            },
        }

        if mutate_after_accept:
            destination.write_text("changed", encoding="utf-8")
        resumed = client.resume(first.run_id, workflow=work)
        assert resumed.ok, resumed.error
        assert resumed.value.artifacts.accepted.read_text() == "accepted"


@pytest.mark.parametrize("outcome", ["stopped", "unknown", "running"])
def test_accept_unresolved_turn_adopts_workspace_and_keeps_thread(tmp_path, outcome):
    from botpipe import Artifact, Botpipe, BotpipeError, Provider, workflow
    from botpipe.providers import FakeProvider
    from botpipe.recovery import Running, Stopped, Unknown

    destination = tmp_path / "accepted.txt"

    def interrupted(request):
        destination.write_text("partial result", encoding="utf-8")
        raise SystemExit("lost terminal response")

    class InterruptedProvider(FakeProvider):
        def recover(self, request):
            return {"stopped": Stopped(), "unknown": Unknown(), "running": Running()}[
                outcome
            ]

    @workflow
    def work():
        return Provider().run("write", writes=[Artifact.text(destination, required=True)])

    provider = InterruptedProvider([interrupted])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="accept-unresolved")
        operation = next(
            row for row in client.journal.operations("accept-unresolved")
            if row["kind"] == "provider"
        )
        client.journal.provider_metadata(operation["id"], thread_id="accepted-thread")
        if outcome == "running":
            with pytest.raises(BotpipeError, match="still running"):
                client.resolve("accept-unresolved", operation["id"], accept=True)
            with pytest.raises(WorkspaceUnresolved), client.workspace_turn(
                run_id="other-run", operation_id="other-operation", timeout=0
            ):
                pass
            return

        client.resolve("accept-unresolved", operation["id"], accept=True)
        saved = client.journal.get(operation["id"])["response"]
        assert saved["session_id"] == "accepted-thread"
        assert saved["metadata"]["operator_accepted"] is True
        destination.write_text("later writer", encoding="utf-8")
        resumed = client.resume("accept-unresolved", workflow=work)
        assert resumed.ok, resumed.error
        assert resumed.value.value == ""
        assert resumed.value.artifacts.accepted.read_text() == "partial result"
        assert len(provider.calls) == 1


@pytest.mark.parametrize("sandbox", ["workspace-write", "read-only"])
def test_accept_typed_unresolved_turn_requires_valid_response(tmp_path, sandbox):
    from botpipe import Botpipe, Provider, workflow
    from botpipe.providers import FakeProvider, ProviderResponse
    from botpipe.recovery import Unknown

    locked_recoveries = []

    class InterruptedProvider(FakeProvider):
        def recover(self, request):
            with pytest.raises(WorkspaceBusy), client.workspace_turn(
                run_id="other-run", operation_id="other-operation", timeout=0
            ):
                pass
            locked_recoveries.append(request.operation_id)
            return Unknown()

    @workflow
    def work():
        return Provider().run("count", returns=int, sandbox=sandbox)

    provider = InterruptedProvider([SystemExit("lost terminal response")])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="accept-typed")
        operation = next(
            row for row in client.journal.operations("accept-typed")
            if row["kind"] == "provider"
        )
        before = operation["response"]
        with pytest.raises(ValueError, match="requires a response"):
            client.resolve("accept-typed", operation["id"], accept=True)
        with pytest.raises(ValueError, match="does not match the output schema"):
            client.resolve(
                "accept-typed", operation["id"], accept=True,
                response=ProviderResponse('"invalid"'),
            )
        assert client.journal.get(operation["id"])["response"] == before
        client.resolve(
            "accept-typed", operation["id"], accept=True, response=ProviderResponse("7")
        )
        assert locked_recoveries == [operation["id"]] * 3
        resumed = client.resume("accept-typed", workflow=work)
        assert resumed.ok, resumed.error
        assert resumed.value.value == 7
        assert len(provider.calls) == 1


def test_accept_checkpoints_selection_before_capture(tmp_path, monkeypatch):
    from botpipe import Artifact, Botpipe, Provider, workflow
    from botpipe.artifacts import ArtifactStore
    from botpipe.providers import FakeProvider

    destination = tmp_path / "accepted.txt"

    def interrupted(request):
        destination.write_text("accepted", encoding="utf-8")
        raise SystemExit("lost terminal response")

    @workflow
    def work():
        return Provider().run(
            "write", writes=[Artifact.text(destination, required=True)]
        )

    with Botpipe(tmp_path, provider=FakeProvider([interrupted])) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="accept-crash")
        operation = next(
            row for row in client.journal.operations("accept-crash")
            if row["kind"] == "provider"
        )
        capture = ArtifactStore.capture

        def crash(*args, **kwargs):
            saved = client.journal.get(operation["id"])["response"]
            assert saved["artifact_resolution"]["digests"] == {
                "accepted": hashlib.sha256(b"accepted").hexdigest()
            }
            with pytest.raises(WorkspaceBusy), client.workspace_turn(
                run_id="other-run", operation_id="other-operation", timeout=0
            ):
                pass
            raise SystemExit("before capture")

        monkeypatch.setattr(ArtifactStore, "capture", crash)
        with pytest.raises(SystemExit, match="before capture"):
            client.resolve("accept-crash", operation["id"], accept=True)
        with pytest.raises(WorkspaceUnresolved), client.workspace_turn(
            run_id="other-run", operation_id="other-operation", timeout=0
        ):
            pass
        monkeypatch.setattr(ArtifactStore, "capture", capture)
        resumed = client.resume("accept-crash", workflow=work)
        assert resumed.ok, resumed.error
        assert resumed.value.artifacts.accepted.read_text() == "accepted"


def test_fail_resolution_replays_fence_cleanup_after_hard_crash(tmp_path, monkeypatch):
    from botpipe import Botpipe, Provider, workflow
    from botpipe.providers import FakeProvider

    @workflow
    def work():
        return Provider().run("write")

    with Botpipe(
        tmp_path, provider=FakeProvider([SystemExit("lost after dispatch")])
    ) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="fail-cleanup")
        operation = next(
            row
            for row in client.journal.operations("fail-cleanup")
            if row["kind"] == "provider"
        )

        clear = client.clear_workspace_fence
        monkeypatch.setattr(
            client,
            "clear_workspace_fence",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                SystemExit("crash before fence cleanup")
            ),
        )
        with pytest.raises(SystemExit, match="fence cleanup"):
            client.resolve("fail-cleanup", operation["id"], fail=True)
        assert client.journal.get(operation["id"])["status"] == "failed"

        monkeypatch.setattr(client, "clear_workspace_fence", clear)
        client.resolve("fail-cleanup", operation["id"], fail=True)
        with client.workspace_turn(
            run_id="another-run", operation_id="another-operation", timeout=0
        ):
            pass


@pytest.mark.parametrize("preset", ["query", "generate"])
@pytest.mark.parametrize("resolution", ["retry", "accept", "fail"])
def test_read_only_resolution_ignores_unrelated_writer_fence(
    tmp_path, monkeypatch, preset, resolution
):
    from botpipe import Botpipe, Provider, workflow
    from botpipe.providers import FakeProvider

    _coordination(monkeypatch, tmp_path)

    @workflow
    def writer():
        return Provider(session=None).run("write")

    @workflow
    def reader():
        provider = Provider(session=None)
        return getattr(provider, preset)("read")

    provider = FakeProvider(
        [SystemExit("writer interrupted"), SystemExit("reader interrupted")]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit, match="writer interrupted"):
            client.run(writer, run_id="fenced-writer")
        with pytest.raises(SystemExit, match="reader interrupted"):
            client.run(reader, run_id=f"{preset}-{resolution}")

        operation = next(
            row
            for row in client.journal.operations(f"{preset}-{resolution}")
            if row["kind"] == "provider"
        )
        client.resolve(
            f"{preset}-{resolution}",
            operation["id"],
            **{resolution: True},
        )

        resolved = client.journal.get(operation["id"])
        if resolution == "retry":
            assert resolved["response"]["retry_authorized"] is True
        elif resolution == "accept":
            assert resolved["response"]["metadata"]["operator_accepted"] is True
        else:
            assert resolved["status"] == "failed"

        with pytest.raises(WorkspaceUnresolved, match="fenced-writer"):
            with client.workspace_turn(
                run_id="another-writer",
                operation_id="another-operation",
                timeout=0,
            ):
                pass
