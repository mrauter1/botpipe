# Test Strategy

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: test
- Phase ID: finish-ctx-request-input-separation
- Phase Directory Key: finish-ctx-request-input-separation
- Phase Title: Finish Ctx Request And Input Separation
- Scope: phase-local producer artifact

## Behavior Coverage Map

- AC-1 request/input separation:
  - `tests/unit/test_primitives_and_stores.py`
  - `tests/unit/test_simple_surface.py`
  - `tests/contract/test_engine_contracts.py`
  - Covers undeclared `{ctx.input.message}` rejection at render-time and compile-time, plus declared-`Input.message` positive paths.
- AC-2 request text through `ctx.message`:
  - `tests/contract/test_engine_contracts.py`
  - Covers provider prompts, operation prompts, and `workflow_step(message=...)` rendering through `{ctx.message}`.
- AC-3 file-backed fresh/resume snapshot authority:
  - `tests/runtime/test_workspace_and_context.py`
  - Covers mutated task-level `request.md` after run creation while fresh/resumed contexts continue reading the run-local snapshot.
- AC-4 unreadable run-local snapshot failure:
  - `tests/contract/test_engine_contracts.py`
  - Covers engine-backed `ctx.message` access raising `WorkflowExecutionError` after the authoritative run snapshot becomes unreadable post-construction.
- AC-5 child input remains distinct from request text:
  - `tests/contract/test_engine_contracts.py`
  - `tests/runtime/test_workspace_and_context.py`
  - Covers child workflow-step message forwarding, child typed input staying separate, and resumed runtime contexts proving undeclared input does not gain `message`.
- AC-6 shared compatibility boundary:
  - `tests/unit/test_primitives_and_stores.py`
  - `tests/unit/test_validation.py`
  - `tests/runtime/test_workspace_and_context.py`
  - Covers direct Python `ctx.input.message` / `ctx.input.model_dump()` following declared fields only, explicit `Input.message` acceptance, and legacy bare `{input.message}` as isolated compatibility behavior.

## Preserved Invariants Checked

- `ctx.message` and `ctx.request.text` remain the built-in request-text bindings.
- Bare `{input.message}` compatibility stays isolated and does not restore aliasing on `ctx.input`.
- Explicit `Input.message` remains supported instead of being globally banned.

## Edge Cases And Failure Paths

- Missing declared input fields reject `ctx.input.*` references deterministically.
- Run-local `request.md` deletion after context construction raises the documented `WorkflowExecutionError`.
- Resume continues using the persisted run-local snapshot even if the task-level request file changes later.

## Stabilization Notes

- Coverage is deterministic: filesystem-local temporary workspaces, scripted providers, and explicit JSON captures replace timing-sensitive assertions.
- No network access, nondeterministic ordering, or background concurrency is involved.

## Known Gaps

- Validation for this phase was rerun on the focused request/input separation suites rather than the full repository matrix.
