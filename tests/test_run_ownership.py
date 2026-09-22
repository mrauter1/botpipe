"""One durable run has one executor, independently of workspace ownership."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from botpipe import Botpipe, BotpipeError, Provider, RunBusy, UncertainOperation
from botpipe.providers import FakeProvider, ProviderResponse
from botpipe.recovery import Completed, Stopped
from botpipe.workspace_ownership import WorkspaceCoordinator


@pytest.fixture(autouse=True)
def coordinator_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "botpipe.workspace_ownership.user_state_dir",
        lambda: tmp_path / "coordinator",
    )


def _interrupted_query(workspace, state_dir):
    provider = FakeProvider([KeyboardInterrupt()])
    with Botpipe(workspace, state_dir=state_dir, provider=provider) as client:
        with pytest.raises((BotpipeError, UncertainOperation)) as raised:
            Provider(runtime=client, session=None).query("inspect")
        run_id = raised.value.run_id
        operation_id = raised.value.operation_id
    return run_id, operation_id


def test_execution_guard_excludes_another_process(tmp_path):
    registry = tmp_path / "coordinator"
    journal = tmp_path / "state.sqlite3"
    ready = tmp_path / "ready"
    release = tmp_path / "release"
    repository = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(repository)
    script = """
import pathlib
import sys
import time
from botpipe.workspace_ownership import WorkspaceCoordinator

registry, journal, ready, release = map(pathlib.Path, sys.argv[1:])
with WorkspaceCoordinator(registry).execution_guard(journal, "run"):
    ready.write_text("ready")
    deadline = time.monotonic() + 10
    while not release.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("parent did not release execution guard")
        time.sleep(0.01)
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            script,
            str(registry),
            str(journal),
            str(ready),
            str(release),
        ],
        cwd=repository,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stderr = ""
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and process.poll() is None:
            if time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        if not ready.exists():
            _stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"guard child did not start: {stderr}")
        coordinator = WorkspaceCoordinator(registry)
        with pytest.raises(RunBusy):
            with coordinator.execution_guard(journal, "run"):
                pass
    finally:
        release.write_text("release")
        try:
            _stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            _stdout, stderr = process.communicate(timeout=5)
            raise
    assert process.returncode == 0, stderr


def test_concurrent_resolves_admit_only_one_recovery(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    run_id, operation_id = _interrupted_query(workspace, state)
    entered = threading.Event()
    release = threading.Event()

    def recover(_request):
        entered.set()
        assert release.wait(5)
        return Stopped("confirmed stopped")

    first_provider = FakeProvider([])
    first_provider.recover = recover
    second_provider = FakeProvider([])
    second_provider.recover = lambda request: pytest.fail(
        "excluded resolve reached provider recovery"
    )
    with (
        Botpipe(workspace, state_dir=state, provider=first_provider) as first,
        Botpipe(workspace, state_dir=state, provider=second_provider) as second,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        resolving = pool.submit(
            first.resolve,
            run_id,
            operation_id,
            response=ProviderResponse("first"),
        )
        try:
            assert entered.wait(5)
            with pytest.raises(RunBusy):
                second.resolve(
                    run_id,
                    operation_id,
                    response=ProviderResponse("second"),
                )
        finally:
            release.set()
        resolving.result(timeout=5)
        assert first.journal.get(operation_id)["response"]["text"] == "first"


def test_concurrent_resumes_are_excluded_across_different_roots(tmp_path):
    original_root = tmp_path / "original"
    other_root = tmp_path / "other"
    original_root.mkdir()
    other_root.mkdir()
    state = tmp_path / "state"
    run_id, _operation_id = _interrupted_query(original_root, state)
    entered = threading.Event()
    release = threading.Event()

    def recover(_request):
        entered.set()
        assert release.wait(5)
        return Completed(ProviderResponse("recovered"))

    first_provider = FakeProvider([])
    first_provider.recover = recover
    second_provider = FakeProvider([])
    second_provider.recover = lambda request: pytest.fail(
        "excluded resume reached provider recovery"
    )
    with (
        Botpipe(original_root, state_dir=state, provider=first_provider) as first,
        Botpipe(other_root, state_dir=state, provider=second_provider) as second,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        resuming = pool.submit(first.resume, run_id)
        try:
            assert entered.wait(5)
            with pytest.raises(RunBusy):
                second.resume(run_id)
        finally:
            release.set()
        result = resuming.result(timeout=5)
        assert result.ok, result.error
        assert result.value.value == "recovered"


def test_initial_execution_excludes_resolution_of_its_live_operation(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    entered = threading.Event()
    release = threading.Event()
    operation = {}

    def run_provider(request):
        operation["id"] = request.operation_id
        entered.set()
        assert release.wait(5)
        return "finished"

    running_provider = FakeProvider([run_provider])
    resolver_provider = FakeProvider([])
    resolver_provider.recover = lambda request: pytest.fail(
        "resolution entered recovery during initial execution"
    )
    with (
        Botpipe(workspace, state_dir=state, provider=running_provider) as runner,
        Botpipe(workspace, state_dir=state, provider=resolver_provider) as resolver,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        running = pool.submit(
            Provider(runtime=runner, session=None).query, "inspect"
        )
        try:
            assert entered.wait(5)
            run_id = runner.journal.runs()[0]["run_id"]
            with pytest.raises(RunBusy):
                resolver.resolve(
                    run_id,
                    operation["id"],
                    response=ProviderResponse("operator"),
                )
        finally:
            release.set()
        assert running.result(timeout=5).value == "finished"


def test_different_read_runs_in_one_journal_remain_parallel(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    both = threading.Barrier(2)

    def read(_request):
        both.wait(timeout=5)
        return "read"

    with (
        Botpipe(workspace, state_dir=state, provider=FakeProvider([read])) as first,
        Botpipe(workspace, state_dir=state, provider=FakeProvider([read])) as second,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        futures = [
            pool.submit(Provider(runtime=client, session=None).query, "inspect")
            for client in (first, second)
        ]
        assert [future.result(timeout=8).value for future in futures] == [
            "read",
            "read",
        ]
        assert len({run["run_id"] for run in first.journal.runs()}) == 2


def test_cancel_does_not_wait_for_execution_guard(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entered = threading.Event()
    release = threading.Event()

    def run_provider(_request):
        entered.set()
        assert release.wait(5)
        return "finished"

    provider = FakeProvider([run_provider])
    with (
        Botpipe(workspace, state_dir=tmp_path / "state", provider=provider) as client,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        running = pool.submit(
            Provider(runtime=client, session=None).query, "inspect"
        )
        assert entered.wait(5)
        run_id = client.journal.runs()[0]["run_id"]
        assert pool.submit(client.pending, run_id).result(timeout=2) == ()
        pool.submit(client.inspect, run_id).result(timeout=2)
        cancelling = pool.submit(client.cancel, run_id)
        try:
            with pytest.raises(UncertainOperation):
                cancelling.result(timeout=2)
        finally:
            release.set()
        with pytest.raises(UncertainOperation):
            running.result(timeout=5)
