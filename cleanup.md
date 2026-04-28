# Working Tree Notes

This repository is on the greenfield `autoloop.simple` and `autoloop` authoring model.

- Public workflow examples and docs should import from `autoloop.simple` or `autoloop`.
- `workflow/` remains a narrow shim and `workflow.primitives` remains a runtime primitive shim.
- Support files such as `specs.py`, `params.py`, and `contracts.py` stay discoverable through the workflow catalog surfaces.
- Runtime-owned behavior stays in `core/` and `runtime/`; docs and tests should not restore removed compatibility surfaces.
