"""Experimental discovery alias for the packaged workflow author."""

from botpipe import workflow
from botpipe.workflows.workflow_author import Params, WorkflowAuthorResult, workflow_author


@workflow(name="workflow_idea_to_workflow_package", version="6")
def WorkflowIdeaToWorkflowPackage(params: Params, request: str = "") -> WorkflowAuthorResult:
    """Build and test a candidate using the same bounded packaged author."""
    return workflow_author(params, request)


workflow_callable = WorkflowIdeaToWorkflowPackage

__all__ = ["WorkflowIdeaToWorkflowPackage", "workflow_callable"]
