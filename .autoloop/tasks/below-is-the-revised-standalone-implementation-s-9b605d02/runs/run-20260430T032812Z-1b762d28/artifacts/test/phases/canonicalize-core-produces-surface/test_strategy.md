# Test Strategy

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: canonicalize-core-produces-surface
- Phase Directory Key: canonicalize-core-produces-surface
- Phase Title: Canonicalize Core Vocabulary
- Scope: phase-local producer artifact

## Behavior-to-coverage map
- Canonical step vocabulary replaces live `produces`/`review_produces`/`do_produces` usage in maintained surfaces.
  - Covered by existing maintained suite updates in `tests/unit/test_validation.py`, `tests/contract/test_engine_contracts.py`, `tests/runtime/test_compatibility_runtime.py`, and `tests/strictness/test_no_compat.py`.
- `autoloop_v3.core.*` and `core.*` must preserve shared module/class identity after removing dynamic alias mirroring.
  - Covered by `tests/unit/test_simple_surface.py::test_autoloop_v3_core_bridge_preserves_shared_module_identity`.
- Workflow discovery/runtime compatibility must keep working through the canonical bridge after the bridge refactor.
  - Covered by `tests/runtime/test_compatibility_runtime.py`, especially workflow package inspection and resolution cases.

## Preserved invariants checked
- `autoloop_v3.core`, `autoloop_v3.core.steps`, `autoloop_v3.core.validation`, and now `autoloop_v3.core.workflow_capabilities` resolve to the same modules as their `core.*` counterparts.
- Compatibility-runtime workflow package inspection still finds workflow classes and compiles them successfully.

## Edge cases
- Import topology where runtime/package discovery touches `workflow_capabilities` through the bridged package name instead of top-level `core.*`.

## Failure paths
- The added assertion would fail if future bridge changes recreate split module identity for `workflow_capabilities`, which previously broke compatibility-runtime workflow discovery.

## Flake-risk control
- Tests are deterministic and import-bound only; no timing, network, or nondeterministic ordering dependencies were introduced.

## Known gaps
- This pass did not add new persisted-session/checkpoint compatibility fixtures because the changed risk surface in cycle 2 was package/module identity, not payload translation.
