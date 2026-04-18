"""Workflow-facing git tracking declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ...workflow.extensions import RunBinding
from .policy import GitPolicy
from .runtime import BoundGitTracking, _NoOpBoundGitTracking


FailureMode = Literal["raise", "ignore"]


@dataclass(frozen=True, slots=True)
class GitTrackingConfig:
    """Optional git-tracking side-effect policy."""

    enabled: bool = True
    track_task_workspace_artifacts: bool = True
    failure_mode: FailureMode = "raise"


@dataclass(frozen=True, slots=True)
class GitTracking:
    """Workflow-declared git tracking extension."""

    policy: GitPolicy
    config: GitTrackingConfig = GitTrackingConfig()

    def bind(self, binding: RunBinding) -> BoundGitTracking | _NoOpBoundGitTracking:
        if not self.config.enabled:
            return _NoOpBoundGitTracking()
        return BoundGitTracking(binding, self.policy, self.config)
