"""Kernel-backed owned-process-tree containment primitives."""

from __future__ import annotations
import array
import hashlib
import json
import os
import re
import select
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
import threading
from dataclasses import dataclass, field
from typing import Any


class ProcessContainmentUnavailable(RuntimeError):
    """The host cannot provide complete process-tree containment."""


_LINUX_HELPER = r'''
import array, ctypes, json, os, select, signal, socket, struct, sys

lifeline_fd = int(sys.argv[1])
ready_fd = int(sys.argv[2])
parent_pidfd = int(sys.argv[3])
environment_fd = int(sys.argv[4])
target = sys.argv[5:]
if os.getpid() != 1 or not target:
    os._exit(125)

# The payload shares our UID.  Make namespace init non-dumpable, then remove
# the temporary capabilities granted solely to construct the user namespace.
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE
    os._exit(125)
with open("/proc/sys/kernel/cap_last_cap", encoding="ascii") as stream:
    cap_last = int(stream.read())
for capability in range(cap_last + 1):
    if libc.prctl(24, capability, 0, 0, 0) != 0:  # PR_CAPBSET_DROP
        os._exit(125)
class CapHeader(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]
class CapData(ctypes.Structure):
    _fields_ = [("effective", ctypes.c_uint32),
                ("permitted", ctypes.c_uint32),
                ("inheritable", ctypes.c_uint32)]
header = CapHeader(0x20080522, 0)
data = (CapData * 2)()
if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
    os._exit(125)
if libc.prctl(47, 4, 0, 0, 0) != 0:  # PR_CAP_AMBIENT, CLEAR_ALL
    os._exit(125)

with os.fdopen(environment_fd, "r", encoding="utf-8") as stream:
    payload_environment = dict(json.load(stream))

pidfd = os.pidfd_open(os.getpid(), 0)
ready = socket.socket(fileno=ready_fd)
rights = array.array("i", [pidfd])
ready.sendmsg([b"R"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)])
os.close(pidfd)

# The payload cannot run until the owner has received the namespace init pidfd.
if (select.select([lifeline_fd, parent_pidfd], [], [])[0] != [lifeline_fd]
        or os.read(lifeline_fd, 1) != b"G"):
    os._exit(125)

pending_signal = 0
def request_stop(signum, _frame):
    global pending_signal
    pending_signal = signum

signal.signal(signal.SIGTERM, request_stop)
signal.signal(signal.SIGINT, request_stop)

child = os.fork()
if child == 0:
    os.close(lifeline_fd)
    os.close(parent_pidfd)
    ready.close()
    for signal_name in ("SIGPIPE", "SIGXFZ", "SIGXFSZ"):
        restored = getattr(signal, signal_name, None)
        if restored is not None:
            signal.signal(restored, signal.SIG_DFL)
    try:
        os.execvpe(target[0], target, payload_environment)
    except BaseException:
        os._exit(127)

forwarded = 0
leader_status = None
while True:
    if pending_signal and pending_signal != forwarded:
        try:
            os.kill(child, pending_signal)
        except ProcessLookupError:
            pass
        forwarded = pending_signal
    while True:
        try:
            waited, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            waited = 0
        if waited == 0:
            break
        if waited == child:
            leader_status = status
    if leader_status is not None:
        os.close(lifeline_fd)
        try:
            ready.sendall(b"S" + struct.pack("!I", leader_status))
        except OSError:
            pass
        ready.close()
        os._exit(0)
    readable, _, _ = select.select([lifeline_fd, parent_pidfd], [], [], 0.02)
    if parent_pidfd in readable:
        os._exit(125)
    if lifeline_fd in readable and os.read(lifeline_fd, 1) == b"":
        os._exit(125)
'''

_LINUX_MIN_UNSHARE_VERSION = (2, 37)
_LINUX_STARTUP_TIMEOUT_SECONDS = 5.0
_linux_probe_cache: dict[tuple[object, ...], str | None] = {}


