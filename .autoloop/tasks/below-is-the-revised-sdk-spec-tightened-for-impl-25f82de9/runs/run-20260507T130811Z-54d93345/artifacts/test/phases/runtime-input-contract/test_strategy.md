# Test Strategy

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: test
- Phase ID: runtime-input-contract
- Phase Directory Key: runtime-input-contract
- Phase Title: Refactor Runtime Input Contract
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- AC-1 direct context surface:
  - `tests/unit/test_primitives_and_stores.py`
  - Covers `ctx.message`, `ctx.input.message`, `ctx.input_fields`, `ctx.input.model_dump()`, explicit `message=None`, and lazy fallback when `request.md` is absent.
- AC-1 runtime rendering and persistence separation:
  - `tests/unit/test_primitives_and_stores.py`
  - Covers `ctx.input.message` prompt rendering and `{input.message}` artifact-template rendering.
  - `tests/runtime/test_workspace_and_context.py`
  - Covers persisted `workflow_input` remaining typed-fields-only in run metadata.
- AC-2 branch and fan-in propagation:
  - `tests/unit/test_branch_group_context_sessions.py`
  - Covers child contexts preserving parent message while reusing raw `input_fields`, not the composite view.
- AC-2 child workflow propagation:
  - `tests/contract/test_engine_contracts.py`
  - Covers child workflow message forwarding/rendering with separate `input.message` and raw `input_fields`.
- AC-2 resume propagation:
  - `tests/runtime/test_workspace_and_context.py`
  - Covers resumed contexts keeping the run-local message snapshot, `ctx.input.message`, and stored raw `input_fields` after task-level request mutation.

## Preserved invariants checked
- `workflow_input` persisted metadata excludes `message`.
- Normal runtime/resume flows keep `ctx.message` aligned with the run-local request snapshot.
- Direct typed-input access still works without a request snapshot until code actually reads `ctx.message` / `ctx.input.message`.

## Edge cases and failure paths
- Explicit `message=None` with typed input.
- Missing `request.md` for direct `Context(...)`.
- Task-level request mutation between paused and resumed segments.
- No typed input provided when `ctx.input.<field>` is rendered.

## Flake-risk notes
- Tests are filesystem-local and provider-scripted; no timing, network, or nondeterministic ordering dependencies were added.

## Known gaps
- Full suite execution was not possible in this environment because `pytest` and runtime deps were unavailable, so this phase relies on deterministic test authoring plus `py_compile` syntax validation here.
