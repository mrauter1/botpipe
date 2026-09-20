"""Portable owned-process-tree containment primitives."""
from __future__ import annotations
import os, signal, subprocess
from dataclasses import dataclass
from typing import Any

@dataclass(slots=True)
class ProcessContainment:
    creation_kwargs: dict[str, Any]
    _windows_job: "WindowsJobObject | None" = None

    @classmethod
    def create(cls) -> "ProcessContainment":
        if os.name == "posix":
            return cls({"start_new_session": True})
        if os.name == "nt":  # pragma: no cover
            return cls({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | 0x4}, WindowsJobObject.create())
        raise RuntimeError(f"process-tree containment unavailable on {os.name!r}")

    def attach_and_start(self, process: subprocess.Popen[bytes]) -> None:
        if self._windows_job is not None:
            self._windows_job.assign_and_resume(process)

    def terminate(self, process: subprocess.Popen[bytes], *, grace_seconds: float) -> None:
        if process.poll() is not None: return
        if os.name == "posix":
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
        else: self._windows_job.terminate(1)  # type: ignore[union-attr]
        try:
            process.wait(timeout=grace_seconds); return
        except subprocess.TimeoutExpired: pass
        if os.name == "posix":
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        else: self._windows_job.terminate(1)  # type: ignore[union-attr]
        process.wait(timeout=grace_seconds)

    def close(self) -> None:
        if self._windows_job is not None: self._windows_job.close()

class WindowsJobObject:
    def __init__(self, handle: object, kernel32: object) -> None: self.handle, self.kernel32 = handle, kernel32
    @classmethod
    def create(cls) -> "WindowsJobObject":  # pragma: no cover
        import ctypes
        from ctypes import wintypes
        class IO(ctypes.Structure):
            _fields_=[(n,ctypes.c_uint64) for n in ("ReadOperationCount","WriteOperationCount","OtherOperationCount","ReadTransferCount","WriteTransferCount","OtherTransferCount")]
        class BASIC(ctypes.Structure):
            _fields_=[("PerProcessUserTimeLimit",ctypes.c_int64),("PerJobUserTimeLimit",ctypes.c_int64),("LimitFlags",wintypes.DWORD),("MinimumWorkingSetSize",ctypes.c_size_t),("MaximumWorkingSetSize",ctypes.c_size_t),("ActiveProcessLimit",wintypes.DWORD),("Affinity",ctypes.c_size_t),("PriorityClass",wintypes.DWORD),("SchedulingClass",wintypes.DWORD)]
        class EXT(ctypes.Structure):
            _fields_=[("BasicLimitInformation",BASIC),("IoInfo",IO),("ProcessMemoryLimit",ctypes.c_size_t),("JobMemoryLimit",ctypes.c_size_t),("PeakProcessMemoryUsed",ctypes.c_size_t),("PeakJobMemoryUsed",ctypes.c_size_t)]
        k=ctypes.WinDLL("kernel32",use_last_error=True)
        k.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]; k.CreateJobObjectW.restype=wintypes.HANDLE
        k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]; k.SetInformationJobObject.restype=wintypes.BOOL
        k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]; k.AssignProcessToJobObject.restype=wintypes.BOOL
        k.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT]; k.TerminateJobObject.restype=wintypes.BOOL
        k.CloseHandle.argtypes=[wintypes.HANDLE]; k.CloseHandle.restype=wintypes.BOOL
        k.ResumeThread.argtypes=[wintypes.HANDLE]; k.ResumeThread.restype=wintypes.DWORD
        h=k.CreateJobObjectW(None,None)
        if not h: raise OSError(ctypes.get_last_error(),"CreateJobObjectW failed")
        info=EXT(); info.BasicLimitInformation.LimitFlags=0x2000
        if not k.SetInformationJobObject(h,9,ctypes.byref(info),ctypes.sizeof(info)):
            error=ctypes.get_last_error(); k.CloseHandle(h); raise OSError(error,"SetInformationJobObject failed")
        return cls(h,k)
    def assign_and_resume(self, process: subprocess.Popen[bytes]) -> None:  # pragma: no cover
        import ctypes
        if not self.kernel32.AssignProcessToJobObject(self.handle,int(process._handle)): raise OSError(ctypes.get_last_error(),"AssignProcessToJobObject failed")
        if self.kernel32.ResumeThread(int(process._thread)) == 0xFFFFFFFF: raise OSError(ctypes.get_last_error(),"ResumeThread failed")
    def terminate(self, code: int) -> None: self.kernel32.TerminateJobObject(self.handle,code)  # pragma: no cover
    def close(self) -> None:  # pragma: no cover
        if self.handle: self.kernel32.CloseHandle(self.handle); self.handle=None

__all__=["ProcessContainment","WindowsJobObject"]
