"""The packaged entry point for the guide-based workflow authoring SOP."""

from pathlib import Path

from botpipe import workflow
from botpipe_optimizer.surface_identity import derive_surface_manifest
from labs.workflows.workflow_idea_to_workflow_package import (
    Params,
    WorkflowIdeaToWorkflowPackage,
)
from labs.workflows.workflow_idea_to_workflow_package.contracts import (
    WorkflowAuthorResult,
)


@workflow(name="workflow_author", version="1")
def workflow_author(params: Params, request: str = "") -> WorkflowAuthorResult:
    """Design, build, test, and independently review a new workflow package."""
    result = WorkflowIdeaToWorkflowPackage(params, request, enforce_generated_test=True)
    # A completed nested workflow replays from its cached result. Recheck the
    # complete candidate here when an interrupted parent re-enters its handoff.
    root = Path(result.candidate_root)
    surface = derive_surface_manifest(
        root,
        expected_root=Path(result.validation.validated_root),
        boundary=result.surface_boundary,
        surface_kind="candidate",
    )
    if surface["surface_id"] != result.validation.candidate_surface_id:
        raise ValueError("generated workflow candidate changed after validation")
    return result.model_copy(update={"workflow_name": "workflow_author"})
