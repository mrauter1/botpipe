# Workflow Authoring Checklist

Use this checklist when designing or building a workflow from a workflow idea.

Supported output shapes:
- `single`: `.botpipe/workflows/<package_name>.py`
- `flow_specs`: `.botpipe/workflows/<package_name>/flow.py` plus optional `specs.py`
- `package`: `labs/workflows/<package_name>/flow.py`, `specs.py`, `workflow.toml`, and any chosen support folders

Required supporting outputs:
- workflow design spec
- machine-readable step contracts
- prompt contract matrix
- verification plan
- generated layout summary
- build report
- verification report
- promotion record
- rollback plan

Optional supporting outputs:
- workflow-specific docs
- workflow-specific tests
- prompts/
- assets/
- workflow.toml
- `__init__.py`
- `specs.py`

Do not:
- invent a hidden generator layer
- move provider-facing SOP into runtime-only metadata
- hide file inventory in prose only
