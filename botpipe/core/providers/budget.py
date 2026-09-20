"""Optional persistent limits for rendered provider dispatches."""
from __future__ import annotations
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
import math, threading, time
from typing import Any
from uuid import uuid4
from ..errors import FailureContext, ProviderExecutionError
BudgetCheckpoint = Callable[[Mapping[str, Any]], None]
class ProviderBudgetExhausted(ProviderExecutionError): pass
class ProviderBudgetResumeError(ValueError): pass
@dataclass(frozen=True, slots=True)
class ProviderDispatchReservation:
    dispatch_id: str
    sequence: int
    timeout_seconds: float | None
def _utc_now(): return datetime.now(timezone.utc)
def _parse_utc(value: str, field: str) -> datetime:
    try: parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc: raise ProviderBudgetResumeError(f'{field} must be an ISO-8601 timestamp') from exc
    if parsed.tzinfo is None: raise ProviderBudgetResumeError(f'{field} must include a UTC offset')
    return parsed.astimezone(timezone.utc)
class ProviderDispatchBudget:
    def __init__(self, max_turns: int, *, timeout_seconds: float|None=None, deadline_utc: str|datetime|None=None,
                 state: Mapping[str,Any]|None=None, checkpoint: BudgetCheckpoint|None=None,
                 wall_clock: Callable[[],datetime]=_utc_now, monotonic_clock: Callable[[],float]=time.monotonic):
        if isinstance(max_turns,bool) or not isinstance(max_turns,int) or max_turns<=0: raise ValueError('max_turns must be a positive integer')
        if timeout_seconds is not None and (not math.isfinite(timeout_seconds) or timeout_seconds<=0): raise ValueError('timeout_seconds must be positive and finite')
        self.max_turns=max_turns; self.timeout_seconds=None if timeout_seconds is None else float(timeout_seconds); self._checkpoint=checkpoint
        self._wall_clock=wall_clock; self._monotonic_clock=monotonic_clock; self._lock=threading.Lock()
        now=wall_clock().astimezone(timezone.utc); self._started_monotonic=monotonic_clock(); saved=dict(state or {})
        if saved and saved.get('timeout_seconds') != self.timeout_seconds: raise ProviderBudgetResumeError('provider turn timeout changed across resume')
        if saved.get('max_turns',max_turns)!=max_turns: raise ProviderBudgetResumeError('provider dispatch budget max_turns changed across resume')
        used=saved.get('used_turns',0)
        if isinstance(used,bool) or not isinstance(used,int) or used<0: raise ProviderBudgetResumeError('used_turns must be a non-negative integer')
        self.used_turns=used
        requested=deadline_utc
        if isinstance(requested,datetime):
            if requested.tzinfo is None: raise ValueError('deadline_utc must be timezone-aware')
            requested=requested.astimezone(timezone.utc).isoformat()
        raw=saved.get('deadline_utc',requested); self._deadline=_parse_utc(str(raw),'deadline_utc') if raw is not None else None
        if saved.get('deadline_utc') is not None and requested is not None and _parse_utc(str(requested),'deadline_utc')!=self._deadline: raise ProviderBudgetResumeError('provider dispatch deadline changed across resume')
        last=saved.get('last_observed_utc')
        if last is not None and now<_parse_utc(str(last),'last_observed_utc'): raise ProviderBudgetResumeError('wall clock moved backwards since the provider budget checkpoint')
        self._last_observed=now; ceiling=saved.get('remaining_seconds_ceiling')
        if ceiling is not None and (isinstance(ceiling,bool) or not isinstance(ceiling,(int,float)) or not math.isfinite(ceiling) or ceiling<0): raise ProviderBudgetResumeError('remaining_seconds_ceiling must be finite and non-negative')
        deadline_remaining=None if self._deadline is None else max(0.,(self._deadline-now).total_seconds())
        self._remaining_at_start=deadline_remaining if ceiling is None else float(ceiling) if deadline_remaining is None else min(float(ceiling),deadline_remaining)
    @classmethod
    def from_snapshot(cls,snapshot:Mapping[str,Any],*,checkpoint:BudgetCheckpoint|None=None,timeout_seconds:float|None=None):
        maximum=snapshot.get('max_turns')
        if isinstance(maximum,bool) or not isinstance(maximum,int): raise ProviderBudgetResumeError('budget snapshot is missing integer max_turns')
        return cls(maximum,timeout_seconds=timeout_seconds,state=snapshot,checkpoint=checkpoint)
    def _remaining_locked(self):
        now=self._wall_clock().astimezone(timezone.utc)
        if now<self._last_observed: raise ProviderBudgetResumeError('wall clock moved backwards while enforcing the provider deadline')
        self._last_observed=now; values=[]
        if self._deadline is not None: values.append(max(0.,(self._deadline-now).total_seconds()))
        if self._remaining_at_start is not None: values.append(max(0.,self._remaining_at_start-max(0.,self._monotonic_clock()-self._started_monotonic)))
        return min(values) if values else None
    def remaining_seconds(self):
        with self._lock: return self._remaining_locked()
    def reserve(self,*,configured_timeout:float|None=None):
        with self._lock:
            remaining=self._remaining_locked()
            if remaining is not None and remaining<=0: raise self._exhausted('provider dispatch deadline exhausted')
            if self.used_turns>=self.max_turns: raise self._exhausted(f'provider dispatch budget exhausted ({self.used_turns}/{self.max_turns} turns used)')
            self.used_turns+=1; candidates=[x for x in (configured_timeout,self.timeout_seconds,remaining) if x is not None]
            result=ProviderDispatchReservation(uuid4().hex,self.used_turns,min(candidates) if candidates else None); self._persist_locked(); return result
    def _snapshot_locked(self):
        remaining=self._remaining_locked(); return {'schema':'botpipe.provider-dispatch-budget.v1','max_turns':self.max_turns,'used_turns':self.used_turns,'timeout_seconds':self.timeout_seconds,'deadline_utc':None if self._deadline is None else self._deadline.isoformat(),'last_observed_utc':self._last_observed.isoformat(),'remaining_seconds_ceiling':remaining}
    def snapshot(self):
        with self._lock: return self._snapshot_locked()
    def checkpoint(self):
        with self._lock:
            value=self._snapshot_locked()
            if self._checkpoint: self._checkpoint(value)
            return value
    def _persist_locked(self):
        if self._checkpoint: self._checkpoint(self._snapshot_locked())
    @staticmethod
    def _exhausted(message): return ProviderBudgetExhausted(message,failure_context=FailureContext(kind='provider_budget_exhausted',step_name='',provider_attributable=False,details={'error':message}))
_ACTIVE: ContextVar[ProviderDispatchBudget|None]=ContextVar('botpipe_active_provider_dispatch_budget',default=None)
def current_provider_dispatch_budget(): return _ACTIVE.get()
@contextmanager
def activate_provider_dispatch_budget(budget):
    if not isinstance(budget,ProviderDispatchBudget): raise TypeError('budget must be a ProviderDispatchBudget')
    token: Token[ProviderDispatchBudget|None]=_ACTIVE.set(budget)
    try: yield budget
    finally: _ACTIVE.reset(token)
