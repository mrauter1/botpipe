"""Bound runtime for the optional git tracking extension."""

from __future__ import annotations

from collections.abc import Sequence

from autoloop.core.extensions import RunBinding, StepFinish, StepStart, TerminalFinish
from .filters import (
    delta_pathspecs,
    filter_delta_by_pathspecs,
    filter_delta_by_prefixes,
    workflow_workspace_pathspec,
)
from .policy import GitCommitPlan, GitPolicy
from .repo import GitRepo, GitRepoError


class _NoOpBoundGitTracking:
    def before_step(self, event: StepStart) -> None:
        return None

    def after_step(self, event: StepFinish) -> None:
        return None

    def on_terminal(self, event: TerminalFinish) -> None:
        return None


class BoundGitTracking:
    """Per-run git tracking runtime bound from a workflow declaration."""

    def __init__(self, binding: RunBinding, policy: GitPolicy, config) -> None:
        self._binding = binding
        self._policy = policy
        self._config = config
        self._repo = None if not config.enabled else GitRepo.discover(binding.root)
        if config.enabled and self._repo is None:
            self._handle_error(
                GitRepoError(f"GitTracking enabled but no git repository was found from {binding.root}")
            )

    def before_step(self, event: StepStart) -> None:
        if self._repo is None:
            return
        self._run_plans(self._policy.before_step(event), raw_delta=self._repo.raw_delta())

    def after_step(self, event: StepFinish) -> None:
        if self._repo is None:
            return
        raw_delta = self._repo.raw_delta()
        self._run_plans(self._policy.after_step(event, raw_delta), raw_delta=raw_delta)

    def on_terminal(self, event: TerminalFinish) -> None:
        if self._repo is None:
            return
        raw_delta = self._repo.raw_delta()
        self._run_plans(self._policy.on_terminal(event, raw_delta), raw_delta=raw_delta)

    def _run_plans(self, plans: Sequence[GitCommitPlan], *, raw_delta) -> None:
        try:
            for plan in plans:
                scoped_delta = raw_delta
                if self._config.track_workflow_workspace_artifacts:
                    prefix = workflow_workspace_pathspec(self._repo.root, self._binding)
                    scoped_delta = filter_delta_by_prefixes(scoped_delta, (prefix,) if prefix else ())
                if plan.include_paths:
                    scoped_delta = filter_delta_by_pathspecs(scoped_delta, plan.include_paths)
                self._repo.commit(plan, pathspecs=delta_pathspecs(scoped_delta))
        except Exception as exc:
            self._handle_error(exc)

    def _handle_error(self, exc: Exception) -> None:
        if self._config.failure_policy == "record_and_continue":
            return
        raise exc


__all__ = ["BoundGitTracking", "_NoOpBoundGitTracking"]
