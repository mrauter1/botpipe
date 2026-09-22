"""Read/write ownership through the public runtime, across overlapping roots."""

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from botpipe import (
    Botpipe,
    Policy,
    Provider,
    RunBusy,
    UncertainOperation,
    parallel,
    workflow,
)
from botpipe.providers import FakeProvider, ProviderResponse
from botpipe.recovery import Completed, Stopped


@pytest.fixture(autouse=True)
def coordinator_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "botpipe.workspace_ownership.user_state_dir",
        lambda: tmp_path / "coordinator",
    )


@pytest.mark.parametrize("reader_first", [False, True])
def test_parent_writer_and_child_reader_exclude_each_other(tmp_path, reader_first):
    parent = tmp_path / "workspace"
    child = parent / "child"
    child.mkdir(parents=True)
    entered, release = threading.Event(), threading.Event()

    def held(request):
        entered.set()
        assert release.wait(5)
        return "finished"

    @workflow
    def read():
        return Provider().query("read child").value

    @workflow
    def write():
        return Provider().run("edit parent").value

    first_root, second_root = (child, parent) if reader_first else (parent, child)
    first_work, second_work = (read, write) if reader_first else (write, read)
    blocked = FakeProvider(["must not dispatch"])
    with (
        Botpipe(first_root, state_dir=tmp_path / "first-state", provider=FakeProvider([held])) as first,
        Botpipe(second_root, state_dir=tmp_path / "second-state", provider=blocked) as second,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        running = pool.submit(first.run, first_work)
        try:
            assert entered.wait(5)
            with pytest.raises(RunBusy):
                second.run(second_work)
            assert not blocked.calls
        finally:
            release.set()
            assert running.result(timeout=5).ok


def test_unresolved_parent_output_is_not_observable_by_child_query(tmp_path):
    parent = tmp_path / "workspace"
    child = parent / "child"
    child.mkdir(parents=True)
    value = child / "value.txt"

    def interrupted(request):
        value.write_text("uncommitted output")
        raise RuntimeError("native result unavailable")

    @workflow
    def write():
        return Provider().run("edit").value

    @workflow
    def read():
        return Provider().query("inspect").value

    reader = FakeProvider([lambda request: value.read_text()])
    with (
        Botpipe(parent, state_dir=tmp_path / "writer-state", provider=FakeProvider([interrupted])) as writer,
        Botpipe(child, state_dir=tmp_path / "reader-state", provider=reader) as observer,
    ):
        result = writer.run(write)
        assert result.status == "interrupted"
        with pytest.raises(RunBusy, match="unresolved"):
            observer.run(read)
        assert not reader.calls
        operation = next(row for row in writer.journal.operations(result.run_id) if row["kind"] == "provider")
        writer.provider.recover = lambda request: Stopped("verified stopped")
        writer.resolve(result.run_id, operation["id"], response=ProviderResponse("reconciled"))
        observed = observer.run(read)
        assert observed.ok, observed.error
        assert observed.value == "uncommitted output"


def test_independent_queries_can_share_an_alternate_read_root(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    origins = [tmp_path / "first", tmp_path / "second"]
    for origin in origins:
        origin.mkdir()
    both = threading.Barrier(2)

    def read(request):
        both.wait(timeout=5)
        return "read"

    @workflow
    def query():
        return Provider().query("inspect", workspace=shared).value

    with (
        Botpipe(origins[0], provider=FakeProvider([read])) as first,
        Botpipe(origins[1], provider=FakeProvider([read])) as second,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        results = [pool.submit(client.run, query) for client in (first, second)]
        for future in results:
            result = future.result(timeout=8)
            assert result.ok, result.error


@pytest.mark.parametrize("primary_target", [False, True])
def test_parallel_writer_cannot_overlap_sibling_target(tmp_path, primary_target):
    origin = tmp_path / "origin"
    target = tmp_path / "target"
    child = target / "child"
    origin.mkdir()
    child.mkdir(parents=True)
    entered, attempted = threading.Event(), threading.Event()

    def edit(request):
        assert request.workspace == target
        entered.set()
        assert attempted.wait(5)
        return "edited"

    @workflow
    def work():
        def parent_branch():
            provider = Provider()
            call = provider.query if primary_target else provider.run
            return call("parent", workspace=target).value

        def child_branch():
            assert entered.wait(5)
            try:
                return Provider().run("child", workspace=child).value
            finally:
                attempted.set()

        return parallel(parent_branch, child_branch, settle="collect")

    adapter = FakeProvider([edit])
    with Botpipe(target if primary_target else origin, provider=adapter) as client:
        result = client.run(work)
    assert result.ok, result.error
    assert result.value[0] == "edited"
    assert result.value[1]["type"] == "RunBusy"
    assert len(adapter.calls) == 1


def test_runtime_does_not_write_lock_files_into_read_only_workspace(tmp_path):
    workspace = tmp_path / "read-only"
    workspace.mkdir()
    workspace.chmod(0o555)

    @workflow
    def read():
        return Provider().query("inspect").value

    try:
        with Botpipe(workspace, state_dir=tmp_path / "state", provider=FakeProvider(["read"])) as client:
            result = client.run(read)
        assert result.ok, result.error
        assert list(workspace.iterdir()) == []
    finally:
        workspace.chmod(0o755)


def test_dynamic_read_claim_blocks_new_ancestor_writer_without_markers(tmp_path):
    origin = tmp_path / "reader-origin"
    parent = tmp_path / "observed"
    child = parent / "child"
    origin.mkdir()
    child.mkdir(parents=True)
    entered, release = threading.Event(), threading.Event()

    def inspect(request):
        with request.read_fence(child):
            entered.set()
            assert release.wait(5)
            return "read"

    @workflow
    def read():
        return Provider().query("inspect").value

    @workflow
    def write():
        return Provider().run("edit parent").value

    blocked = FakeProvider(["must not dispatch"])
    with (
        Botpipe(origin, provider=FakeProvider([inspect])) as reader,
        Botpipe(parent, state_dir=tmp_path / "writer-state", provider=blocked) as writer,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        running = pool.submit(reader.run, read)
        try:
            assert entered.wait(5)
            with pytest.raises(RunBusy):
                writer.run(write)
            assert not blocked.calls
            assert writer.journal.runs() == []
        finally:
            release.set()
            assert running.result(timeout=5).ok


@pytest.mark.parametrize("action", ["resume", "resolve"])
def test_unknown_recovery_does_not_leave_a_workspace_claim(tmp_path, action):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    @workflow
    def work():
        return "finished"

    with Botpipe(
        workspace, state_dir=tmp_path / "state", provider=FakeProvider([])
    ) as client:
        with pytest.raises(KeyError, match="Unknown run missing"):
            if action == "resume":
                client.resume("missing", workflow=work)
            else:
                client.resolve(
                    "missing",
                    "missing:root:0",
                    response=ProviderResponse("unused"),
                )

        result = client.run(work, run_id="fresh")
        assert result.ok, result.error


def test_saved_uncertainty_precedes_a_later_overlapping_claim(tmp_path):
    origin = tmp_path / "origin"
    target = tmp_path / "target"
    child = target / "child"
    origin.mkdir()
    child.mkdir(parents=True)

    def uncertain(request):
        raise RuntimeError("original outcome is unknown")

    shared = Provider(session=None)

    @workflow
    def work():
        try:
            shared.run("edit parent", workspace=target)
        except UncertainOperation:
            pass
        try:
            shared.query("read child", workspace=child)
        except UncertainOperation:
            pass
        return "must remain interrupted"

    adapter = FakeProvider([uncertain])
    with Botpipe(origin, provider=adapter) as client:
        result = client.run(work, run_id="uncertain-parent")

    assert result.status == "interrupted"
    assert result.error == "original outcome is unknown"
    assert len(adapter.calls) == 1


def test_child_root_can_read_an_authorized_ancestor(tmp_path):
    parent = tmp_path / "workspace"
    child = parent / "child"
    child.mkdir(parents=True)
    (parent / "shared.txt").write_text("shared context")

    def inspect(request):
        with request.read_fence(parent):
            return (parent / "shared.txt").read_text()

    @workflow
    def work():
        return Provider(policy=Policy(allow_read=(str(parent),))).query("inspect").value

    with Botpipe(child, provider=FakeProvider([inspect])) as client:
        result = client.run(work)
    assert result.ok, result.error
    assert result.value == "shared context"


def test_child_root_recovers_ancestor_writer_without_releasing_other_fences(tmp_path):
    parent = tmp_path / "workspace"
    child = parent / "child"
    sibling = parent / "sibling"
    child.mkdir(parents=True)
    sibling.mkdir()

    @workflow
    def work():
        return Provider().run("edit parent", workspace=parent).value

    @workflow
    def read():
        return Provider().query("inspect sibling").value

    adapter = FakeProvider([RuntimeError("unknown native result")])
    with (
        Botpipe(child, state_dir=tmp_path / "writer-state", provider=adapter) as writer,
        Botpipe(sibling, state_dir=tmp_path / "reader-state", provider=FakeProvider(["read"])) as reader,
    ):
        interrupted = writer.run(work)
        assert interrupted.status == "interrupted"
        operation = next(row for row in writer.journal.operations(interrupted.run_id) if row["kind"] == "provider")
        with pytest.raises(RunBusy):
            reader.run(read)
        # Root orchestration can resume, but cannot grant a sibling operation
        # the interrupted writer's workspace merely because the run ID matches.
        with writer._ownership(interrupted.run_id, recovery=True) as root:
            with pytest.raises(RunBusy):
                with writer._ownership(
                    interrupted.run_id, workspace=sibling, parent=(root,),
                    recovery=True, operation_id="different-operation",
                ):
                    pytest.fail("another operation acquired unresolved output")

        def recovered(request):
            assert request.operation_id == operation["id"]
            with pytest.raises(RunBusy):
                reader.run(read)
            return Completed(ProviderResponse("recovered"))

        adapter.recover = recovered
        resumed = writer.resume(interrupted.run_id, workflow=work)
        assert resumed.ok, resumed.error
        assert resumed.value == "recovered"
        assert len(adapter.calls) == 1
        assert reader.run(read).ok
