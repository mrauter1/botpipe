# Cleanup Note

This repository now uses the greenfield `autoloop.simple` and `autoloop` authoring model.

Workflow authors should import from `autoloop.simple` or `autoloop`.

`Event`, `Outcome`, `Checkpoint`, `ResolvedArtifacts`, and `ChildWorkflowResult` import from `autoloop.simple` or `autoloop`.

`contracts.py` stay discoverable through the workflow catalog surfaces.
