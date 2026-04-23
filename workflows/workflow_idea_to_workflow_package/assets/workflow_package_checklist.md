# Workflow Package Checklist

Use this checklist when designing or building a workflow package from a workflow idea.

Required package surfaces:
- `workflows/<package_name>/__init__.py`
- `workflows/<package_name>/workflow.py`
- `workflows/<package_name>/workflow.toml`
- `workflows/<package_name>/prompts/`
- `workflows/<package_name>/assets/`

Required supporting outputs:
- workflow design spec
- machine-readable step contracts
- prompt contract matrix
- verification plan
- build report
- verification report
- promotion record
- rollback plan
- package-specific docs
- package-specific tests

Do not:
- invent a hidden generator layer
- move provider-facing SOP into runtime-only metadata
- hide file inventory in prose only
