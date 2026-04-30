# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: canonical-surface-pruning
- Phase Directory Key: canonical-surface-pruning
- Phase Title: Prune Public And Top-Level Surfaces
- Scope: phase-local producer artifact

## Files changed

- `autoloop/simple.py`
- `core/__init__.py`
- `core/_compat.py`
- `autoloop_v3/core/__init__.py`
- `stdlib/control.py`
- `stdlib/prompts.py`
- `stdlib/steps.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/fixtures/toy_runtime_workflow.py`

## Symbols touched

- Removed from active `autoloop.simple`: `AfterHookResult`, `Checkpoint`, `ChildWorkflowResult`, `ResolvedArtifacts`, `WorkflowStep`
- Removed from active top-level `core`: `AfterHookResult`, `LLMStep`, `PairStep`, `Param`, `RouteInfo`, `StateVar`, `SUCCESS`, `SystemStep`, `WorkflowStep`
- Added explicit compatibility seam: `core._compat`, `autoloop_v3.core`

## Checklist mapping

- Milestone 1 / AC-1: trimmed `autoloop.simple` globals and importability to the canonical authoring surface
- Milestone 1 / AC-2: pruned legacy names from active `core/__init__.py` exports
- Milestone 1 / AC-3: kept an explicit `autoloop_v3.core` bridge while preserving shared `core` / `autoloop_v3.core` submodule identity and adding regression assertions

## Assumptions

- Later phases will migrate active low-level runtime/validation suites off `SUCCESS`, `RouteInfo`, and direct legacy step-class assertions instead of treating those failures as part of this surface-pruning slice.

## Preserved invariants

- `autoloop` root public surface remains unchanged and canonical
- `autoloop_v3.core.<submodule>` imports resolve with the same module identities as `core.<submodule>`
- persisted compatibility coverage can still import quarantined legacy names through `core._compat`

## Intended behavior changes

- `from autoloop.simple import Checkpoint`, `ChildWorkflowResult`, `ResolvedArtifacts`, `AfterHookResult`, or `WorkflowStep` now fails
- `from autoloop_v3.core import SUCCESS`, `RouteInfo`, legacy step classes, `Param`, or `StateVar` now fails

## Known non-changes

- This phase does not remove legacy names from internal modules such as `core.steps`, `core.routes`, `core.primitives`, or `core.validation`
- This phase does not migrate the broader legacy-heavy contract/runtime suites to canonical route and terminal expectations; active suites were limited to import-path decoupling from top-level `core`

## Expected side effects

- Maintained helpers that previously depended on top-level `core` imports now import from explicit submodules
- Compatibility fixtures that still exercise legacy authoring names now do so through `core._compat`
- Active legacy-heavy suites no longer rely on removed top-level `autoloop_v3.core` exports, but they still retain later-phase semantic expectations around legacy route and terminal names

## Validation performed

- `python3` import and identity smoke checks for `autoloop.simple`, `autoloop_v3.core`, `autoloop_v3.core._compat`, `autoloop_v3.core.compiler`, and shared `core.*` / `autoloop_v3.core.*` module identity
- `./.venv/bin/pytest tests/unit/test_simple_surface.py -q`
- `./.venv/bin/pytest tests/unit/test_primitives_and_stores.py::test_public_authoring_surfaces_export_requested_runtime_primitives -q`
- `./.venv/bin/pytest tests/runtime/test_compatibility_runtime.py::test_resolve_workflow_reference_preserves_same_root_workflow_class_identity -q`
- `./.venv/bin/pytest tests/unit/test_validation.py --collect-only -q`
- `./.venv/bin/pytest tests/contract/test_engine_contracts.py --collect-only -q`
- Broader targeted suite run (`tests/unit/test_validation.py`, `tests/contract/test_engine_contracts.py`, `tests/runtime/test_compatibility_runtime.py`) remains red on pre-existing later-phase canonicalization gaps around `SUCCESS`/`RouteInfo` expectations and low-level contract assertions

## Deduplication / centralization decisions

- Centralized quarantined legacy top-level imports in `core._compat` instead of leaving ad hoc re-exports on `core.__init__`
- Centralized `autoloop_v3.core` compatibility in one explicit bridge package while retaining shared module identity through the existing aliasing path
