"""Experimental discovery alias for the packaged workflow author."""

from botpipe import workflow
from botpipe.workflows.workflow_author.contracts import WorkflowAuthorResult
from botpipe.workflows.workflow_author.params import Params
from botpipe.workflows.workflow_author.workflow import _build_workflow_package


@workflow(name="workflow_idea_to_workflow_package", version="5")
def WorkflowIdeaToWorkflowPackage(
    params: Params, request: str = "", *, enforce_generated_test: bool = False
) -> WorkflowAuthorResult:
    """Run the packaged author under its historical experimental name."""
    return _build_workflow_package(
        params,
        request,
        enforce_generated_test=enforce_generated_test,
        workflow_name="workflow_idea_to_workflow_package",
    )


workflow_callable = WorkflowIdeaToWorkflowPackage

__all__ = ["WorkflowIdeaToWorkflowPackage", "workflow_callable"]
