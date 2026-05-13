"""Workflow validation orchestration and compatibility re-exports."""

from __future__ import annotations

from .discovery import WorkflowDefinition, WorkflowMeta, describe_workflow_class, get_workflow_definition, has_start_hook, is_workflow_class
from .hook_validation import validate_handlers, validate_step_hooks
from .inventory import ArtifactInventoryRecord, collect_artifact_inventory, public_artifact_inventory, resolve_artifact_reference, resolve_optional_read_reference
from .lowering import PayloadValidator, compile_expected_output_contract, normalize_step_route_metadata, outcome_middleware_name, step_available_route_tags
from .state_validation import (
    validate_entry,
    validate_extensions,
    validate_sessions,
    validate_state,
    validate_transitions_shape,
    validate_worklists,
)
from .topology import (
    validate_artifact_declarations,
    validate_artifact_graph,
    validate_control_contracts,
    validate_required_artifacts,
    validate_topology,
)


def validate_workflow_definition(definition: WorkflowDefinition) -> None:
    """Validate a workflow definition through the owned validation modules."""

    validate_state(definition)
    validate_entry(definition)
    validate_transitions_shape(definition)
    validate_sessions(definition)
    validate_worklists(definition)
    validate_extensions(definition)
    validate_handlers(definition)
    validate_step_hooks(definition)
    inventory = collect_artifact_inventory(definition)
    validate_artifact_declarations(inventory)
    validate_required_artifacts(definition, inventory)
    validate_artifact_graph(definition, inventory)
    validate_topology(definition)
    validate_control_contracts(definition, inventory)


__all__ = [
    "ArtifactInventoryRecord",
    "PayloadValidator",
    "WorkflowDefinition",
    "WorkflowMeta",
    "collect_artifact_inventory",
    "compile_expected_output_contract",
    "describe_workflow_class",
    "get_workflow_definition",
    "has_start_hook",
    "is_workflow_class",
    "normalize_step_route_metadata",
    "outcome_middleware_name",
    "public_artifact_inventory",
    "resolve_artifact_reference",
    "resolve_optional_read_reference",
    "step_available_route_tags",
    "validate_workflow_definition",
]
