# Implementation Notes

- Task ID: revised-sdk-implementation-spec-1-scope-implemen-1e1a7513
- Pair: implement
- Phase ID: sdk-routing-and-helper-entrypoints
- Phase Directory Key: sdk-routing-and-helper-entrypoints
- Phase Title: SDK Routing And Helper Entrypoints
- Scope: phase-local producer artifact

## Files changed
- `autoloop/sdk.py`
- `autoloop/core/engine.py`
- `tests/unit/test_sdk_facade.py`

## Symbols touched
- `Autoloop.step`
- `Autoloop.prompt_step`
- `Autoloop.produce_verify_step`
- `Autoloop.python_step`
- `Autoloop.workflow_step`
- `_build_synthetic_step_workflow`
- `_default_routes_for_step`
- `_normalize_prompt`
- `_normalize_retry_policy`
- `_materialize_child_workflow_params`
- `_step_result_route`
- `Engine._resolve_workflow_step_message`

## Checklist mapping
- M3 prompt rendering and one-step workflow correctness: completed in `autoloop/sdk.py` and `autoloop/core/engine.py`.
- M4 helper entrypoints and regression coverage: completed in `autoloop/sdk.py` and `tests/unit/test_sdk_facade.py`.
- Existing simple named declaration compatibility: preserved; no narrowing of the simple-declaration branch.

## Assumptions
- The prior retention/result-model phases remain authoritative and are not reworked here.
- Strict-step `route_metadata` support stays as a compatibility fallback when callers omit `routes=`.

## Preserved invariants
- `Autoloop.run(...)` and helper entrypoints remain thin facades over `execute_workflow_package(...)`.
- Simple named declarations still flow through the pre-existing synthetic `simple.Workflow` path unchanged.
- Branch-group and worklist-scoped SDK step rejections remain in place.

## Intended behavior changes
- Concrete `Step` executions now preserve explicit `routes=` exactly, including `SELF`.
- Default strict-step routes use `accepted -> SELF` rework looping semantics for produce/verify only when no explicit routes are provided.
- SDK helper entrypoints now construct concrete `PromptStep`, `ProduceVerifyStep`, `PythonStep`, and `ChildWorkflowStep` instances and delegate through `client.step(...)`.
- Child workflow messages can now render `input.*` placeholders the same way prompt-backed steps do.

## Known non-changes
- `StepResult.value` remains `None` in MVP.
- `llm(...)` and `classify(...)` still do not participate in retention policy handling.
- No branch-group support was added to the SDK MVP.

## Expected side effects
- Prompt/workflow-step placeholder failures now surface through the helper path with the widened `input.*` rendering support.
- Helper methods can now apply per-call retention overrides through the existing retention plumbing.

## Validation performed
- `./.venv/bin/python -m pytest tests/unit/test_sdk_facade.py -q`
- `./.venv/bin/python -m compileall autoloop/sdk.py autoloop/core/engine.py`

## Deduplication / centralization
- Helper normalization is centralized in `_normalize_prompt`, `_normalize_retry_policy`, `_materialize_child_workflow_params`, and `_step_result_route` instead of duplicating conversion logic across helper methods.
