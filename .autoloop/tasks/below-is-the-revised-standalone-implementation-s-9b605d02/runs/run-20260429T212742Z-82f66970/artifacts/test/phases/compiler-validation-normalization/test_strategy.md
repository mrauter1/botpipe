# Test Strategy

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: compiler-validation-normalization
- Phase Directory Key: compiler-validation-normalization
- Phase Title: Compiler And Validation Canonicalization
- Scope: phase-local producer artifact

## Coverage map

- AC-1 canonical compiled/route surface:
  `tests/unit/test_simple_surface.py` asserts removed simple aliases stay absent, `Route.complete` is gone, `required_outputs=` fails fast, canonical compiled kinds are emitted, and canonical default session name is `global`.
- AC-2 canonical validation rules:
  `tests/unit/test_simple_surface.py` asserts `Parameters` is rejected, non-`BaseModel` step state is rejected, and class-level `transitions` are rejected on the simple surface.
- AC-3 route injection and state/public-surface behavior:
  `tests/unit/test_simple_surface.py` asserts default routes by step kind, `control_routes=False` removes injected control routes and implicit semantic defaults, simple runtime step state stays model-backed through checkpoint serialization, and `item_state` / `step_item_state` fail fast when the model-backed public surface is not implemented.

## Preserved invariants checked

- Canonical `autoloop` export list remains unchanged.
- `produce_verify_step` still compiles with Pydantic workflow `State` / `Params` models and step-local state models.
- Operation nodes still compile as single-route feedforward nodes with only `"done"`.

## Edge cases and failure paths

- Invalid legacy keywords on simple declarations raise `TypeError`.
- `item.state` prompt placeholders fail validation instead of compiling to a partial public surface.
- Restored step-state payloads rehydrate to the declared Pydantic step model rather than remaining raw dicts.

## Known gaps

- Provider payload rename coverage remains out of scope for this phase.
- I only ran `python3 -m py_compile tests/unit/test_simple_surface.py` here; full pytest execution is still blocked by the missing test/runtime dependencies in this environment.
