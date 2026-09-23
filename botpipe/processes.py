"""Portable owned-process-tree containment primitives."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any


class ProcessCleanupError(RuntimeError):
    """Owned process cleanup ran, but descendant inspection was incomplete."""


def _posix_processes() -> dict[int, tuple[int, int, str, str]]:
    """Return pid -> (ppid, pgid, state, stable process identity)."""

    snapshot = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,pgid=,stat=,lstart="],
        check=True,
        capture_output=True,
        text=True,
        timeout=0.5,
    )
    processes = {}
    for line in snapshot.stdout.splitlines():
        fields = line.split(None, 4)
        if len(fields) != 5:
            continue
        try:
            pid, ppid, pgid = map(int, fields[:3])
        except ValueError:
            continue
        identity = fields[4]
        if os.path.exists(f"/proc/{pid}/stat"):
            try:
                # Linux field 22 is the kernel start tick and survives renames.
                with open(f"/proc/{pid}/stat", "rb") as proc_stat:
                    tail = proc_stat.read().rsplit(b") ", 1)[1]
                identity = f"linux:{tail.split()[19].decode('ascii')}"
            except FileNotFoundError:
                # The process exited between ps and procfs inspection.
                continue
            except (OSError, IndexError, UnicodeDecodeError) as exc:
                raise OSError(f"could not identify process {pid} from procfs") from exc
        processes[pid] = (ppid, pgid, fields[3], identity)
    return processes


def _posix_group_is_quiescent(process_group: int) -> bool:
    """Confirm that a group contains no process that can still execute."""

    try:
        snapshot = subprocess.run(
            ["ps", "-axo", "pid=,pgid=,stat="],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    for line in snapshot.stdout.splitlines():
        fields = line.split(None, 2)
        if len(fields) != 3:
            continue
        try:
            member_group = int(fields[1])
        except ValueError:
            continue
        if member_group == process_group and fields[2][:1] not in {"X", "Z"}:
            return False
    return True


@dataclass(slots=True)
class ProcessContainment:
    creation_kwargs: dict[str, Any]
    _windows_job: WindowsJobObject | None = None
    _owned_pid: int | None = None
    _owned_pgid: int | None = None
    _descendant_groups: dict[int, dict[int, str]] = field(default_factory=dict)
    _inspection_errors: list[str] = field(default_factory=list)

    def _inspection_failed(self, operation: str, exc: BaseException) -> None:
        self._inspection_errors.append(f"{operation}: {exc}")

    def _raise_if_unverified(self) -> None:
        if self._inspection_errors:
            detail = "; ".join(dict.fromkeys(self._inspection_errors))
            raise ProcessCleanupError(
                "process-tree cleanup could not be verified because inspection failed: "
                + detail
            )

    @classmethod
    def create(cls) -> ProcessContainment:
        if os.name == "posix":
            return cls({"start_new_session": True})
        if os.name == "nt":
            return cls(
                {
                    "creationflags": getattr(
                        subprocess, "CREATE_NEW_PROCESS_GROUP", 512
                    )
                    | 4
                },
                WindowsJobObject.create(),
            )
        raise RuntimeError(f"process-tree containment unavailable on {os.name!r}")

    def attach_and_start(self, process: subprocess.Popen[bytes]) -> None:
        if self._windows_job is not None:
            self._windows_job.assign_and_resume(process)
            self._owned_pid = process.pid
            return
        try:
            process_group = os.getpgid(process.pid)
        except ProcessLookupError:
            # start_new_session happens before exec; a very short child can
            # already have exited by the time Popen returns.
            process_group = process.pid
        if process_group != process.pid or process_group == os.getpgrp():
            raise RuntimeError("subprocess did not enter its own process group")
        self._owned_pid = process.pid
        self._owned_pgid = process_group

    def capture_descendant_groups(self, process: subprocess.Popen[bytes]) -> None:
        """Remember attached descendant groups before native cleanup reparents them."""

        if (
            os.name != "posix"
            or process.pid != self._owned_pid
            or process.poll() is not None
        ):
            return
        try:
            if os.getpgid(process.pid) != self._owned_pgid:
                return
        except ProcessLookupError:
            return
        except OSError as exc:
            self._inspection_failed("inspect owned process group", exc)
            return
        try:
            processes = _posix_processes()
        except (OSError, subprocess.SubprocessError) as exc:
            self._inspection_failed("snapshot descendants", exc)
            return
        descendants = {process.pid}
        changed = True
        while changed:
            changed = False
            for pid, (ppid, _pgid, _state, _identity) in processes.items():
                if pid not in descendants and ppid in descendants:
                    descendants.add(pid)
                    changed = True
        for pid in descendants - {process.pid}:
            _ppid, pgid, state, identity = processes[pid]
            if pgid != self._owned_pgid and state[:1] not in {"X", "Z"}:
                self._descendant_groups.setdefault(pgid, {})[pid] = identity

    def _signal_descendant_groups(self, sig: signal.Signals) -> None:
        if not self._descendant_groups:
            return
        try:
            processes = _posix_processes()
        except (OSError, subprocess.SubprocessError) as exc:
            self._inspection_failed("verify descendant identities", exc)
            return
        finished = set()
        for pgid, witnesses in self._descendant_groups.items():
            # A live member with the captured start identity prevents signalling
            # a group whose numeric ID was reused after cleanup.
            if not any(
                pid in processes
                and processes[pid][1] == pgid
                and processes[pid][2][:1] not in {"X", "Z"}
                and processes[pid][3] == identity
                for pid, identity in witnesses.items()
            ):
                finished.add(pgid)
                continue
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                finished.add(pgid)
            else:
                if sig == signal.SIGKILL:
                    finished.add(pgid)
        for pgid in finished:
            self._descendant_groups.pop(pgid, None)

    def terminate(
        self, process: subprocess.Popen[bytes], *, grace_seconds: float = 10.0
    ) -> None:
        if process.pid != self._owned_pid:
            raise RuntimeError("refusing to terminate an unregistered process")
        if os.name == "posix":
            self._signal_descendant_groups(signal.SIGTERM)
            self._terminate_posix_group(process, grace_seconds=grace_seconds)
            self._signal_descendant_groups(signal.SIGKILL)
            self._raise_if_unverified()
            return
        assert self._windows_job is not None
        self._windows_job.terminate(1)
        if process.poll() is None:
            process.wait(timeout=grace_seconds)

    def ensure_tree_exited(
        self, process: subprocess.Popen[bytes], *, grace_seconds: float = 10.0
    ) -> None:
        """Wait briefly for owned descendants, then terminate any survivors."""

        if process.pid != self._owned_pid:
            raise RuntimeError("refusing to inspect an unregistered process")
        if os.name == "nt":
            # Closing or terminating the owned Job is the reliable descendant check.
            assert self._windows_job is not None
            self._windows_job.terminate(0)
            return
        self._signal_descendant_groups(signal.SIGTERM)
        process_group = self._owned_pgid
        if (
            process_group is None
            or process_group != process.pid
            or process_group == os.getpgrp()
        ):
            raise RuntimeError("refusing to inspect an unverified process group")
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            process.poll()
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                self._signal_descendant_groups(signal.SIGKILL)
                self._raise_if_unverified()
                return
            except PermissionError:
                if _posix_group_is_quiescent(process_group):
                    self._signal_descendant_groups(signal.SIGKILL)
                    self._raise_if_unverified()
                    return
                raise
            time.sleep(0.02)
        self._terminate_posix_group(process, grace_seconds=grace_seconds)
        self._signal_descendant_groups(signal.SIGKILL)
        self._raise_if_unverified()

    def _terminate_posix_group(
        self, process: subprocess.Popen[bytes], *, grace_seconds: float
    ) -> None:
        process_group = self._owned_pgid
        if (
            process_group is None
            or process_group != process.pid
            or process_group == os.getpgrp()
        ):
            raise RuntimeError("refusing to signal an unverified process group")
        try:
            current_process_group = os.getpgid(process.pid)
        except ProcessLookupError:
            current_process_group = None
        if current_process_group is not None and current_process_group != process_group:
            raise RuntimeError(
                "registered process ID now belongs to another process group"
            )
        try:
            os.killpg(process_group, signal.SIGTERM)
        except ProcessLookupError:
            return
        except PermissionError:
            if _posix_group_is_quiescent(process_group):
                process.poll()
                return
            raise
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            process.poll()
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                break
            except PermissionError:
                if _posix_group_is_quiescent(process_group):
                    break
                raise
            time.sleep(0.02)
        else:
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                if not _posix_group_is_quiescent(process_group):
                    raise
        if process.poll() is None:
            process.wait(timeout=grace_seconds)

    def close(self) -> None:
        if self._windows_job is not None:
            self._windows_job.close()


class WindowsJobObject:
    def __init__(self, handle: Any, kernel32: Any) -> None:
        self.handle, self.kernel32 = (handle, kernel32)

    @classmethod
    def create(cls) -> WindowsJobObject:
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

        ctypes_api: Any = ctypes
        k = ctypes_api.WinDLL("kernel32", use_last_error=True)
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
            raise OSError(ctypes_api.get_last_error(), "CreateJobObjectW failed")
        info = EXT()
        info.BasicLimitInformation.LimitFlags = 8192
        if not k.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes_api.get_last_error()
            k.CloseHandle(h)
            raise OSError(error, "SetInformationJobObject failed")
        return cls(h, k)

    def assign_and_resume(self, process: subprocess.Popen[bytes]) -> None:
        import ctypes

        ctypes_api: Any = ctypes
        process_api: Any = process
        if not self.kernel32.AssignProcessToJobObject(
            self.handle, int(process_api._handle)
        ):
            raise OSError(
                ctypes_api.get_last_error(), "AssignProcessToJobObject failed"
            )
        self._resume_process_threads(process.pid)

    def _resume_process_threads(self, process_id: int) -> None:
        import ctypes
        from ctypes import wintypes

        ctypes_api: Any = ctypes

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
            raise OSError(
                ctypes_api.get_last_error(), "CreateToolhelp32Snapshot failed"
            )
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

            ctypes_api: Any = ctypes
            raise OSError(ctypes_api.get_last_error(), "TerminateJobObject failed")

    def close(self) -> None:
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None


__all__ = ["ProcessCleanupError", "ProcessContainment", "WindowsJobObject"]
