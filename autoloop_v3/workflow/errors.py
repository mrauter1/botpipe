"""Workflow core error types."""

from __future__ import annotations


class WorkflowError(Exception):
    """Base exception for the strict workflow core."""


class WorkflowValidationError(WorkflowError):
    """Raised when a workflow definition is invalid."""


class WorkflowCompilationError(WorkflowError):
    """Raised when a validated workflow cannot be compiled."""


class WorkflowExecutionError(WorkflowError):
    """Raised when workflow execution fails."""


class RoutingError(WorkflowExecutionError):
    """Raised when no route exists for a produced tag."""


class ArtifactResolutionError(WorkflowExecutionError):
    """Raised when artifacts cannot be resolved or required inputs are missing."""


class MissingArtifactError(ArtifactResolutionError):
    """Raised when a required artifact path does not exist at runtime."""


class CheckpointError(WorkflowExecutionError):
    """Raised when checkpoint persistence fails."""


class ProviderExecutionError(WorkflowExecutionError):
    """Raised when the provider contract is violated."""

