from __future__ import annotations

import pytest
from pydantic import BaseModel

from botlane import FINISH
from botlane.core import Workflow
from botlane.core.artifacts import Artifact
from botlane.core.discovery import get_workflow_definition
from botlane.core.errors import WorkflowValidationError
from botlane.core.inventory import collect_artifact_inventory
from botlane.core.steps import PythonStep


def _done(_ctx) -> None:
    return None


def test_collect_artifact_inventory_preserves_workflow_level_reuse_and_producers() -> None:
    shared_request = Artifact("request.txt")

    class InventoryWorkflow(Workflow):
        class State(BaseModel):
            pass

        request = shared_request
        publish = PythonStep(name="publish", writes={"request": shared_request}, handler=_done)
        revise = PythonStep(name="revise", writes={"request": shared_request}, handler=_done)
        entry = publish
        transitions = {
            publish: {"done": revise},
            revise: {"done": FINISH},
        }

    inventory = collect_artifact_inventory(get_workflow_definition(InventoryWorkflow))

    assert inventory["request"].qualified_name == "request"
    assert inventory["request"].owner_step is None
    assert inventory["request"].workflow_level is True
    assert inventory["request"].producer_steps == ("publish", "revise")


def test_collect_artifact_inventory_rebinds_passive_artifact_when_later_written() -> None:
    shared_log = Artifact("shared-log.txt")

    class RebindWorkflow(Workflow):
        class State(BaseModel):
            pass

        log_artifacts = (shared_log,)
        publish = PythonStep(name="publish", writes={"report": shared_log}, handler=_done)
        entry = publish
        transitions = {publish: {"done": FINISH}}

    inventory = collect_artifact_inventory(get_workflow_definition(RebindWorkflow))

    assert "workflow__log_1" not in inventory
    assert inventory["publish.report"].name == "report"
    assert inventory["publish.report"].owner_step == "publish"
    assert inventory["publish.report"].workflow_level is False
    assert inventory["publish.report"].producer_steps == ("publish",)


def test_collect_artifact_inventory_reports_workflow_level_name_conflicts_directly() -> None:
    workflow_request = Artifact("request.txt", name="request")
    produced_request = Artifact("produced-request.txt", name="request")

    class WorkflowLevelConflictWorkflow(Workflow):
        class State(BaseModel):
            pass

        request = workflow_request
        publish = PythonStep(name="publish", writes={"request": produced_request}, handler=_done)
        entry = publish
        transitions = {publish: {"done": FINISH}}

    with pytest.raises(
        WorkflowValidationError,
        match="declared by multiple artifact objects with the same public name",
    ) as exc_info:
        collect_artifact_inventory(get_workflow_definition(WorkflowLevelConflictWorkflow))

    message = str(exc_info.value)
    assert "workflow-level declaration 'request'" in message
    assert "step output 'publish.request' from step 'publish'" in message
    assert "template='request.txt'" in message
    assert "template='produced-request.txt'" in message


def test_collect_artifact_inventory_reports_duplicate_qualified_name_diagnostics() -> None:
    produced_report = Artifact("report.txt", name="report")
    conflicting_report = Artifact(
        "shadow-report.txt",
        name="report",
        owner_step="publish",
        qualified_name="publish.report",
    )

    class QualifiedNameConflictWorkflow(Workflow):
        class State(BaseModel):
            pass

        publish = PythonStep(
            name="publish",
            writes={"report": produced_report},
            log_artifacts=[conflicting_report],
            handler=_done,
        )
        entry = publish
        transitions = {publish: {"done": FINISH}}

    with pytest.raises(WorkflowValidationError, match="artifact qualified name 'publish\\.report'") as exc_info:
        collect_artifact_inventory(get_workflow_definition(QualifiedNameConflictWorkflow))

    message = str(exc_info.value)
    assert "template='report.txt'" in message
    assert "template='shadow-report.txt'" in message
    assert "share one Artifact object" in message
