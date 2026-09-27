"""Compatibility exports for packaged workflow author materialization."""

from botpipe.workflows.workflow_author import materialization as _canonical

WorkflowManifestValidationError = _canonical.WorkflowManifestValidationError
freeze_generated_workflow_candidate = _canonical.freeze_generated_workflow_candidate
materialize_generated_workflow_manifest = (
    _canonical.materialize_generated_workflow_manifest
)
prepare_generated_workflow_candidate = _canonical.prepare_generated_workflow_candidate
validate_generated_workflow_candidate = _canonical.validate_generated_workflow_candidate
_materialize_generated_workflow_manifest_activity = (
    _canonical._materialize_generated_workflow_manifest_activity
)
_revalidate_generated_workflow_materialization = (
    _canonical._revalidate_generated_workflow_materialization
)
_revalidate_generated_workflow_validation = (
    _canonical._revalidate_generated_workflow_validation
)
_validate_generated_workflow_candidate_activity = (
    _canonical._validate_generated_workflow_candidate_activity
)

__all__ = [
    "WorkflowManifestValidationError",
    "freeze_generated_workflow_candidate",
    "materialize_generated_workflow_manifest",
    "prepare_generated_workflow_candidate",
    "validate_generated_workflow_candidate",
]
