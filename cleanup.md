# Working Tree Note

This repository now treats the greenfield `autoloop` authoring model as the default public workflow surface.

For new workflow code and examples, import from `autoloop`.

`Event` and `Outcome` import from `autoloop`.

New docs and new workflow templates should stay on the canonical public surface: `FINISH`, `python_step`, `produce_verify_step`, `writes`, step-local `routes`, and one-argument `python_step` handlers that mutate `ctx`.

Workflow-local helper modules such as `contracts.py` stay discoverable through the workflow catalog surfaces.
