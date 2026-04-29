# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Canonical Public Surface
- Scope: phase-local producer artifact

## Files changed

- `autoloop/__init__.py`
- `autoloop/simple.py`
- `core/descriptors.py`
- `core/validation.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/strictness/test_no_compat.py`
- `tests/runtime/test_workflow_reference_resolution.py`
- `tests/contract/test_engine_contracts.py`
- `docs/authoring.md`
- `docs/architecture.md`
- `workflows/*/workflow.py` for the simple public authoring packages that imported `do_review_step`

## Symbols touched

- Added/kept canonical public surface: `Workflow`, `step`, `produce_verify_step`, `python_step`, `workflow_step`, `llm`, `classify`, `Prompt`, `Md`, `Json`, `Text`, `Raw`, `Route`, `Session`, `Continuity`, `Worklist`, `Event`, `Outcome`, `FINISH`, `PAUSE`, `FAIL`, `SELF`
- Removed public root/simple aliases: `SUCCESS`, `RouteInfo`, `StrictWorkflow`, `chain`, `review_step`, `do_review_step`, `system_step`, `StateVar`, `Param`
- Canonical simple args: `producer_prompt`, `verifier_prompt`, `producer_writes`, `verifier_writes`, `verifier_requires`, `verifier_session`, `writes`
- Canonical model namespaces: workflow `State`, workflow `Params`, step `state=BaseModelSubclass`

## Checklist mapping

- Public export cleanup: completed in `autoloop/__init__.py`
- Simple declaration rename to canonical producer/verifier surface: completed in `autoloop/simple.py`
- BaseModel-backed state/params for the simple surface: completed in `core/descriptors.py` and `core/validation.py`
- Presence/absence regression tests for the canonical import surface: completed in `tests/unit/test_simple_surface.py` and `tests/strictness/test_no_compat.py`
- Repo-authored simple workflow consumers migrated to canonical names: completed for `workflows/*/workflow.py`, `docs/*`, and the touched public-surface tests

## Assumptions

- Keeping internal lowering support for `flow` / `transitions` is acceptable in this phase as long as the public alias exports stay removed.
- Package-level `Parameters` / `params.py` runtime discovery is deferred; this pass only enforces `Params` on the `autoloop.simple.Workflow` authoring surface.

## Preserved invariants

- Existing engine/provider/checkpoint logic was not refactored in this phase.
- Simple declaration lowering still feeds the current core `LLMStep` / `PairStep` / `SystemStep` pipeline.
- Route/control-route behavior remains driven by the current validation/compiler path.

## Intended behavior changes

- `from autoloop import ...` now exposes only the canonical public symbols.
- `autoloop.simple` no longer exposes the removed alias helpers and only accepts canonical simple-step argument names.
- Simple workflow state/params authoring now uses `State`, `Params`, and step `state=BaseModelSubclass`; descriptor-backed simple authoring is rejected.
- Repo-authored simple workflows now call `produce_verify_step(...)` with `producer_prompt=` / `verifier_prompt=`.

## Known non-changes

- Core/internal compatibility types such as `RouteInfo`, `SUCCESS`, and low-level `PairStep` remain outside this phase’s cleanup boundary.
- Persisted run-file migration, topology artifact renames, static graph cleanup, and optimizer/package relocation were not changed here.

## Expected side effects

- Public root imports of removed symbols now fail by design.
- Public simple workflows that still use removed aliases must migrate to the canonical names.

## Validation performed

- `.venv/bin/pytest tests/unit/test_simple_surface.py tests/strictness/test_no_compat.py tests/unit/test_primitives_and_stores.py -q`
- `.venv/bin/pytest tests/runtime/test_workflow_reference_resolution.py::test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection tests/contract/test_engine_contracts.py::test_produce_verify_step_sends_split_phase_contracts_without_implicitly_requiring_producer_writes -q`

## Dedup / centralization

- Step-state model adaptation is centralized in `core/validation.py` so the engine can keep using one step-state storage shape during this phase.
- `autoloop/__init__.py` now points all public simple imports through the canonical `autoloop.simple` symbols instead of re-exporting legacy aliases.
