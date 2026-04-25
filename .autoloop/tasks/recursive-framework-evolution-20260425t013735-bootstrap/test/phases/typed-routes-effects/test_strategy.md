# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: test
- Phase ID: typed-routes-effects
- Phase Directory Key: typed-routes-effects
- Phase Title: Typed Routes And Effects
- Scope: phase-local producer artifact

## Behaviors Covered

- Shorthand transitions still normalize to explicit compiled route metadata.
- `Route.to(...)` and `Route.complete()` compile and execute without breaking existing engine routing.
- Invalid effect/worklist references fail at compile time.
- `Advance(..., if_exhausted="route")` still rejects missing `route_to` before the deferred worklist check.
- Capability/CLI compatibility remains string-target based for transitions.
- Root `workflow` shim exposes `Route` but not deferred effect classes.

## Preserved Invariants Checked

- Existing transition dict shorthand still executes successfully.
- Workflow control semantics remain step-target or terminal-only.
- Root shims still exclude runtime/compiler internals.
- Internal effect validation stays available through `autoloop_v3.core.effects`.

## Edge Cases

- Empty-effect `Route.complete()` still compiles with an empty `effects` tuple.
- Step-target routes compile to the step name rather than retaining live step objects.
- Public shim surface is checked explicitly to prevent effect re-exports from drifting back in.

## Failure Paths

- Unknown effect worklist names are rejected deterministically at validation time.
- `Advance(..., if_exhausted="route")` without `route_to` is rejected deterministically.

## Known Gaps

- Worklist-backed effect execution is intentionally deferred; current coverage only protects the deferred/public-surface boundary and compile-time rejection behavior.
- Full-suite `pytest -q` was not run in this phase; coverage is focused on strictness, unit, contract, and compatibility paths touched by the change.
