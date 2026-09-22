"""Portable owned-process-tree containment primitives."""

from __future__ import annotations
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ProcessContainment:
    creation_kwargs: dict[str, Any]
    _windows_job: "WindowsJobObject | None" = None
    _owned_pid: int | None = None
    _owned_pgid: int | None = None

    @classmethod
    def create(cls) -> "ProcessContainment":
        if os.name == "posix":
            return cls({"start_new_session": True})
        if os.name == "nt":
            return cls(
                {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | 4},
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

    def terminate(
        self, process: subprocess.Popen[bytes], *, grace_seconds: float
    ) -> None:
        if process.pid != self._owned_pid:
            raise RuntimeError("refusing to terminate an unregistered process")
        if os.name == "posix":
            self._terminate_posix_group(process, grace_seconds=grace_seconds)
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
        process_group = self._owned_pgid
        if (
            process_group is None
            or process_group != process.pid
            or process_group == os.getpgrp()
        ):
            raise RuntimeError("refusing to inspect an unverified process group")
        self._terminate_posix_group(process, grace_seconds=grace_seconds)

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
            process.poll()
            return
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            process.poll()
            if not self._posix_group_has_live_processes(process_group):
                return
            time.sleep(0.02)
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            process.poll()
            return
        kill_deadline = time.monotonic() + grace_seconds
        while time.monotonic() < kill_deadline:
            process.poll()
            if not self._posix_group_has_live_processes(process_group):
                return
            time.sleep(0.02)
        raise subprocess.TimeoutExpired(process.args, grace_seconds)

    @staticmethod
    def _posix_group_has_live_processes(process_group: int) -> bool:
        """Return whether a group has a non-zombie member.

        Linux can leave orphaned zombies visible in a process group until its
        subreaper collects them.  They cannot execute effects and must not turn
        successful containment into permanent uncertainty.  Other POSIX
        platforms fall back to the portable group-existence probe.
        """

        proc = "/proc"
        if os.path.isdir(proc):
            try:
                entries = os.scandir(proc)
            except OSError:
                entries = None
            if entries is not None:
                scan_uncertain = False
                with entries:
                    for entry in entries:
                        if not entry.name.isdigit():
                            continue
                        try:
                            with open(
                                os.path.join(entry.path, "stat"),
                                encoding="utf-8",
                            ) as handle:
                                raw_stat = handle.read()
                            # comm is parenthesized and may itself contain spaces.
                            stat_fields = raw_stat[raw_stat.rindex(")") + 2 :].split()
                            state = stat_fields[0]
                            member_group = int(stat_fields[2])
                        except FileNotFoundError:
                            continue
                        except (OSError, ValueError, IndexError):
                            scan_uncertain = True
                            continue
                        if member_group == process_group and state != "Z":
                            return True
                if not scan_uncertain:
                    return False
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return False
        return True

    def close(self) -> None:
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


__all__ = ["ProcessContainment", "WindowsJobObject"]
