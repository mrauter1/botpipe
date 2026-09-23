from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from botpipe.processes import ProcessContainment


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group behavior")
def test_posix_zombie_only_group_permission_error_is_quiescent(monkeypatch):
    from botpipe import processes

    process = SimpleNamespace(pid=321, poll=lambda: 0)
    containment = ProcessContainment({}, _owned_pid=321, _owned_pgid=321)
    monkeypatch.setattr(processes.os, "getpgrp", lambda: 1)
    monkeypatch.setattr(processes.os, "getpgid", lambda _pid: 321)
    monkeypatch.setattr(
        processes.os,
        "killpg",
        lambda *_args: (_ for _ in ()).throw(PermissionError()),
    )
    monkeypatch.setattr(
        processes.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="321 321 Z\n"),
    )

    containment._terminate_posix_group(process, grace_seconds=0)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group behavior")
def test_posix_live_group_permission_error_is_not_suppressed(monkeypatch):
    from botpipe import processes

    process = SimpleNamespace(pid=321, poll=lambda: None)
    containment = ProcessContainment({}, _owned_pid=321, _owned_pgid=321)
    monkeypatch.setattr(processes.os, "getpgrp", lambda: 1)
    monkeypatch.setattr(processes.os, "getpgid", lambda _pid: 321)
    monkeypatch.setattr(
        processes.os,
        "killpg",
        lambda *_args: (_ for _ in ()).throw(PermissionError()),
    )
    monkeypatch.setattr(
        processes.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="321 321 S\n"),
    )

    with pytest.raises(PermissionError):
        containment._terminate_posix_group(process, grace_seconds=0)


def test_windows_child_is_suspended_until_owned_job_assignment(monkeypatch):
    from botpipe import processes

    calls = []
    job = SimpleNamespace(
        assign_and_resume=lambda process: calls.append(
            ("assign-and-resume", process.pid)
        ),
        terminate=lambda code: calls.append(("terminate", code)),
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


@pytest.mark.skipif(os.name != "nt", reason="Native Windows Job Object smoke test")
def test_windows_job_close_terminates_running_descendants(tmp_path):
    import time
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
