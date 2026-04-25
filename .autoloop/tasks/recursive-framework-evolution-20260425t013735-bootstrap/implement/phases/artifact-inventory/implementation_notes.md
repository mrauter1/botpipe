# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: artifact-inventory
- Phase Directory Key: artifact-inventory
- Phase Title: Artifact Inventory Compilation
- Scope: phase-local producer artifact

## Files changed

- `core/validation.py`
- `core/compiler.py`
- `core/engine.py`
- `tests/unit/test_validation.py`

## Symbols touched

- `ArtifactInventoryRecord`
- `collect_artifact_inventory(...)`
- `public_artifact_inventory(...)`
- `resolve_artifact_reference(...)`
- `normalize_step_route_contracts(...)`
- `CompiledWorkflow.artifacts_by_qualified_name`
- `Engine._resolve_artifacts(...)`

## Checklist mapping

- Plan milestone 2: unified workflow-level and step-local artifact inventory with qualified-name resolution.
- Active phase AC-03: step-local produced artifacts now bind owner-step metadata, qualified names, and compile as step attributes plus canonical compiled outputs.
- Active phase AC-04: compiler validation now rejects ambiguous artifact references and resolves route-contract artifact names deterministically.

## Assumptions

- Duplicate unqualified artifact names across different steps are now allowed only when callers use explicit qualified references or step-local route resolution can disambiguate them.
- Full runtime artifact-contract enforcement remains deferred to later phases; this phase only prepares canonical inventory and compile-time references.

## Preserved invariants

- Existing workflow-level artifact declarations still compile and keep unqualified aliases when globally unique.
- Existing `produces={"name": artifact}` and `requires=[artifact]` behavior remains valid.
- Deterministic compiled-workflow caching remains unchanged.

## Intended behavior changes

- Inline step-local produced artifacts now compile to canonical qualified references such as `draft.summary`.
- Route-contract `required_artifacts` are normalized through compiler-side artifact resolution, preferring current-step outputs before global unqualified lookup.

## Known non-changes

- No runtime artifact requiredness/schema enforcement was added.
- No session, continuity, worklist, or child-workflow changes were made in this phase.

## Expected side effects

- `CompiledWorkflow.artifacts` now exposes only unqualified aliases that are globally unambiguous.
- `CompiledWorkflow.artifacts_by_qualified_name` carries the full inventory for downstream runtime phases.
- Engine artifact resolution now exposes both canonical qualified handles and preserved unqualified aliases where safe.

## Validation performed

- `./.venv/bin/python -m py_compile core/validation.py core/compiler.py core/engine.py tests/unit/test_validation.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_validation.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py`
- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "compiled_workflow_is_deterministic or pair_step_contract_logs_raw_output_and_updates_state or llm_step_contract_logs_outcome_raw_output_and_uses_global_route"`

## Deduplication / centralization

- Centralized artifact-name disambiguation in `core.validation` so validation and compilation use the same resolution rules.
