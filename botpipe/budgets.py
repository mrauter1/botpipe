"""Durable limits on actual provider dispatches, shared by child workflows."""

from __future__ import annotations

import math
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from .errors import BudgetExceeded


def _seconds(value, name):
    if value is not None and (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be positive and finite")
    return None if value is None else float(value)


class ProviderBudget:
    """A journal-backed budget. Obtain one with :func:`provider_budget`."""

    def __init__(self, ctx, operation_id, config):
        self.ctx, self.operation_id = ctx, operation_id
        self.config = config
        self._monotonic_start = time.monotonic()
        state = ctx.journal.create_budget(operation_id, config, time.time())
        self._remaining_at_start = state["remaining_seconds"]
        self._last_observed = state["last_observed"]

    def _remaining_cap(self):
        if self._remaining_at_start is None:
            return None
        return self._remaining_at_start - (time.monotonic() - self._monotonic_start)

    def snapshot(self):
        states = self.ctx.journal.observe_budgets(
            self.ctx.run_id,
            [self.operation_id],
            time.time(),
            {self.operation_id: self._remaining_cap()},
        )
        state = states[0]
        self._last_observed = state["last_observed"]
        deadline = state.pop("deadline")
        state.pop("last_observed")
        return {
            **state,
            "deadline_utc": None
            if deadline is None
            else datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
        }

    @property
    def used_turns(self):
        return self.snapshot()["used_turns"]


@contextmanager
def provider_budget(*, max_turns, max_seconds=None, turn_timeout_seconds=None):
    """Limit actual dispatches, including repairs and explicitly authorized retries.

    The duration starts once and includes time spent suspended. Re-entering on
    replay restores its original deadline and count. Nested budgets all apply.
    Time bounds require a provider declaring ``supports_timeout = True``;
    that contract means it joins/stops all effects before returning or raising.
    """
    from .runtime import current_run

    if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns <= 0:
        raise ValueError("max_turns must be a positive integer")
    config = {
        "max_turns": max_turns,
        "max_seconds": _seconds(max_seconds, "max_seconds"),
        "turn_timeout_seconds": _seconds(turn_timeout_seconds, "turn_timeout_seconds"),
    }
    ctx = current_run()
    operation_id = ctx.operation(
        "provider_budget", config, lambda: ctx.operation_id, retry_safe=True
    )
    budget = ProviderBudget(ctx, operation_id, config)
    previous = ctx.provider_budgets
    ctx.provider_budgets = (*previous, budget)
    try:
        yield budget
    finally:
        ctx.provider_budgets = previous
        # Each reservation and explicit snapshot persists the remaining ceiling.
        # Do not mask a workflow failure with a second exception on cleanup.


def _dispatch_limits(provider, configured_timeout, states, *, check_counts=True):
    from .providers import ProviderPolicyError

    if any(
        budget.config["max_seconds"] is not None
        or budget.config["turn_timeout_seconds"] is not None
        for budget, _state in states
    ) and getattr(provider, "supports_timeout", False) is not True:
        raise ProviderPolicyError(
            "Timed provider budgets require supports_timeout=True: the adapter must "
            "enforce request.timeout and stop/join all effects before returning"
        )
    limits = [configured_timeout]
    for _budget, state in states:
        remaining = state.get("remaining_seconds")
        if "remaining_seconds" in state and remaining is not None and remaining <= 0:
            raise BudgetExceeded("Provider dispatch deadline exhausted")
        if check_counts and state["used_turns"] >= state["max_turns"]:
            raise BudgetExceeded(
                f"Provider dispatch budget exhausted ({state['used_turns']}/{state['max_turns']} turns)"
            )
        limits.extend(
            value
            for value in (remaining, state["turn_timeout_seconds"])
            if value is not None
        )
    return limits


def dispatch_timeout_ceiling(provider, configured_timeout):
    """Read the current dispatch time ceiling without consuming a turn."""
    from .runtime import _CURRENT

    ctx = _CURRENT.get()
    if ctx is None:
        return configured_timeout
    budgets = ctx.provider_budgets
    if not budgets:
        return configured_timeout
    observed = time.time()
    states = ctx.journal.observe_budgets(
        ctx.run_id,
        [budget.operation_id for budget in budgets],
        observed,
        {budget.operation_id: budget._remaining_cap() for budget in budgets},
    )
    paired = list(zip(budgets, states, strict=True))
    limits = _dispatch_limits(provider, configured_timeout, paired)
    for budget, state in paired:
        budget._last_observed = state["last_observed"]
    return min(limits)


def reserve_dispatch(provider, configured_timeout, *, dispatch_id, details):
    """Reserve every active limit atomically, immediately before a new effect."""
    from .runtime import _CURRENT
    ctx = _CURRENT.get()
    budgets = () if ctx is None else ctx.provider_budgets
    if ctx is None:
        return configured_timeout
    # Provider capability is checked before a durable reservation. Counts and
    # deadlines are rechecked atomically by the journal before it appends the
    # one record shared by all enclosing budgets.
    configurations = [(budget, budget.config) for budget in budgets]
    _dispatch_limits(provider, configured_timeout, configurations, check_counts=False)
    observed = time.time()
    states = ctx.journal.reserve_budgets(
        ctx.run_id,
        ctx.operation_id,
        [budget.operation_id for budget in budgets],
        observed,
        {budget.operation_id: budget._remaining_cap() for budget in budgets},
        configured_timeout,
        {**details, "dispatch_id": dispatch_id},
    )
    paired = list(zip(budgets, states, strict=True))
    limits = _dispatch_limits(provider, configured_timeout, paired, check_counts=False)
    for budget, state in paired:
        budget._last_observed = state["last_observed"]
    return min(limits)
