# Test Strategy

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: test
- Phase ID: ctx-rendering-and-validation
- Phase Directory Key: ctx-rendering-and-validation
- Phase Title: Integrate Safe ctx Prompt Rendering
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- `tests/unit/test_primitives_and_stores.py`
  Covers direct runtime `ctx` resolution for happy-path scalar rendering, missing `ctx.input` failure, non-scalar `ctx` model values, unsafe `ctx` paths, and explicit artifact-path rejection for `ctx.*`.
- `tests/unit/test_simple_surface.py`
  Covers compile-time simple-step validation for supported `ctx.*` placeholders and rejected forms such as `{message}`, `{ctx}`, bare `ctx.request/input/state/params`, unknown model fields, and unsafe dotted paths.
- `tests/contract/test_engine_contracts.py`
  Covers provider-backed prompt rendering, producer/verifier prompt rendering, operation prompt rendering, valid `workflow_step(message=...)` rendering, and runtime-only invalid `workflow_step(message=...)` failures.

## Preserved invariants checked

- `ctx.*` remains prompt-only; artifact templates reject it explicitly.
- `workflow_step(message=...)` renders supported placeholders without changing `message_from` behavior elsewhere in the repo.
- Runtime-only child-message rendering does not leak raw `AttributeError` when compile-time validation is bypassed.

## Edge cases and failure paths

- Missing workflow input for `ctx.input.<field>`.
- Complex `ctx` model values that must not be silently stringified.
- Unsafe or unsupported `ctx` dotted paths.
- Missing-field failures across runtime-only `ctx.input`, `ctx.state`, and `ctx.params` child-message placeholders.

## Flake risk and stabilization

- All added coverage is deterministic and uses local temporary directories plus fake providers or stub child invokers.
- No timing, network, or nondeterministic ordering assumptions were introduced.

## Known gaps

- I did not add new coverage for provider adapter implementations themselves because the phase contract keeps adapter-specific behavior out of scope.
- Local `pytest` execution remains unavailable in this environment, so validation here is limited to static coverage review and syntax checks performed in producer turns.
