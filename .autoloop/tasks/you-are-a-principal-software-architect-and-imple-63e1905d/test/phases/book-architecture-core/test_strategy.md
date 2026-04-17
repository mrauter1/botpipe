# Test Strategy

- Task ID: you-are-a-principal-software-architect-and-imple-63e1905d
- Pair: test
- Phase ID: book-architecture-core
- Phase Directory Key: book-architecture-core
- Phase Title: Book-Architecture Core
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Strict import surface removal:
  `autoloop_v3/tests/unit/test_primitives_and_stores.py::test_root_workflow_shim_reexports_strict_surface_only`
  Checks root and strict workflow surfaces do not re-export `SessionLifecycle`, and root/strict primitives do not re-export `Verdict`.
- Explicit entry requirement:
  `autoloop_v3/tests/unit/test_validation.py::test_validation_rejects_missing_entry`
  Confirms inferred-entry fallback is gone.
- `on_verdict` removal:
  `autoloop_v3/tests/unit/test_validation.py::test_validation_rejects_on_verdict_alias_without_matching_step`
  Confirms `on_verdict` is no longer middleware and becomes an orphan-handler failure unless a real `verdict` step exists.
- Strict handler signatures:
  `autoloop_v3/tests/unit/test_validation.py::test_validation_rejects_legacy_pair_handler_arity`
  `autoloop_v3/tests/unit/test_validation.py::test_validation_rejects_static_on_start_signature`
  Confirms legacy pair-handler arity and non-canonical `on_start` signatures fail validation.
- Explicit session opening:
  `autoloop_v3/tests/contract/test_engine_contracts.py::test_missing_session_binding_fails_instead_of_auto_opening`
  Confirms the engine now errors instead of auto-opening step sessions.
- Loader no-injection rule:
  `autoloop_v3/tests/runtime/test_compatibility_runtime.py::test_loader_does_not_inject_canonical_symbols`
  Confirms modules must import canonical names explicitly.

## Preserved Invariants Checked

- Canonical workflows still load through the strict root shim.
- Workflow-level artifact resolution and checkpoint/store primitives remain intact.
- Step-local naming collisions like `on_start` and `on_outcome` still work when they refer to actual steps.

## Edge Cases

- A removed compat symbol reappears on either import surface.
- A workflow omits `entry` and silently compiles.
- A legacy `on_verdict` hook is accepted without a matching step.
- A session-bound step executes without any explicit `ctx.open_session(...)`.

## Failure Paths

- Validation failures for missing `entry`, legacy pair-handler arity, and static `on_start`.
- Runtime execution failure for unopened session slots.
- Import-time failure for workflow modules that rely on loader-injected canonical names.

## Stabilization

- All tests use in-memory stores, scripted providers, and temporary files only.
- No timing, network, subprocess ordering, or external service behavior is asserted.

## Known Gaps

- This phase does not broaden runtime-parity coverage for Autoloop-v1 workspace behavior; that remains for later runtime/parity phases by contract.
