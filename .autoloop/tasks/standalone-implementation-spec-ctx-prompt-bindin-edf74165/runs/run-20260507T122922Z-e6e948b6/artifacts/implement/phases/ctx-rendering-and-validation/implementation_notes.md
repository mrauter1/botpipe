# Implementation Notes

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: implement
- Phase ID: ctx-rendering-and-validation
- Phase Directory Key: ctx-rendering-and-validation
- Phase Title: Integrate Safe ctx Prompt Rendering
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/artifacts.py`
- `autoloop/core/discovery.py`
- `autoloop/core/engine.py`
- `autoloop/core/operations.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_simple_surface.py`
- `tests/contract/test_engine_contracts.py`
- `.../decisions.txt`

## Symbols touched

- `PromptContextView`
- `resolve_artifact_template(...)`
- `render_runtime_template(...)`
- `_resolve_placeholder(...)`
- `_resolve_ctx_placeholder(...)`
- `_render_prompt_value(...)`
- `_reject_ctx_placeholders_in_artifact_template(...)`
- `_validate_simple_prompt_reference(...)`
- `_validate_ctx_prompt_reference(...)`
- `Engine._resolve_prompt(...)`
- `Engine._resolve_workflow_step_message(...)`
- `operations._resolve_prompt(...)`

## Checklist mapping

- Plan milestone 2: added lazy `ctx` runtime prompt resolution, scalar-only rendering, and artifact-path rejection in `artifacts.py`.
- Plan milestone 2: rendered `workflow_step(message=...)` through runtime templates while keeping `message_from` literal.
- Plan milestone 3: added compile-time `ctx.*` validation in `discovery.py` with spec-matched `message` / `ctx` / bare model-root failures.
- Plan milestone 3: added focused unit and engine-contract coverage for safe rendering, invalid placeholders, runtime failures, provider/operation prompt rendering, and child-workflow message rendering.
- Reviewer `IMP-001`: converted runtime-only missing `ctx.input/state/params` field lookups into `WorkflowExecutionError` and added child-workflow message regression coverage.

## Assumptions

- This phase stays scoped to rendering and validation surfaces; broader docs updates remain for a later phase or turn.
- Existing non-`ctx` placeholder rendering should remain behaviorally unchanged unless the spec explicitly required `ctx` handling.

## Preserved invariants

- `message_from` workflow-step content is still read literally with no template expansion.
- Existing non-`ctx` placeholder traversal in prompts and artifact templates remains unchanged.
- `ctx.*` is rejected for artifact paths before generic path rendering.
- `ctx.message` stays lazy because `PromptContextView` delegates to `Context` accessors instead of materializing request text eagerly.

## Intended behavior changes

- Provider-backed prompts, producer/verifier prompts, operation prompts, and workflow-step message strings now render supported `ctx.*` placeholders.
- Unsupported or unsafe `ctx.*` prompt placeholders now fail explicitly instead of leaking through or silently stringifying internals.
- Runtime-only message surfaces such as `workflow_step(message=...)` now fail explicitly on missing `ctx` model fields instead of leaking raw `AttributeError`.

## Known non-changes

- No provider adapter-specific code was changed.
- `autoloop/core/prompt_validation.py` was left unchanged because it does not perform independent dotted-placeholder validation.
- No CLI flags, run layout, or message persistence paths were changed in this phase.

## Expected side effects

- Workflows can now access `ctx.message`, `ctx.request.*`, `ctx.input.<field>`, `ctx.state.<field>`, and `ctx.params.<field>` in prompt text and workflow-step messages.
- Complex `ctx` model values now raise explicit runtime errors instead of being stringified in prompts.

## Validation performed

- `python3 -m py_compile autoloop/core/artifacts.py autoloop/core/discovery.py autoloop/core/engine.py autoloop/core/operations.py tests/unit/test_primitives_and_stores.py tests/unit/test_simple_surface.py tests/contract/test_engine_contracts.py`
- Attempted `pytest` execution, but the environment does not have `pytest` installed.
- Attempted import-level smoke execution, but the environment does not have `pydantic` installed for the system interpreter.

## Deduplication / centralization

- Runtime `ctx` safety checks reuse `validate_safe_ctx_reference(...)` from `autoloop/core/context_placeholders.py` instead of duplicating allowlists in `artifacts.py`.
- Compile-time `ctx` validation keeps shared syntax/root rules in `context_placeholders.py` and layers only model-field existence checks locally for spec-specific error messages.