def _trusted_system_executable(name: str) -> tuple[str, tuple[object, ...]]:
    value = shutil.which(name, path="/usr/bin:/bin")
    if value is None:
        raise ProcessContainmentUnavailable(
            f"Linux process containment requires trusted {name} in /usr/bin or /bin"
        )
    path = os.path.realpath(value)
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0:
        raise ProcessContainmentUnavailable(
            f"Linux process containment requires root-owned regular {name}: {path}"
        )
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ProcessContainmentUnavailable(
            f"Linux process containment requires immutable trusted {name}: {path}"
        )
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    identity = (
        path,
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        digest.digest(),
    )
    return path, identity


def _linux_dependencies() -> tuple[str, str, tuple[object, ...]]:
    if not sys.platform.startswith("linux"):
        raise ProcessContainmentUnavailable(
            "complete POSIX process containment currently requires Linux PID namespaces"
        )
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise ProcessContainmentUnavailable(
            "Linux process containment requires pidfd_open and pidfd_send_signal"
        )
    if not hasattr(os, "memfd_create"):
        raise ProcessContainmentUnavailable(
            "Linux process containment requires sealed anonymous memory files"
        )
    try:
        import fcntl
    except ImportError as exc:
        raise ProcessContainmentUnavailable(
            "Linux process containment requires the standard fcntl module"
        ) from exc
    required_fcntl = (
        "F_ADD_SEALS",
        "F_SEAL_SEAL",
        "F_SEAL_SHRINK",
        "F_SEAL_GROW",
        "F_SEAL_WRITE",
    )
    if any(not hasattr(fcntl, name) for name in required_fcntl):
        raise ProcessContainmentUnavailable(
            "Linux process containment requires fcntl memfd sealing support"
        )
    unshare, unshare_identity = _trusted_system_executable("unshare")
    python, python_identity = _trusted_system_executable("python3")
    try:
        version_text = subprocess.check_output(
            (unshare, "--version"),
            text=True,
            stderr=subprocess.STDOUT,
            timeout=2,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
        match = re.search(r"(\d+)\.(\d+)", version_text)
        version = tuple(map(int, match.groups())) if match else (0, 0)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ProcessContainmentUnavailable(
            "could not verify the trusted util-linux unshare version"
        ) from exc
    if version < _LINUX_MIN_UNSHARE_VERSION:
        required = ".".join(map(str, _LINUX_MIN_UNSHARE_VERSION))
        raise ProcessContainmentUnavailable(
            f"Linux process containment requires util-linux unshare >= {required}"
        )
    return unshare, python, (unshare_identity, python_identity, version)


def _linux_control_resources(serialized_environment: bytes):
    import fcntl

    environment_fd = parent_pidfd = lifeline_read = lifeline_write = -1
    ready_parent = ready_child = None
    try:
        environment_fd = os.memfd_create(
            "botpipe-payload-environment", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING
        )
        remaining = memoryview(serialized_environment)
        while remaining:
            remaining = remaining[os.write(environment_fd, remaining) :]
        os.lseek(environment_fd, 0, os.SEEK_SET)
        fcntl.fcntl(
            environment_fd,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE,
        )
        parent_pidfd = os.pidfd_open(os.getpid(), 0)
        lifeline_read, lifeline_write = os.pipe2(os.O_CLOEXEC)
        ready_parent, ready_child = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC
        )
        ready_parent.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        return (
            environment_fd,
            parent_pidfd,
            lifeline_read,
            lifeline_write,
            ready_parent,
            ready_child,
        )
    except BaseException:
        for descriptor in (
            environment_fd,
            parent_pidfd,
            lifeline_read,
            lifeline_write,
        ):
            if descriptor >= 0:
                os.close(descriptor)
        if ready_parent is not None:
            ready_parent.close()
        if ready_child is not None:
            ready_child.close()
        raise


