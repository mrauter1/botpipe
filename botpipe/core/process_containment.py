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
        process_group = os.getpgid(process.pid)
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
        if process.poll() is None:
            process.wait(timeout=grace_seconds)

    def ensure_tree_exited(
        self, process: subprocess.Popen[bytes], *, grace_seconds: float
    ) -> None:
        """Wait briefly for owned descendants, then terminate any survivors."""

        if process.pid != self._owned_pid:
            raise RuntimeError("refusing to inspect an unregistered process")
        if os.name == "nt":
            # Closing or terminating the owned Job is the reliable descendant check.
            assert self._windows_job is not None
            self._windows_job.terminate(0)
            return
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
                return
            time.sleep(0.02)
        self._terminate_posix_group(process, grace_seconds=grace_seconds)

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
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            process.poll()
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.poll() is None:
            process.wait(timeout=grace_seconds)

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
        self.kernel32.TerminateJobObject(self.handle, code)

    def close(self) -> None:
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None


__all__ = ["ProcessContainment", "WindowsJobObject"]
