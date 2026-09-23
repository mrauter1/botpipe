"""Durable limits on actual provider dispatches, shared by child workflows."""

from __future__ import annotations

import json
import math
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from .errors import BudgetExceeded, ReplayMismatch


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
        now = time.time()
        with ctx.journal.transaction() as db:
            row = db.execute(
                "SELECT state FROM provider_budgets WHERE id=?", (operation_id,)
            ).fetchone()
            if row is None:
                duration = config["max_seconds"]
                started = datetime.fromisoformat(
                    ctx.journal.get(operation_id)["started_at"]
                ).timestamp()
                deadline = None if duration is None else started + duration
                state = {
                    **config,
                    "used_turns": 0,
                    "deadline": deadline,
                    "last_observed": now,
                    "remaining_seconds": None
                    if deadline is None
                    else max(0.0, deadline - now),
                }
                db.execute(
                    "INSERT INTO provider_budgets VALUES (?,?)",
                    (operation_id, json.dumps(state)),
                )
            else:
                state = json.loads(row[0])
                if any(state[key] != value for key, value in config.items()):
                    raise ReplayMismatch("Provider budget limits changed across resume")
        self._remaining_at_start = state["remaining_seconds"]
        self._last_observed = state["last_observed"]

    def _state(self, db):
        state = json.loads(
            db.execute(
                "SELECT state FROM provider_budgets WHERE id=?", (self.operation_id,)
            ).fetchone()[0]
        )
        now = time.time()
        if now < max(self._last_observed, state["last_observed"]):
            raise BudgetExceeded(
                "Wall clock moved backwards while enforcing provider deadline"
            )
        self._last_observed = state["last_observed"] = now
        if state["deadline"] is not None:
            state["remaining_seconds"] = max(
                0.0,
                min(
                    state["deadline"] - now,
                    state["remaining_seconds"],
                    self._remaining_at_start
                    - (time.monotonic() - self._monotonic_start),
                ),
            )
        return state

    def _save(self, db, state):
        db.execute(
            "UPDATE provider_budgets SET state=? WHERE id=?",
            (json.dumps(state), self.operation_id),
        )

    def snapshot(self):
        with self.ctx.journal.transaction() as db:
            state = self._state(db)
            self._save(db, state)
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


def _dispatch_limits(provider, configured_timeout, states):
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
        remaining = state["remaining_seconds"]
        if remaining is not None and remaining <= 0:
            raise BudgetExceeded("Provider dispatch deadline exhausted")
        if state["used_turns"] >= state["max_turns"]:
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
    with ctx.journal.transaction() as db:
        states = [(budget, budget._state(db)) for budget in budgets]
        limits = _dispatch_limits(provider, configured_timeout, states)
        for budget, state in states:
            budget._save(db, state)
    return min(limits)


def reserve_dispatch(provider, configured_timeout, *, dispatch_id, details):
    """Reserve every active limit atomically, immediately before a new effect."""
    from .runtime import _CURRENT
    ctx = _CURRENT.get()
    budgets = () if ctx is None else ctx.provider_budgets
    if ctx is None:
        return configured_timeout
    with ctx.journal.transaction() as db:
        states = [(budget, budget._state(db)) for budget in budgets]
        limits = _dispatch_limits(provider, configured_timeout, states)
        reservations = []
        for budget, state in states:
            state["used_turns"] += 1
            budget._save(db, state)
            reservations.append(
                {"budget_id": budget.operation_id, "sequence": state["used_turns"]}
            )
        ctx.journal._event(
            db,
            ctx.run_id,
            ctx.operation_id,
            "provider_dispatch_reserved",
            {
                **details,
                "dispatch_id": dispatch_id,
                "timeout_seconds": min(limits),
                "budgets": reservations,
            },
        )
    return min(limits)
