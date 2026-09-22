from __future__ import annotations

import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from botpipe import Botpipe, Policy, Provider, provider_budget, workflow
from botpipe.processes import ProcessContainment
from botpipe.providers import CodexProvider


def test_windows_child_is_suspended_until_owned_job_assignment(monkeypatch):
    import botpipe.processes as processes

    calls = []
    job = SimpleNamespace(
        assign_and_resume=lambda process: calls.append(
            ("assign-and-resume", process.pid)
        ),
        terminate=lambda code: calls.append(("terminate", code)),
        active_process_count=lambda: 0,
        close=lambda: calls.append(("close",)),
    )
    monkeypatch.setattr(processes, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    monkeypatch.setattr(processes.WindowsJobObject, "create", lambda: job)
    containment = ProcessContainment.create()
    assert containment.creation_kwargs["creationflags"] & 4  # CREATE_SUSPENDED
    process = SimpleNamespace(pid=123, poll=lambda: 0)
    containment.attach_and_start(process)
    containment.ensure_tree_exited(process, grace_seconds=0.1)
    containment.close()
    assert calls == [("assign-and-resume", 123), ("terminate", 0), ("close",)]


def test_windows_job_survivor_is_cleanup_uncertainty(monkeypatch):
    import botpipe.processes as processes

    job = SimpleNamespace(
        terminate=lambda _code: None,
        active_process_count=lambda: 1,
    )
    containment = ProcessContainment({}, _windows_job=job, _owned_pid=123)
    process = SimpleNamespace(pid=123, args=("stub",), poll=lambda: 0)
    monkeypatch.setattr(processes, "os", SimpleNamespace(name="nt"))

    with pytest.raises(subprocess.TimeoutExpired):
        containment.ensure_tree_exited(process, grace_seconds=0.001)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_posix_post_kill_survivor_is_cleanup_uncertainty(monkeypatch):
    import botpipe.processes as processes

    signals = []
    containment = ProcessContainment({}, _owned_pid=123, _owned_pgid=123)
    process = SimpleNamespace(pid=123, args=("stub",), poll=lambda: None)
    monkeypatch.setattr(processes.os, "getpgid", lambda _pid: 123)
    monkeypatch.setattr(
        processes.os, "killpg", lambda pgid, sig: signals.append((pgid, sig))
    )
    monkeypatch.setattr(
        ProcessContainment,
        "_posix_group_has_live_processes",
        staticmethod(lambda _pgid: True),
    )

    with pytest.raises(subprocess.TimeoutExpired):
        containment.terminate(process, grace_seconds=0.001)

    assert signals == [(123, processes.signal.SIGTERM), (123, processes.signal.SIGKILL)]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_success_cleanup_signals_descendants_without_pre_term_delay(tmp_path):
    ready = tmp_path / "ready"
    escaped = tmp_path / "escaped"
    child = (
        "import pathlib,sys,time;"
        "pathlib.Path(sys.argv[1]).write_text('ready');"
        "time.sleep(.05);"
        "pathlib.Path(sys.argv[2]).write_text('escaped')"
    )
    parent = (
        "import pathlib,subprocess,sys,time\n"
        f"subprocess.Popen([sys.executable,'-c',{child!r},{str(ready)!r},{str(escaped)!r}])\n"
        f"p=pathlib.Path({str(ready)!r})\n"
        "while not p.exists(): time.sleep(.001)\n"
    )
    containment = ProcessContainment.create()
    process = subprocess.Popen(
        [sys.executable, "-c", parent], **containment.creation_kwargs
    )
    try:
        containment.attach_and_start(process)
        process.wait(timeout=2)
        containment.ensure_tree_exited(process, grace_seconds=0.1)
        time.sleep(0.1)
        assert not escaped.exists()
    finally:
        try:
            containment.terminate(process, grace_seconds=0.1)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass
        containment.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_successful_native_leader_cannot_leave_effectful_descendant(tmp_path):
    marker = tmp_path / "escaped"
    child = f"import time,pathlib;time.sleep(1);pathlib.Path({str(marker)!r}).write_text('bad')"
    script = tmp_path / "cli.py"
    script.write_text(
        "import subprocess,sys,json\n"
        f"subprocess.Popen([sys.executable,'-c',{child!r}])\n"
        "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'done'}}))\n"
        "print(json.dumps({'type':'turn.completed'}))\n"
    )

    @workflow
    def work():
        return Provider().run("work").value

    with Botpipe(
        tmp_path, provider=CodexProvider((sys.executable, str(script)))
    ) as client:
        assert client.run(work).status == "completed"
    time.sleep(1.1)
    assert not marker.exists()


def test_native_budget_timeout_cannot_be_overridden_by_policy(tmp_path):
    script = tmp_path / "cli.py"
    script.write_text("import time;time.sleep(10)\n")

    @workflow
    def work():
        with provider_budget(max_turns=1, turn_timeout_seconds=0.05):
            Provider().run("work", policy=Policy(timeout=10))

    started = time.monotonic()
    with Botpipe(
        tmp_path, provider=CodexProvider((sys.executable, str(script)))
    ) as client:
        result = client.run(work)
        assert result.status == "interrupted"
        assert "timed out after 0.05" in result.error
    assert time.monotonic() - started < 3


@pytest.mark.skipif(os.name != "nt", reason="Native Windows Job Object smoke test")
def test_windows_job_close_terminates_running_descendants(tmp_path):
    ready, escaped = tmp_path / "ready", tmp_path / "escaped"
    child = (
        f"import pathlib,time;pathlib.Path({str(ready)!r}).write_text('ready');"
        f"time.sleep(1);pathlib.Path({str(escaped)!r}).write_text('escaped')"
    )
    parent = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{child!r}]);time.sleep(10)"
    containment = ProcessContainment.create()
    process = subprocess.Popen(
        [sys.executable, "-c", parent], **containment.creation_kwargs
    )
    try:
        containment.attach_and_start(process)
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "contained child did not start"
        containment.close()
        process.wait(timeout=3)
        time.sleep(1.1)
        assert not escaped.exists()
    finally:
        if process.poll() is None:
            containment.terminate(process, grace_seconds=1)
        containment.close()
