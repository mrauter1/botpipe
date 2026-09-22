from __future__ import annotations

import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from botpipe.processes import ProcessContainment, ProcessContainmentUnavailable

_SIGTERM = int(getattr(signal, "SIGTERM", 15))
_SIGKILL = int(getattr(signal, "SIGKILL", 9))


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux wait-status contract"
)
@pytest.mark.parametrize(
    ("wait_status", "exit_code"),
    [
        (37 << 8, 37),
        (_SIGTERM, -_SIGTERM),
        (_SIGKILL, -_SIGKILL),
    ],
)
def test_linux_payload_status_decodes_wait_status(wait_status, exit_code):
    parent, helper = socket.socketpair()
    containment = ProcessContainment({}, _linux_status_socket=parent)
    helper.sendall(b"S" + struct.pack("!I", wait_status))
    helper.close()

    assert containment._read_linux_payload_status(required=True) == exit_code


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux wait-status contract"
)
@pytest.mark.parametrize(
    "record",
    [
        b"",
        b"S\0",
        b"X" + b"\0" * 4,
        b"S" + b"\0" * 5,
        b"S" + struct.pack("!I", 0x10000),
    ],
)
def test_linux_payload_status_missing_or_malformed_fails_closed(record):
    parent, helper = socket.socketpair()
    containment = ProcessContainment({}, _linux_status_socket=parent)
    helper.sendall(record)
    helper.close()

    with pytest.raises(RuntimeError, match="payload.*status"):
        containment._read_linux_payload_status(required=True)


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux wait-status contract"
)
def test_forced_linux_cleanup_allows_missing_payload_status(monkeypatch):
    parent, helper = socket.socketpair()
    helper.close()
    process = SimpleNamespace(pid=123)
    containment = ProcessContainment(
        {}, _owned_pid=123, _process=process, _linux_status_socket=parent
    )
    monkeypatch.setattr(
        ProcessContainment,
        "_terminate_linux",
        lambda self, observed, *, grace_seconds: None,
    )

    assert containment.finish(process, grace_seconds=0.1, forced=True) is None


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux wait-status contract"
)
def test_linux_finish_caches_authenticated_payload_status(monkeypatch):
    parent, helper = socket.socketpair()
    helper.sendall(b"S" + struct.pack("!I", 23 << 8))
    helper.close()
    process = SimpleNamespace(pid=123, poll=lambda: 0, returncode=0)
    containment = ProcessContainment(
        {}, _owned_pid=123, _process=process, _linux_status_socket=parent
    )
    cleanups = []
    monkeypatch.setattr(
        ProcessContainment,
        "ensure_tree_exited",
        lambda self, observed, *, grace_seconds: cleanups.append(observed),
    )

    assert containment.finish(process, grace_seconds=0.1) == 23
    assert containment.finish(process, grace_seconds=0.1) == 23
    assert cleanups == [process]


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux wait-status contract"
)
def test_concurrent_linux_finish_reads_terminal_status_once(monkeypatch):
    parent, helper = socket.socketpair()
    helper.sendall(b"S" + struct.pack("!I", 17 << 8))
    helper.close()
    process = SimpleNamespace(pid=123, poll=lambda: 0, returncode=0)
    containment = ProcessContainment(
        {}, _owned_pid=123, _process=process, _linux_status_socket=parent
    )
    cleanups = []

    def cleanup(self, observed, *, grace_seconds):
        cleanups.append(observed)
        time.sleep(0.02)

    monkeypatch.setattr(ProcessContainment, "ensure_tree_exited", cleanup)
    start = threading.Barrier(3)
    results = []
    errors = []

    def finish():
        try:
            start.wait()
            results.append(containment.finish(process, grace_seconds=0.1))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=finish) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=1)

    assert not errors
    assert results == [17, 17]
    assert cleanups == [process]


