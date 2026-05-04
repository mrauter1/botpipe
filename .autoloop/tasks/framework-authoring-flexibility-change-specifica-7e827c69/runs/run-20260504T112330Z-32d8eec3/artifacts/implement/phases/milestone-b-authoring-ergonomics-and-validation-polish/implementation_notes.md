# Implementation Notes

- Task ID: framework-authoring-flexibility-change-specifica-7e827c69
- Pair: implement
- Phase ID: milestone-b-authoring-ergonomics-and-validation-polish
- Phase Directory Key: milestone-b-authoring-ergonomics-and-validation-polish
- Phase Title: Milestone B Authoring Ergonomics
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/effects.py`
- `autoloop/core/routes.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/inventory.py`
- `autoloop/core/artifacts.py`
- `autoloop/core/engine.py`
- `autoloop/core/operations.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched

- `WorklistEffect`
- `Effects.refresh`
- `Route.complete_current`
- `Route.complete_and_advance`
- `HookRunner.normalize_result`
- `collect_artifact_inventory`
- `_raise_dual_role_artifact_error`
- `_raise_artifact_ownership_ambiguity_error`
- `_resolve_prompt`
- `_resolve_runtime_path`

## Checklist mapping

- Milestone B / worklist effects:
  Added `WorklistEffect` helper constructors, direct `WorklistEffect` return normalization, and additive `Route.complete_and_advance(...)` sugar.
- Milestone B / validation helper alignment:
  No behavioral rewrite needed; existing helper already covered repair routing/feedback writing. Tests remain targeted at the current helper contract.
- Milestone B / prompt late binding:
  Tightened runtime diagnostics for late-bound `item`/`worklist` prompt placeholders with step/worklist context.
- Milestone B / artifact ownership diagnostics:
  Extended ambiguity diagnostics to distinct-artifact public-name collisions across workflow-level and produced artifacts.

## Assumptions

- The existing `ValidationResult` and `validation_step(...)` surface from earlier work is the intended in-tree API to preserve.
- Prompt runtime diagnostics may intentionally change wording to include step/worklist context without broadening compile-time placeholder validation.

## Preserved invariants

- Worklist mutations still execute in the existing refresh -> status -> advance order through one runtime pipeline.
- Checkpoint/runtime state mutation behavior for worklist effects remains owned by the existing worklist runtime view and engine checkpointing.
- Artifact-template placeholder rendering still uses the artifact-specific label; only prompt-render labels were made step-aware.
- Managed-artifact behavior remains unchanged; only ambiguity diagnostics were tightened.

## Intended behavior changes

- Hooks and python steps may now return a bare `WorklistEffect` in addition to `Effects(...)`.
- `WorklistEffect` exposes narrow constructor helpers for the supported scoped-work mutations.
- Prompt placeholder runtime failures now name the current step and, for runtime path failures, the worklist when applicable.
- Distinct artifacts that reuse a workflow-level public artifact name as a produced output now fail with an ownership-specific diagnostic.

## Known non-changes

- `validation_step(...)` still uses the existing `failed` route-tag contract and does not introduce a second validation abstraction.
- No workflow packages or broad documentation surfaces were modified in this phase.
- No new generalized effects DSL was introduced.

## Expected side effects

- Tests that asserted the old prompt-placeholder wording need the updated step/worklist-aware message expectations.
- Authoring code can use `Route.complete_and_advance(...)` as additive sugar, but existing `Effects.*` helpers remain the primary surface.

## Validation performed

- `python3 -m compileall` on all touched framework modules.
- `python3 -m compileall` on the touched contract/unit test files.
- Attempted targeted pytest execution, but the environment lacks `pytest`.
- Attempted import smoke test, but the environment lacks `pydantic`, so runtime imports could not be exercised here.

## Deduplication / centralization

- Direct `WorklistEffect` returns are normalized back into `Effects(...)` so effect ordering and exhausted-route handling stay centralized in `HookRunner._apply_effects(...)`.
- Artifact ownership ambiguity now funnels through one helper for both same-identity and distinct-identity workflow-level vs produced collisions.
