"""One immutable telemetry identity per physical provider dispatch attempt."""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid

from .journal import now

_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)

_TOKEN_ALIASES = {
    "input_tokens": ("input_tokens", "prompt_tokens"),
    "output_tokens": ("output_tokens", "completion_tokens"),
}


def _token_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _aliased_token_count(usage, *fields):
    for field in fields:
        value = usage.get(field)
        if _token_count(value):
            return value
    return None


def known_token_total(usage, *, provider=None):
    """Return a reported total only when the field semantics determine one."""
    usage = usage or {}
    total = usage.get("total_tokens")
    if _token_count(total):
        return total
    input_tokens = _aliased_token_count(usage, "input_tokens", "prompt_tokens")
    output_tokens = _aliased_token_count(usage, "output_tokens", "completion_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    additive = ("cache_creation_input_tokens", "cache_read_input_tokens")
    present = [field for field in additive if field in usage]
    provider_name = str(provider or "").lower()
    if present and provider_name not in {"anthropic", "claude"}:
        return None
    cache_tokens = 0
    for field in present:
        value = usage[field]
        if not _token_count(value):
            return None
        cache_tokens += value
    # cached_input_tokens is an input subset and reasoning_tokens is an output
    # subset. Claude's cache creation/read fields are separate input categories.
    return input_tokens + output_tokens + cache_tokens


def normalize_usage(usage, *, final, provider=None):
    raw = usage or {}
    values = {
        key: value
        for key in _TOKEN_FIELDS
        if isinstance((value := raw.get(key)), (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    }
    for target, aliases in _TOKEN_ALIASES.items():
        for source in aliases:
            value = raw.get(source)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0
            ):
                values[target] = value
                break
    total = known_token_total(values, provider=provider)
    if total is not None:
        values["total_tokens"] = total
    availability = (
        "known_total"
        if final and total is not None
        else "partial"
        if values
        else "unknown"
    )
    return values, availability


class Dispatch:
    """Reserve once before effects; record start and terminal facts separately."""

    def __init__(self, provider, request):
        from .budgets import reserve_dispatch
        from .runtime import _CURRENT

        self.ctx = _CURRENT.get()
        self.provider_name = str(getattr(provider, "name", type(provider).__name__))
        self.operation_id = request.operation_id
        self.id = uuid.uuid4().hex
        self._started_monotonic = None
        self._ended_monotonic = None
        self._finished_at = None
        self._finished = False
        from .policy import Policy
        policy = getattr(request, "policy", None)
        effective = policy.effective() if policy is not None else Policy(model=getattr(request, "settings", {}).get("model")).effective()
        details = {
            "provider": self.provider_name,
            "capability_profile": getattr(getattr(provider, "capabilities", None), "version", None),
            "operation": str(getattr(request, "operation", "decide")),
            "model": effective.model,
            "effort": None if effective.effort is None else effective.effort.value,
            "policy_fingerprint": hashlib.sha256(
                json.dumps(effective.to_dict(), sort_keys=True).encode()
            ).hexdigest(),
            "attempt": request.attempt,
            "generation": request.attempt - 1,
            "scope": None if self.ctx is None else self.ctx.scope,
        }
        self.timeout = reserve_dispatch(
            provider,
            min(request.timeout, effective.timeout or request.timeout),
            dispatch_id=self.id,
            details=details,
        )
        if self.ctx is not None:
            from .streaming import bind_stream_identity

            bind_stream_identity(self.ctx.run_id, self.operation_id)

    def _event(self, name, data):
        if self.ctx is not None:
            self.ctx.journal.event(
                self.ctx.run_id,
                name,
                {"dispatch_id": self.id, **data},
                self.operation_id,
            )

    def started(self):
        self._started_monotonic = time.monotonic()
        self._event("provider_dispatch_started", {"started_at": now()})

    def stopped(self):
        """Capture effects having stopped before local parsing/receipt work."""
        if self._ended_monotonic is None:
            self._ended_monotonic, self._finished_at = time.monotonic(), now()

    def finish(self, outcome, *, usage=None, error=None):
        if self._finished:
            return
        self.stopped()
        self._finished = True
        values, availability = normalize_usage(
            usage, final=outcome == "completed", provider=self.provider_name
        )
        self._event(
            "provider_dispatch_finished",
            {
                "finished_at": self._finished_at,
                "outcome": outcome,
                "elapsed_seconds": None
                if self._started_monotonic is None
                else self._ended_monotonic - self._started_monotonic,
                "usage_availability": availability,
                "usage": values,
                "error_type": None if error is None else type(error).__name__,
            },
        )


def dispatch_records(events):
    """Fold lifecycle facts without upgrading unknown attempts from later responses."""
    records = {}
    for event in events:
        if event["event"] not in {
            "provider_dispatch_reserved",
            "provider_dispatch_started",
            "provider_dispatch_finished",
        }:
            continue
        data = event["data"]
        dispatch_id = data.get("dispatch_id")
        if not dispatch_id:
            continue
        record = records.setdefault(
            dispatch_id,
            {
                "dispatch_id": dispatch_id,
                "operation_id": event["operation_id"],
                "outcome": "unknown",
                "usage_availability": "unknown",
                "usage": {},
                "started_at": None,
                "finished_at": None,
                "elapsed_seconds": None,
            },
        )
        record.update(data)
        if event["event"] == "provider_dispatch_reserved":
            record["reserved_at"] = event["at"]
        record.update(record["usage"])
        if (
            "total_tokens" not in record
            and {"input_tokens", "output_tokens"} <= record.keys()
        ):
            record["total_tokens"] = record["input_tokens"] + record["output_tokens"]
    by_operation = {}
    for record in records.values():
        by_operation.setdefault(record["operation_id"], []).append(record)
    return by_operation


def aggregate_usage(dispatches):
    """Sum reported fields; completeness remains an explicit per-attempt fact."""
    values = {}
    for dispatch in dispatches:
        for key, value in dispatch["usage"].items():
            values[key] = values.get(key, 0) + value
    return values
