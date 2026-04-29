# Working Tree Note

This repository now treats the greenfield `autoloop.simple` and `autoloop` authoring model as the default public workflow surface.

For new workflow code and examples, import from `autoloop.simple` or `autoloop`.

`Event`, `Outcome`, `Checkpoint`, `ResolvedArtifacts`, and `ChildWorkflowResult` import from `autoloop.simple` or `autoloop`.

Legacy aliases remain available during migration, but new docs and new workflow templates should stay on the canonical phase-1 surface: `FINISH`, `python_step`, `do_review_step`, `writes`, and step-local `routes`.

Workflow-local helper modules such as `contracts.py` stay discoverable through the workflow catalog surfaces.
