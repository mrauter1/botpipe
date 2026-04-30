# Test Strategy

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: canonical-surface-pruning
- Phase Directory Key: canonical-surface-pruning
- Phase Title: Prune Public And Top-Level Surfaces
- Scope: phase-local producer artifact

## Behavior coverage map

- Canonical public surface: assert `autoloop` root exports only the documented public API and removed symbols fail to import.
- Canonical simple surface: assert `autoloop.simple` omits non-canonical helpers and rejects legacy keyword shapes.
- Canonical top-level core surface: assert removed legacy names are absent from `autoloop_v3.core`.
- Bridge compatibility invariant: assert `core`, `autoloop_v3.core`, and key submodules share module/class identity so workflow discovery and validation do not split.
- Explicit compatibility boundary: assert `_compat` imports remain confined to explicit compatibility coverage files only.

## Preserved invariants checked

- `autoloop_v3.core.Workflow` is the same object as `core.Workflow`.
- `autoloop_v3.core.steps.Step` and `autoloop_v3.core.validation.WorkflowMeta` resolve through the same module graph as `core.*`.
- Compatibility-only fixtures may still use `core._compat` without re-exposing those names on active top-level imports.

## Edge cases

- Removed symbols are checked both via `hasattr(...)` absence and import failure.
- Bridge identity is checked at both package and submodule levels to catch partial aliasing regressions.

## Failure paths

- Legacy `simple` keyword aliases still fail fast with `TypeError`.
- `_compat` leakage into maintained active files fails the quarantine test by reporting offending paths.

## Known gaps

- This phase does not migrate the broader semantic legacy expectations in active runtime/contract suites; those remain later-phase coverage work.