def test_windows_spawn_assigns_suspended_child_before_resume(monkeypatch):
    import botpipe.processes as processes

    calls = []
    job = SimpleNamespace(
        assign_and_resume=lambda process: calls.append(("assign", process.pid)),
        terminate=lambda code: calls.append(("terminate", code)),
        active_process_count=lambda: 0,
        close=lambda: calls.append(("close",)),
    )
    process = SimpleNamespace(pid=123, poll=lambda: 0, returncode=0)
    monkeypatch.setattr(processes, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    monkeypatch.setattr(processes.WindowsJobObject, "create", lambda: job)
    monkeypatch.setattr(
        processes.subprocess,
        "Popen",
        lambda argv, **kwargs: calls.append(("popen", tuple(argv), kwargs)) or process,
    )

    containment = ProcessContainment.create()
    observed = containment.spawn(("command",), stdin=subprocess.DEVNULL)
    assert containment.finish(observed, grace_seconds=0.1) == 0
    containment.close()

    assert calls[0][0] == "popen"
    assert calls[0][2]["creationflags"] & 4  # CREATE_SUSPENDED
    assert calls[1:] == [
        ("assign", 123),
        ("terminate", 0),
        ("close",),
    ]


def test_windows_close_proves_job_exit_before_releasing_handle(monkeypatch):
    import botpipe.processes as processes

    calls = []
    job = SimpleNamespace(
        terminate=lambda code: calls.append(("terminate", code)),
        active_process_count=lambda: 0,
        close=lambda: calls.append(("close",)),
    )
    process = SimpleNamespace(
        pid=123, args=("stub",), poll=lambda: 1, returncode=1
    )
    containment = ProcessContainment(
        {}, _windows_job=job, _owned_pid=123, _process=process
    )
    monkeypatch.setattr(processes, "os", SimpleNamespace(name="nt"))

    containment.close()

    assert calls == [("terminate", 1), ("close",)]
    assert containment.finish(process, grace_seconds=0.1, forced=True) == 1


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux close contract"
)
def test_linux_close_proves_monitor_exit_before_closing_status_channel(monkeypatch):
    parent, helper = socket.socketpair()
    process = SimpleNamespace(pid=123)
    containment = ProcessContainment(
        {}, _owned_pid=123, _process=process, _linux_status_socket=parent
    )
    calls = []

    def terminate(self, observed, *, grace_seconds):
        assert self._linux_status_socket is not None
        assert self._linux_status_socket.fileno() >= 0
        calls.append("proved-exit")
        helper.close()

    monkeypatch.setattr(ProcessContainment, "_terminate_linux", terminate)

    containment.close()

    assert calls == ["proved-exit"]
    assert parent.fileno() == -1
    assert containment.finish(process, grace_seconds=0.1, forced=True) is None


def test_windows_job_survivor_is_cleanup_uncertainty(monkeypatch):
    import botpipe.processes as processes

    job = SimpleNamespace(terminate=lambda _code: None, active_process_count=lambda: 1)
    containment = ProcessContainment({}, _windows_job=job, _owned_pid=123)
    process = SimpleNamespace(pid=123, args=("stub",), poll=lambda: 0)
    monkeypatch.setattr(processes, "os", SimpleNamespace(name="nt"))

    with pytest.raises(subprocess.TimeoutExpired):
        containment.ensure_tree_exited(process, grace_seconds=0.001)


def test_linux_capability_probe_is_cached_by_launcher_identity(monkeypatch):
    import botpipe.processes as processes

    identity = (("unshare", 1), ("python", 2), (2, 39))
    calls = []
    monkeypatch.setattr(processes.os, "name", "posix")
    monkeypatch.setattr(
        processes,
        "_linux_dependencies",
        lambda: ("/usr/bin/unshare", "/usr/bin/python3", identity),
    )
    monkeypatch.setattr(
        ProcessContainment,
        "_probe_linux",
        lambda self: calls.append(self._linux_identity) or None,
    )
    processes._linux_probe_cache.clear()

    ProcessContainment.create().close()
    ProcessContainment.create().close()

    assert calls == [identity]


def test_unsupported_posix_host_fails_closed(monkeypatch):
    import botpipe.processes as processes

    monkeypatch.setattr(processes.os, "name", "posix")
    monkeypatch.setattr(
        processes,
        "_linux_dependencies",
        lambda: (_ for _ in ()).throw(
            ProcessContainmentUnavailable("PID namespaces unavailable")
        ),
    )

    with pytest.raises(
        ProcessContainmentUnavailable, match="PID namespaces unavailable"
    ):
        ProcessContainment.create()


@pytest.mark.parametrize(
    "unsafe_kwarg",
    [
        {"executable": "/bin/true"},
        {"preexec_fn": lambda: None},
        {"shell": True},
    ],
)
def test_spawn_rejects_bootstrap_bypass_kwargs_before_popen(
    unsafe_kwarg, monkeypatch
):
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("Popen must not be reached"),
    )
    containment = ProcessContainment({})

    with pytest.raises(ValueError, match="contained spawn"):
        containment.spawn(("command",), **unsafe_kwarg)


@pytest.mark.skipif(os.name != "posix", reason="POSIX containment dispatch")
def test_ensure_tree_exited_terminates_a_still_running_namespace(monkeypatch):
    process = SimpleNamespace(pid=123, poll=lambda: None)
    containment = ProcessContainment({}, _owned_pid=123, _process=process)
    calls = []
    monkeypatch.setattr(
        ProcessContainment,
        "_terminate_linux",
        lambda self, observed, *, grace_seconds: calls.append(
            (self, observed, grace_seconds)
        ),
    )

    containment.ensure_tree_exited(process, grace_seconds=0.25)

    assert calls == [(containment, process, 0.25)]


@pytest.fixture
def linux_containment() -> ProcessContainment:
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux PID-namespace integration test")
    try:
        containment = ProcessContainment.create()
    except ProcessContainmentUnavailable as exc:
        if os.environ.get("BOTPIPE_REQUIRE_NATIVE_CONTAINMENT") == "1":
            pytest.fail(f"required native containment is unavailable: {exc}")
        pytest.skip(f"host lacks required PID-namespace containment: {exc}")
    try:
        yield containment
    finally:
        containment.close()


