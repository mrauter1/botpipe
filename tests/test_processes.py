from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from botpipe.processes import ProcessCleanupError, ProcessContainment


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


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group behavior")
def test_captured_nested_group_is_killed_after_parent_is_reaped(tmp_path):
    from botpipe.processes import _posix_group_is_quiescent

    marker, pid_file = tmp_path / "escaped", tmp_path / "child.pid"
    child = (
        "import pathlib,sys,time;"
        "pathlib.Path(sys.argv[1]).write_text(str(__import__('os').getpid()));"
        "time.sleep(1);pathlib.Path(sys.argv[2]).write_text('escaped')"
    )
    parent = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',{child!r},sys.argv[1],sys.argv[2]],"
        "start_new_session=True);time.sleep(10)"
    )
    containment = ProcessContainment.create()
    process = subprocess.Popen(
        [sys.executable, "-c", parent, str(pid_file), str(marker)],
        **containment.creation_kwargs,
    )
    containment.attach_and_start(process)
    try:
        deadline = time.monotonic() + 3
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pid_file.exists()
        child_pid = int(pid_file.read_text())
        containment.capture_descendant_groups(process)
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)

        containment.ensure_tree_exited(process, grace_seconds=0.1)
        assert _posix_group_is_quiescent(child_pid)
        time.sleep(1.1)
        assert not marker.exists()
    finally:
        if process.poll() is None:
            containment.terminate(process, grace_seconds=0.1)
        containment.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group behavior")
def test_captured_group_with_reused_witness_is_not_signalled(monkeypatch):
    from botpipe import processes

    containment = ProcessContainment(
        {}, _descendant_groups={456: {123: "original-start"}}
    )
    monkeypatch.setattr(
        processes,
        "_posix_processes",
        lambda: {123: (1, 456, "S", "replacement-start")},
    )
    signals = []
    monkeypatch.setattr(processes.os, "killpg", lambda pgid, sig: signals.append((pgid, sig)))

    containment._signal_descendant_groups(signal.SIGKILL)

    assert signals == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group behavior")
def test_inspection_failure_still_attempts_group_cleanup_and_is_exposed(monkeypatch):
    from botpipe import processes

    process = SimpleNamespace(pid=321, poll=lambda: None)
    containment = ProcessContainment({}, _owned_pid=321, _owned_pgid=321)
    monkeypatch.setattr(processes.os, "getpgrp", lambda: 1)
    monkeypatch.setattr(processes.os, "getpgid", lambda _pid: 321)
    monkeypatch.setattr(
        processes,
        "_posix_processes",
        lambda: (_ for _ in ()).throw(OSError("ps unavailable")),
    )
    signals = []

    def missing_group(pgid, sig):
        signals.append((pgid, sig))
        raise ProcessLookupError

    monkeypatch.setattr(processes.os, "killpg", missing_group)

    containment.capture_descendant_groups(process)
    with pytest.raises(ProcessCleanupError, match="ps unavailable"):
        containment.terminate(process, grace_seconds=0)
    assert signals == [(321, signal.SIGTERM)]


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


@pytest.mark.skipif(os.name != "posix", reason="POSIX parent signal behavior")
def test_release_signals_only_owned_parent(monkeypatch):
    from botpipe import processes

    calls = []

    class Process:
        pid = 321

        def poll(self):
            return None

        def wait(self, *, timeout):
            calls.append(("wait", timeout))
            return 0

    containment = ProcessContainment({}, _owned_pid=321, _owned_pgid=321)
    monkeypatch.setattr(
        processes.os, "kill", lambda pid, sig: calls.append(("kill", pid, sig))
    )
    monkeypatch.setattr(
        processes.os,
        "killpg",
        lambda *_args: pytest.fail("normal release signalled a process group"),
    )

    containment.release(Process(), grace_seconds=0.25)  # type: ignore[arg-type]

    assert calls == [("kill", 321, signal.SIGINT), ("wait", 0.25)]
    assert containment._owned_pid is None


def test_windows_release_disarms_job_instead_of_terminating(monkeypatch):
    from botpipe import processes

    calls = []
    job = SimpleNamespace(
        release=lambda: calls.append(("release",)),
        terminate=lambda code: calls.append(("terminate", code)),
    )
    process = SimpleNamespace(
        pid=123,
        poll=lambda: 0,
        terminate=lambda: calls.append(("parent-terminate",)),
    )
    containment = ProcessContainment({}, _windows_job=job, _owned_pid=123)
    monkeypatch.setattr(processes, "os", SimpleNamespace(name="nt"))

    containment.release(process, grace_seconds=0.1)

    assert calls == [("release",)]
    assert containment._windows_job is None


def test_windows_job_release_clears_kill_on_close_limit():
    import ctypes

    from botpipe.processes import WindowsJobObject

    calls = []

    class Kernel:
        def SetInformationJobObject(self, handle, info_class, pointer, size):
            calls.append((handle, info_class, ctypes.string_at(pointer, size)))
            return True

        def CloseHandle(self, handle):
            calls.append(("close", handle))
            return True

    job = WindowsJobObject(17, Kernel())
    job.release()

    assert calls[0][:2] == (17, 9)
    assert set(calls[0][2]) <= {0}
    assert calls[1] == ("close", 17)
    assert job.handle is None


def test_windows_job_close_failure_retains_handle():
    from botpipe.processes import WindowsJobObject

    class Kernel:
        def CloseHandle(self, _handle):
            return False

    job = WindowsJobObject(17, Kernel())

    with pytest.raises(OSError, match="CloseHandle failed"):
        job.close()

    assert job.handle == 17


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


@pytest.mark.skipif(os.name != "nt", reason="Native Windows Job Object smoke test")
def test_windows_job_release_allows_running_descendant_to_finish(tmp_path):
    ready, finished = tmp_path / "ready", tmp_path / "finished"
    child = (
        f"import pathlib,time;pathlib.Path({str(ready)!r}).write_text('ready');"
        f"time.sleep(1);pathlib.Path({str(finished)!r}).write_text('finished')"
    )
    parent = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',{child!r}]);time.sleep(10)"
    )
    containment = ProcessContainment.create()
    process = subprocess.Popen(
        [sys.executable, "-c", parent], **containment.creation_kwargs
    )
    containment.attach_and_start(process)
    deadline = time.monotonic() + 5
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert ready.exists(), "contained child did not start"

    containment.release(process, grace_seconds=3)

    deadline = time.monotonic() + 3
    while not finished.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert finished.read_text() == "finished"