@dataclass(slots=True)
class ProcessContainment:
    creation_kwargs: dict[str, Any]
    _windows_job: "WindowsJobObject | None" = None
    _owned_pid: int | None = None
    _linux_unshare: str | None = None
    _linux_python: str | None = None
    _linux_identity: tuple[object, ...] | None = None
    _linux_init_pidfd: int | None = None
    _linux_lifeline: int | None = None
    _linux_status_socket: socket.socket | None = None
    _payload_status_finished: bool = False
    _payload_returncode: int | None = None
    _process: subprocess.Popen[bytes] | None = None
    _finish_lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )

    @classmethod
    def create(cls) -> "ProcessContainment":
        if os.name == "nt":
            return cls(
                {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | 4},
                WindowsJobObject.create(),
            )
        if os.name != "posix":
            raise ProcessContainmentUnavailable(
                f"process-tree containment unavailable on {os.name!r}"
            )
        unshare, python, identity = _linux_dependencies()
        cached = _linux_probe_cache.get(identity, "missing")
        if cached == "missing":
            probe = cls(
                {"start_new_session": True},
                _linux_unshare=unshare,
                _linux_python=python,
                _linux_identity=identity,
            )
            error = probe._probe_linux()
            _linux_probe_cache[identity] = error
            cached = error
        if cached is not None:
            raise ProcessContainmentUnavailable(cached)
        return cls(
            {"start_new_session": True},
            _linux_unshare=unshare,
            _linux_python=python,
            _linux_identity=identity,
        )

    @classmethod
    def require_available(cls) -> None:
        """Fail before dispatch unless complete containment is available."""

        containment = cls.create()
        containment.close()

    def _probe_linux(self) -> str | None:
        try:
            process = self._spawn_linux(
                (self._linux_python, "-I", "-S", "-c", "pass"),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd="/",
                env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            )
            process.wait(timeout=_LINUX_STARTUP_TIMEOUT_SECONDS)
            if self.finish(process, grace_seconds=1.0) != 0:
                return "Linux PID-namespace containment probe failed"
            return None
        except BaseException as exc:
            return (
                "Linux process containment requires permitted user, PID, and mount "
                f"namespaces with a private /proc mount: {exc}"
            )
        finally:
            self.close()

    def spawn(
        self, argv: Any, /, **popen_kwargs: Any
    ) -> subprocess.Popen[bytes]:
        """Start *argv* only after the kernel containment owner is registered."""

        if "executable" in popen_kwargs:
            raise ValueError("contained spawn does not accept executable=")
        if "preexec_fn" in popen_kwargs:
            raise ValueError("contained spawn does not accept preexec_fn=")
        if popen_kwargs.get("shell", False):
            raise ValueError("contained spawn requires shell=False")
        if self._owned_pid is not None or self._process is not None:
            raise RuntimeError("process containment instances are single-use")
        if self._windows_job is not None:
            kwargs = dict(popen_kwargs)
            flags = int(kwargs.pop("creationflags", 0))
            flags |= int(self.creation_kwargs["creationflags"])
            process = subprocess.Popen(argv, creationflags=flags, **kwargs)
            try:
                self._windows_job.assign_and_resume(process)
            except BaseException:
                process.kill()
                process.wait()
                raise
            self._owned_pid = process.pid
            self._process = process
            return process
        return self._spawn_linux(argv, **popen_kwargs)

    def _spawn_linux(
        self, argv: Any, /, **popen_kwargs: Any
    ) -> subprocess.Popen[bytes]:
        if self._linux_unshare is None or self._linux_python is None:
            raise ProcessContainmentUnavailable(
                "Linux process containment dependencies were not initialized"
            )
        current_unshare, current_python, current_identity = _linux_dependencies()
        if (
            current_unshare != self._linux_unshare
            or current_python != self._linux_python
            or current_identity != self._linux_identity
        ):
            raise ProcessContainmentUnavailable(
                "Linux containment launcher identity changed before spawn"
            )

        command = tuple(os.fspath(value) for value in argv)
        payload_environment = kwargs_environment = popen_kwargs.get("env")
        if kwargs_environment is None:
            payload_environment = dict(os.environ)
        try:
            serialized_environment = json.dumps(
                [
                    [os.fsdecode(key), os.fsdecode(value)]
                    for key, value in payload_environment.items()
                ],
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("ascii")
        except (AttributeError, TypeError, UnicodeError) as exc:
            raise ValueError("env must map strings or bytes to strings or bytes") from exc
        if any(
            "\0" in os.fsdecode(item)
            for pair in payload_environment.items()
            for item in pair
        ):
            raise ValueError("embedded null byte")
        (
            environment_fd,
            parent_pidfd,
            lifeline_read,
            lifeline_write,
            ready_parent,
            ready_child,
        ) = _linux_control_resources(serialized_environment)
        kwargs = dict(popen_kwargs)
        inherited = tuple(kwargs.pop("pass_fds", ()))
        kwargs["env"] = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
        kwargs.pop("start_new_session", None)
        wrapped = (
            self._linux_unshare,
            "--user",
            "--map-current-user",
            "--keep-caps",
            "--pid",
            "--fork",
            "--mount-proc",
            "--kill-child",
            "--",
            self._linux_python,
            "-I",
            "-S",
            "-c",
            _LINUX_HELPER,
            str(lifeline_read),
            str(ready_child.fileno()),
            str(parent_pidfd),
            str(environment_fd),
            *command,
        )
        process = None
        init_pidfd = None
        try:
            process = subprocess.Popen(
                wrapped,
                pass_fds=(
                    *inherited,
                    lifeline_read,
                    ready_child.fileno(),
                    parent_pidfd,
                    environment_fd,
                ),
                start_new_session=True,
                **kwargs,
            )
            os.close(lifeline_read)
            lifeline_read = -1
            os.close(parent_pidfd)
            parent_pidfd = -1
            os.close(environment_fd)
            environment_fd = -1
            ready_child.close()
            if not select.select(
                [ready_parent], [], [], _LINUX_STARTUP_TIMEOUT_SECONDS
            )[0]:
                raise ProcessContainmentUnavailable(
                    "timed out waiting for Linux namespace-init ownership handshake"
                )
            message, ancillary, _flags, _address = ready_parent.recvmsg(
                1,
                socket.CMSG_SPACE(array.array("i").itemsize)
                + socket.CMSG_SPACE(struct.calcsize("3i")),
                getattr(socket, "MSG_CMSG_CLOEXEC", 0),
            )
            received = array.array("i")
            sender_pid = None
            for level, kind, data in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    received.frombytes(data[: len(data) - (len(data) % received.itemsize)])
                if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
                    sender_pid, _sender_uid, _sender_gid = struct.unpack(
                        "3i", data[: struct.calcsize("3i")]
                    )
            if message != b"R" or len(received) != 1 or sender_pid is None:
                for descriptor in received:
                    os.close(descriptor)
                raise ProcessContainmentUnavailable(
                    "invalid Linux namespace-init ownership handshake"
                )
            init_pidfd = received[0]
            os.set_inheritable(init_pidfd, False)
            self._verify_linux_namespace_init(init_pidfd, sender_pid)
            if process.poll() is not None:
                raise ProcessContainmentUnavailable(
                    "Linux containment monitor exited before payload release"
                )
            os.write(lifeline_write, b"G")
            self._linux_init_pidfd = init_pidfd
            self._linux_lifeline = lifeline_write
            self._linux_status_socket = ready_parent
            ready_parent = None
            self._owned_pid = process.pid
            self._process = process
            return process
        except BaseException:
            os.close(lifeline_write)
            lifeline_write = -1
            if init_pidfd is not None:
                try:
                    signal.pidfd_send_signal(init_pidfd, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
            if process is not None:
                if process.poll() is None:
                    process.kill()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
            if init_pidfd is not None:
                if not select.select([init_pidfd], [], [], 1.0)[0]:
                    self._linux_init_pidfd = init_pidfd
                    self._process = process
                    self._owned_pid = process.pid if process is not None else None
                    init_pidfd = None
                    raise RuntimeError(
                        "Linux namespace init survived failed startup cleanup"
                    )
                os.close(init_pidfd)
            raise
        finally:
            if lifeline_read >= 0:
                os.close(lifeline_read)
            if parent_pidfd >= 0:
                os.close(parent_pidfd)
            if environment_fd >= 0:
                os.close(environment_fd)
            if ready_parent is not None:
                ready_parent.close()
            ready_child.close()

    def finish(
        self,
        process: subprocess.Popen[bytes],
        *,
        grace_seconds: float,
        forced: bool = False,
    ) -> int | None:
        """Clean up the owned tree and return the contained payload's status.

        The launcher/monitor status is deliberately not used as the payload
        result.  Forced cleanup may prevent namespace init from reporting a
        terminal payload status, so that case returns ``None``.
        """

        with self._finish_lock:
            return self._finish_locked(
                process, grace_seconds=grace_seconds, forced=forced
            )

    def _finish_locked(
        self,
        process: subprocess.Popen[bytes],
        *,
        grace_seconds: float,
        forced: bool,
    ) -> int | None:
        if process.pid != self._owned_pid:
            raise RuntimeError("refusing to finish an unregistered process")
        if self._payload_status_finished:
            if self._payload_returncode is None and not forced:
                raise RuntimeError("contained payload status was unavailable")
            return self._payload_returncode
        if os.name == "nt":
            if forced:
                self.terminate(process, grace_seconds=grace_seconds)
            else:
                self.ensure_tree_exited(process, grace_seconds=grace_seconds)
            self._payload_returncode = process.returncode
            self._payload_status_finished = True
            return self._payload_returncode
        if forced:
            self._terminate_linux(process, grace_seconds=grace_seconds)
            self._payload_returncode = self._read_linux_payload_status(required=False)
            self._payload_status_finished = True
            return self._payload_returncode
        if process.poll() is None:
            raise RuntimeError("contained process monitor has not exited")
        self.ensure_tree_exited(process, grace_seconds=grace_seconds)
        self._payload_returncode = self._read_linux_payload_status(required=True)
        self._payload_status_finished = True
        return self._payload_returncode

    def _read_linux_payload_status(self, *, required: bool) -> int | None:
        channel = self._linux_status_socket
        if channel is None:
            if required:
                raise RuntimeError("missing Linux payload-status channel")
            return None
        record = bytearray()
        try:
            # Normal finish has already proved namespace init (the only peer)
            # exited, so a stream socket now contains the complete frame and
            # EOF.  Forced finish provides the same proof before reading.
            channel.setblocking(False)
            while len(record) < 6:
                try:
                    chunk = channel.recv(6 - len(record))
                except BlockingIOError:
                    break
                if not chunk:
                    break
                record.extend(chunk)
        finally:
            channel.close()
            self._linux_status_socket = None
        if not record and not required:
            return None
        if len(record) != 5 or record[:1] != b"S":
            raise RuntimeError("missing or malformed Linux payload status")
        wait_status = struct.unpack("!I", record[1:])[0]
        if wait_status > 0xFFFF or not (
            os.WIFEXITED(wait_status) or os.WIFSIGNALED(wait_status)
        ):
            raise RuntimeError("invalid Linux payload wait status")
        return os.waitstatus_to_exitcode(wait_status)

    @staticmethod
    def _verify_linux_namespace_init(pidfd: int, sender_pid: int) -> None:
        if select.select([pidfd], [], [], 0)[0]:
            raise ProcessContainmentUnavailable(
                "Linux namespace init exited during ownership handshake"
            )
        try:
            with open(f"/proc/self/fdinfo/{pidfd}", encoding="ascii") as stream:
                fdinfo = stream.read().splitlines()
            pid_line = next(line for line in fdinfo if line.startswith("Pid:"))
            pidfd_pid = int(pid_line.partition(":")[2].strip())
            with open(f"/proc/{sender_pid}/status", encoding="ascii") as stream:
                status = stream.read().splitlines()
            nspid_line = next(line for line in status if line.startswith("NSpid:"))
            namespace_pids = tuple(
                map(int, nspid_line.partition(":")[2].strip().split())
            )
        except (OSError, StopIteration, ValueError) as exc:
            raise ProcessContainmentUnavailable(
                "could not verify Linux namespace-init identity"
            ) from exc
        if (
            pidfd_pid != sender_pid
            or not namespace_pids
            or namespace_pids[-1] != 1
        ):
            raise ProcessContainmentUnavailable(
                "Linux ownership handshake did not identify a new PID-namespace init"
            )

    def terminate(
        self, process: subprocess.Popen[bytes], *, grace_seconds: float
    ) -> None:
        if process.pid != self._owned_pid:
            raise RuntimeError("refusing to terminate an unregistered process")
        if os.name == "posix":
            self._terminate_linux(process, grace_seconds=grace_seconds)
            return
        assert self._windows_job is not None
        self._windows_job.terminate(1)
        self._wait_for_windows_job_exit(process, timeout=grace_seconds)

    def ensure_tree_exited(
        self, process: subprocess.Popen[bytes], *, grace_seconds: float
    ) -> None:
        """Terminate the owned tree and verify that no live member survives."""

        if process.pid != self._owned_pid:
            raise RuntimeError("refusing to inspect an unregistered process")
        if os.name == "nt":
            assert self._windows_job is not None
            self._windows_job.terminate(0)
            self._wait_for_windows_job_exit(process, timeout=grace_seconds)
            return
        self._terminate_linux(process, grace_seconds=grace_seconds)

    def _wait_for_windows_job_exit(
        self, process: subprocess.Popen[bytes], *, timeout: float
    ) -> None:
        assert self._windows_job is not None
        deadline = time.monotonic() + timeout
        while True:
            leader_exited = process.poll() is not None
            active_processes = self._windows_job.active_process_count()
            if leader_exited and active_processes == 0:
                return
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(process.args, timeout)
            time.sleep(0.02)

    def _terminate_linux(
        self, process: subprocess.Popen[bytes], *, grace_seconds: float
    ) -> None:
        pidfd = self._linux_init_pidfd
        if pidfd is None or process is not self._process:
            raise RuntimeError("refusing to signal an unverified namespace init")
        try:
            signal.pidfd_send_signal(pidfd, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self._wait_for_linux_exit(process, timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            signal.pidfd_send_signal(pidfd, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self._wait_for_linux_exit(process, timeout=grace_seconds)

    def _wait_for_linux_exit(
        self, process: subprocess.Popen[bytes], *, timeout: float
    ) -> None:
        pidfd = self._linux_init_pidfd
        if pidfd is None or process is not self._process:
            raise RuntimeError("refusing to inspect an unverified namespace init")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            init_exited = bool(select.select([pidfd], [], [], 0)[0])
            monitor_exited = process.poll() is not None
            if init_exited and monitor_exited:
                return
            time.sleep(0.02)
        raise subprocess.TimeoutExpired(process.args, timeout)

    def close(self) -> None:
        with self._finish_lock:
            self._close_locked()

    def _close_locked(self) -> None:
        process = self._process
        if process is not None and not self._payload_status_finished:
            if process.pid != self._owned_pid:
                raise RuntimeError("owned process identity changed before close")
            # Preserve the same cleanup proof as finish(): closing ownership
            # handles first could make a later caller mistake unavailable
            # descriptors for a successfully quiesced process tree.
            self._finish_locked(process, grace_seconds=1.0, forced=True)
        if self._linux_lifeline is not None:
            os.close(self._linux_lifeline)
            self._linux_lifeline = None
        if self._linux_status_socket is not None:
            self._linux_status_socket.close()
            self._linux_status_socket = None
        if self._linux_init_pidfd is not None:
            if process is None and not select.select(
                [self._linux_init_pidfd], [], [], 0
            )[0]:
                raise RuntimeError(
                    "cannot verify live namespace init without its monitor"
                )
            os.close(self._linux_init_pidfd)
            self._linux_init_pidfd = None
        if self._windows_job is not None:
            self._windows_job.close()


class WindowsJobObject:
    def __init__(self, handle: object, kernel32: object) -> None:
        self.handle, self.kernel32 = (handle, kernel32)

    @classmethod
    def create(cls) -> "WindowsJobObject":
        import ctypes
        from ctypes import wintypes

        class IO(ctypes.Structure):
            _fields_ = [
                (n, ctypes.c_uint64)
                for n in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class BASIC(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class EXT(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC),
                ("IoInfo", IO),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        k.SetInformationJobObject.restype = wintypes.BOOL
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.AssignProcessToJobObject.restype = wintypes.BOOL
        k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k.TerminateJobObject.restype = wintypes.BOOL
        k.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        k.QueryInformationJobObject.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.ResumeThread.argtypes = [wintypes.HANDLE]
        k.ResumeThread.restype = wintypes.DWORD
        k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k.Thread32First.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        k.Thread32First.restype = wintypes.BOOL
        k.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        k.Thread32Next.restype = wintypes.BOOL
        k.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenThread.restype = wintypes.HANDLE
        h = k.CreateJobObjectW(None, None)
        if not h:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        info = EXT()
        info.BasicLimitInformation.LimitFlags = 8192
        if not k.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.get_last_error()
            k.CloseHandle(h)
            raise OSError(error, "SetInformationJobObject failed")
        return cls(h, k)

    def assign_and_resume(self, process: subprocess.Popen[bytes]) -> None:
        import ctypes

        if not self.kernel32.AssignProcessToJobObject(
            self.handle, int(process._handle)
        ):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        self._resume_process_threads(process.pid)

    def _resume_process_threads(self, process_id: int) -> None:
        import ctypes
        from ctypes import wintypes

        class THREADENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
            ]

        snapshot = self.kernel32.CreateToolhelp32Snapshot(4, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
        resumed = 0
        try:
            entry = THREADENTRY32()
            entry.dwSize = ctypes.sizeof(entry)
            ok = self.kernel32.Thread32First(snapshot, ctypes.byref(entry))
            while ok:
                if entry.th32OwnerProcessID == process_id:
                    thread = self.kernel32.OpenThread(2, False, entry.th32ThreadID)
                    if thread:
                        try:
                            if self.kernel32.ResumeThread(thread) != 4294967295:
                                resumed += 1
                        finally:
                            self.kernel32.CloseHandle(thread)
                ok = self.kernel32.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            self.kernel32.CloseHandle(snapshot)
        if resumed == 0:
            raise OSError("no suspended process thread could be resumed")

    def terminate(self, code: int) -> None:
        if not self.kernel32.TerminateJobObject(self.handle, code):
            import ctypes

            raise OSError(ctypes.get_last_error(), "TerminateJobObject failed")

    def active_process_count(self) -> int:
        import ctypes
        from ctypes import wintypes

        class BASIC_ACCOUNTING(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_int64),
                ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64),
                ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            ]

        info = BASIC_ACCOUNTING()
        returned = wintypes.DWORD()
        if not self.kernel32.QueryInformationJobObject(
            self.handle,
            1,  # JobObjectBasicAccountingInformation
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(returned),
        ):
            raise OSError(ctypes.get_last_error(), "QueryInformationJobObject failed")
        return int(info.ActiveProcesses)

    def close(self) -> None:
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None


__all__ = [
    "ProcessContainment",
    "ProcessContainmentUnavailable",
    "WindowsJobObject",
]