def test_linux_spawn_preserves_argv_cwd_env_and_stdio(
    tmp_path: Path, linux_containment: ProcessContainment
):
    script = (
        "import json,os,sys;"
        "print(json.dumps([sys.argv[1:],os.getcwd(),os.environ['TOKEN'],"
        "sys.stdin.read()]))"
    )
    process = linux_containment.spawn(
        (sys.executable, "-c", script, "one", "two"),
        cwd=tmp_path,
        env={"PATH": os.environ.get("PATH", ""), "TOKEN": "present"},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate(b"input")
    returncode = linux_containment.finish(process, grace_seconds=2.0)

    assert returncode == 0
    assert stderr == b""
    assert stdout == (
        f'[["one", "two"], "{tmp_path}", "present", "input"]\n'.encode()
    )


def test_linux_payload_restores_default_sigpipe(
    linux_containment: ProcessContainment,
):
    process = linux_containment.spawn(
        ("/bin/sh", "-c", "kill -s PIPE $$; exit 99"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate()
    returncode = linux_containment.finish(process, grace_seconds=2.0)

    assert returncode == -signal.SIGPIPE
    assert stderr == b""
    assert stdout == b""


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        ("import sys;sys.exit(37)", 37),
        ("import os,signal;os.kill(os.getpid(),signal.SIGTERM)", -_SIGTERM),
        ("import os,signal;os.kill(os.getpid(),signal.SIGKILL)", -_SIGKILL),
    ],
)
def test_linux_finish_reports_payload_status(
    linux_containment: ProcessContainment, script: str, expected: int
):
    process = linux_containment.spawn(
        (sys.executable, "-c", script),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    process.wait(timeout=3)

    assert process.returncode == 0
    assert linux_containment.finish(process, grace_seconds=2.0) == expected


def test_linux_normal_exit_kills_detached_descendant(
    tmp_path: Path, linux_containment: ProcessContainment
):
    ready = tmp_path / "ready"
    escaped = tmp_path / "escaped"
    child = (
        "import pathlib,sys,time;"
        "pathlib.Path(sys.argv[1]).write_text('ready');"
        "time.sleep(.5);pathlib.Path(sys.argv[2]).write_text('escaped')"
    )
    parent = (
        "import pathlib,subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]],"
        "start_new_session=True);"
        "p=pathlib.Path(sys.argv[2]);deadline=time.monotonic()+2;"
        "exec('while not p.exists() and time.monotonic() < deadline: time.sleep(.01)')"
    )
    process = linux_containment.spawn(
        (sys.executable, "-c", parent, child, str(ready), str(escaped)),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    process.wait(timeout=3)
    assert linux_containment.finish(process, grace_seconds=2.0) == 0
    time.sleep(0.7)

    assert ready.exists()
    assert not escaped.exists()


def test_linux_timeout_kills_detached_descendant(
    tmp_path: Path, linux_containment: ProcessContainment
):
    ready = tmp_path / "ready"
    escaped = tmp_path / "escaped"
    child = (
        "import pathlib,sys,time;"
        "pathlib.Path(sys.argv[1]).write_text('ready');"
        "time.sleep(.5);pathlib.Path(sys.argv[2]).write_text('escaped')"
    )
    parent = (
        "import subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]],"
        "start_new_session=True);time.sleep(30)"
    )
    process = linux_containment.spawn(
        (sys.executable, "-c", parent, child, str(ready), str(escaped)),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 2
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.exists()

    linux_containment.finish(process, grace_seconds=0.2, forced=True)
    time.sleep(0.7)

    assert not escaped.exists()


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux PID-namespace integration test"
)
def test_linux_owner_death_closes_lifeline_and_kills_namespace(tmp_path: Path):
    try:
        ProcessContainment.require_available()
    except ProcessContainmentUnavailable as exc:
        if os.environ.get("BOTPIPE_REQUIRE_NATIVE_CONTAINMENT") == "1":
            pytest.fail(f"required native containment is unavailable: {exc}")
        pytest.skip(f"host lacks required PID-namespace containment: {exc}")

    ready = tmp_path / "ready"
    escaped = tmp_path / "escaped"
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import subprocess,sys\n"
        "from botpipe.processes import ProcessContainment\n"
        "child=(\"import pathlib,sys,time;\"\n"
        "       \"pathlib.Path(sys.argv[1]).write_text('ready');\"\n"
        "       \"time.sleep(.5);pathlib.Path(sys.argv[2]).write_text('escaped')\")\n"
        "payload=(\"import subprocess,sys,time;\"\n"
        "         \"subprocess.Popen([sys.executable,'-c',sys.argv[1],\"\n"
        "         \"sys.argv[2],sys.argv[3]],start_new_session=True);time.sleep(30)\")\n"
        "c=ProcessContainment.create()\n"
        "p=c.spawn((sys.executable,'-c',payload,child,sys.argv[1],sys.argv[2]),\n"
        "          stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,\n"
        "          stderr=subprocess.DEVNULL)\n"
        "p.wait()\n"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    owner = subprocess.Popen(
        (sys.executable, str(driver), str(ready), str(escaped)), env=environment
    )
    try:
        deadline = time.monotonic() + 4
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        os.kill(owner.pid, signal.SIGKILL)
        owner.wait(timeout=2)
        time.sleep(0.7)
        assert not escaped.exists()
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait()
