# Implementation Notes

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: implement
- Phase ID: runtime-input-contract
- Phase Directory Key: runtime-input-contract
- Phase Title: Refactor Runtime Input Contract
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/context.py`
- `autoloop/core/branch_groups/context.py`
- `autoloop/core/engine.py`
- `autoloop/core/artifacts.py`
- `autoloop/core/discovery.py`
- `autoloop/runtime/runner.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_branch_group_context_sessions.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched
- `WorkflowInputView`
- `Context.message`
- `Context.input_fields`
- `Context.input`
- `Engine.run`, `Engine.run_async`, `Engine.resume`, `Engine.resume_async`
- `create_branch_context`, `create_fan_in_context`
- `render_runtime_template`, `resolve_artifact_template`
- `_validate_ctx_prompt_reference`

## Checklist mapping
- Runtime input contract refactor: complete
- Context propagation for root/resume/branch/fan-in: complete
- Request snapshot and `workflow_input` persistence separation: preserved
- Regression coverage for context/message/input behavior: added focused unit/contract coverage

## Assumptions
- This phase remains runtime-scoped; SDK facade entrypoints and `Workflow.Input.message` compile rejection stay for later phases.
- Existing direct `Context(...)` callers still need legacy `request.md`-backed `ctx.message` when they do not pass `message`.

## Preserved invariants
- `workflow_input` persistence remains typed-fields-only; no message data is written into run metadata.
- Normal runtime and resume flows keep `ctx.message` equal to the persisted run-local request snapshot.
- Branch/fan-in clones reuse raw typed input models via `input_fields`, not the composite `ctx.input` view.

## Intended behavior changes
- Runtime contexts now expose `ctx.input.message` and `ctx.input_fields` while keeping raw typed input available separately from `ctx.message`.
- Explicit `message=None` is preserved on `Context`, allowing a message-less runtime view even when a request snapshot file exists.
- Artifact template resolution now supports bare `{input.message}` / `{input.<field>}` lookups through the composite input view.
- Simple-step safe placeholder validation now accepts `ctx.input.message`.

## Known non-changes
- No SDK public API, pause loop, or async facade work was added in this phase.
- No change to persisted `request.md` ownership or child-workflow dict-input compatibility.

## Expected side effects
- Prompt and workflow-step message rendering can now treat `ctx.input.message` as an alias of `ctx.message`.
- Branch/fan-in nested contexts now retain both the parent message and raw typed input fields without conflating them.

## Validation performed
- `python3 -m py_compile` on touched runtime/core modules and the touched tests.
- Attempted focused `pytest` execution, but the environment lacks `pytest`.
- Attempted focused runtime assertions, but the environment Python also lacks installed runtime dependencies such as `pydantic`.

## Deduplication / centralization
- Kept composite input behavior centralized in `Context` and runtime placeholder resolution instead of adding per-callsite adapters.
- Kept resume message alignment centralized in `runtime/runner.py` by reusing the persisted run snapshot text for both root and resumed Engine entry.
