"""Bounded subprocess execution with owned descendant containment."""
from __future__ import annotations
import subprocess, threading, time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from botpipe.core.process_containment import ProcessContainment

DEFAULT_MAX_STREAM_BYTES=1024*1024
DEFAULT_TERMINATION_GRACE_SECONDS=5.0

@dataclass(frozen=True,slots=True)
class ProcessResult:
    argv: tuple[str,...]; exit_code:int|None; timed_out:bool; cancelled:bool; elapsed_seconds:float
    stdout:str; stderr:str; stdout_truncated:bool; stderr_truncated:bool
    def to_dict(self,*,phase:str|None=None)->dict[str,object]:
        value={"argv":list(self.argv),"exit_code":self.exit_code,"timed_out":self.timed_out,"cancelled":self.cancelled,"elapsed_seconds":self.elapsed_seconds,"stdout":self.stdout,"stderr":self.stderr,"stdout_truncated":self.stdout_truncated,"stderr_truncated":self.stderr_truncated}
        if phase is not None:value["phase"]=phase
        return value

class _Tail:
    def __init__(self,limit:int):self.limit=limit;self.parts:deque[bytes]=deque();self.size=0;self.truncated=False
    def append(self,data:bytes)->None:
        self.parts.append(data);self.size+=len(data)
        while self.size>self.limit:
            over=self.size-self.limit; head=self.parts[0]
            if len(head)<=over:self.parts.popleft();self.size-=len(head)
            else:self.parts[0]=head[over:];self.size-=over
            self.truncated=True
    def text(self)->str:return b"".join(self.parts).decode("utf-8",errors="replace")

def run_bounded_process(argv:Sequence[str],*,cwd:Path,timeout_seconds:float,max_stream_bytes:int=DEFAULT_MAX_STREAM_BYTES,termination_grace_seconds:float=DEFAULT_TERMINATION_GRACE_SECONDS,env:Mapping[str,str]|None=None,cancel_requested:Callable[[],bool]|None=None)->ProcessResult:
    if isinstance(argv,(str,bytes)) or not argv or any(not isinstance(v,str) or not v or "\0" in v for v in argv):raise ValueError("argv must be a non-empty sequence of valid strings")
    if timeout_seconds<=0 or termination_grace_seconds<=0:raise ValueError("timeouts must be positive")
    if isinstance(max_stream_bytes,bool) or not isinstance(max_stream_bytes,int) or max_stream_bytes<=0:raise ValueError("max_stream_bytes must be positive")
    root=Path(cwd).resolve(strict=True)
    if not root.is_dir():raise ValueError("cwd must be a directory")
    containment=ProcessContainment.create(); started=time.monotonic()
    process=subprocess.Popen(list(argv),cwd=root,env=None if env is None else dict(env),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=False,**containment.creation_kwargs)
    try:
        try:containment.attach_and_start(process)
        except BaseException:process.kill();process.wait();raise
        out,err=_Tail(max_stream_bytes),_Tail(max_stream_bytes)
        readers=[threading.Thread(target=_drain,args=(process.stdout,out),daemon=True),threading.Thread(target=_drain,args=(process.stderr,err),daemon=True)]
        for reader in readers:reader.start()
        deadline=started+timeout_seconds;timed_out=cancelled=False
        while process.poll() is None:
            if cancel_requested is not None and cancel_requested():cancelled=True;break
            if time.monotonic()>=deadline:timed_out=True;break
            time.sleep(min(.05,max(0,deadline-time.monotonic())))
        if timed_out or cancelled:containment.terminate(process,grace_seconds=termination_grace_seconds)
        else:process.wait()
        for reader in readers:reader.join(timeout=termination_grace_seconds)
        return ProcessResult(tuple(argv),process.returncode,timed_out,cancelled,max(0,time.monotonic()-started),out.text(),err.text(),out.truncated,err.truncated)
    except BaseException:
        if process.poll() is None:containment.terminate(process,grace_seconds=termination_grace_seconds)
        raise
    finally:containment.close()

def _drain(stream:BinaryIO|None,tail:_Tail)->None:
    if stream is None:return
    try:
        for chunk in iter(lambda:stream.read(65536),b""):tail.append(chunk)
    finally:stream.close()

__all__=["DEFAULT_MAX_STREAM_BYTES","DEFAULT_TERMINATION_GRACE_SECONDS","ProcessResult","run_bounded_process"]
