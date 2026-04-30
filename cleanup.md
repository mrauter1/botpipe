# Working Tree Note

This repository now treats the greenfield `autoloop.simple` and `autoloop` authoring model as the default public workflow surface.

For new workflow code and examples, import from `autoloop.simple` or `autoloop`.

`Event` and `Outcome` import from `autoloop.simple` or `autoloop`.

New docs and new workflow templates should stay on the canonical public surface: `FINISH`, `python_step`, `produce_verify_step`, `writes`, and step-local `routes`.

Workflow-local helper modules such as `contracts.py` stay discoverable through the workflow catalog surfaces.
