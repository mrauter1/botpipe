# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: artifact-model
- Phase Directory Key: artifact-model
- Phase Title: Artifact Model Upgrade
- Scope: phase-local producer artifact

## Files changed

- `core/artifacts.py`
- `core/compiler.py`
- `core/validation.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_validation.py`
- `.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/decisions.txt`

## Symbols touched

- `Artifact`
- `ArtifactHandle`
- `ArtifactValidationResult`
- `CompiledArtifact`
- `resolve_artifact_template(...)`
- `validate_artifact_declaration(...)`
- `validate_artifact_handle(...)`
- `validate_workflow_definition(...)`
- `_validate_artifact_declarations(...)`
- `_compile_artifacts(...)`

## Checklist mapping

- Plan milestone 1: implemented `Artifact.kind`, `Artifact.schema`, `Artifact.required`, `Artifact.owner_step`, `Artifact.qualified_name`, factory constructors, handle JSON/model helpers, and validation helpers.
- Plan milestone 2 subset: added compile-time artifact schema-placement validation only; full artifact inventory qualification and ambiguity resolution remain deferred.

## Assumptions

- This phase should not change route execution, checkpoint payload shape, or runtime artifact-enforcement order.
- Existing plain `Artifact(...)` declarations remain the common compatibility path; extended metadata is additive.

## Preserved invariants

- `Artifact("{workflow_folder}/x.md")` remains valid with default text-kind semantics.
- `ArtifactHandle.read_text/write_text/append/exists` behavior is unchanged.
- Existing engine and provider flows continue to resolve artifacts by template/name as before.

## Intended behavior changes

- Artifact declarations can now carry `kind`, `schema`, `required`, `owner_step`, and `qualified_name`.
- Artifact handles can read/write JSON, round-trip Pydantic models, and validate resolved file contents against artifact metadata.
- Workflow definition validation now rejects artifact schemas on non-JSON artifacts and rejects unsupported artifact schema types early.

## Known non-changes

- No runtime route-specific artifact enforcement yet.
- No step-local artifact inventory/qualified-name resolution yet.
- No session, params, worklist, route/effect, or child-workflow contract changes in this phase.

## Expected side effects

- Compiled artifact metadata now preserves additive artifact fields for later enforcement work.
- Step-local relative artifact path resolution is supported when `resolve_artifact_template(...)` receives an `Artifact` carrying `owner_step`; existing string-template calls are unchanged.

## Validation performed

- `./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py`
- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py`
- `./.venv/bin/python -m pytest -q tests/runtime/test_compatibility_runtime.py`
- `./.venv/bin/python -m compileall core tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py`

## Deduplication / centralization

- Centralized artifact declaration checks in `core.artifacts.validate_artifact_declaration(...)`.
- Centralized file-level artifact validation in `core.artifacts.validate_artifact_handle(...)` and reused it from `ArtifactHandle.validate()`.
