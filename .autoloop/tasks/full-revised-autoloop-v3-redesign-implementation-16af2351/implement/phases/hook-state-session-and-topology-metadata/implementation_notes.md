# Implementation Notes

- Task ID: `full-revised-autoloop-v3-redesign-implementation-16af2351`
- Pair: `implement`
- Phase ID: `hook-state-session-and-topology-metadata`
- Phase Directory Key: `hook-state-session-and-topology-metadata`
- Phase Title: `Hook state session and topology metadata`
- Scope: `phase-local producer artifact`

## Files Changed

- `core/descriptors.py`
- `core/__init__.py`
- `autoloop/simple.py`
- `autoloop/__init__.py`
- `core/steps.py`
- `core/validation.py`
- `core/compiler.py`
- `core/context.py`
- `core/stores/protocols.py`
- `runtime/stores/filesystem.py`
- `core/engine.py`
- `runtime/runner.py`
- `runtime/static_graph.py`
- `runtime/workspace.py`
- `tests/unit/test_simple_surface.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/contract/test_engine_contracts.py`
- `decisions.txt`

## Symbols Touched

- `StateVar`, `Param`, `effective_state_model`, `effective_parameters_model`
- `step(..., on_route=...)`, `do_review_step(..., state=..., before_do=..., after_do=..., before_review=..., after_review=..., on_route=...)`
- `Session(open=...)`, `Session.run/task/work_item/fresh`
- `CompiledStep.on_route_hook/before_do_hook/after_do_hook/before_review_hook/after_review_hook/step_state_fields`
- `CompiledWorkflow.parameters_cls/default_session_open/source_hash/topology_hash`
- `Context.step_state/item_state/step_item_state/values/artifacts/route/outcome/meta/session/reset_global_session/set_global_session/read/write/read_json/write_json`
- `CheckpointPayload.step_states/item_states/step_item_states`
- `Engine._run_before_hook/_run_after_hook/_run_route_hook/_finalize_step_result/_save_checkpoint/_assert_resume_topology_compatible`
- `workflow_topology_payload`, `write_topology_artifacts`, `update_run_metadata(..., topology=...)`

## Checklist Mapping

- Phase 3 hook contract: completed in `core/engine.py`, `core/validation.py`, `tests/contract/test_engine_contracts.py`
- StateVar / Param surface: completed in `core/descriptors.py`, `core/validation.py`, `runtime/loader.py`, `tests/unit/test_simple_surface.py`
- Context surface expansion: completed in `core/context.py`
- Global session semantics and persistence: completed in `core/steps.py`, `core/context.py`, `core/compiler.py`, `core/engine.py`, checkpoint/session store files, contract tests
- Prompt/state namespace compilation: completed in `core/validation.py`, targeted simple-surface tests
- Topology/source hash metadata and resume mismatch guard: completed in `core/compiler.py`, `runtime/static_graph.py`, `runtime/runner.py`, `runtime/workspace.py`, `core/engine.py`, runtime tests

## Assumptions

- Hook transactionality is limited to state/session rollback; hook-authored artifact writes remain observable and are revalidated afterward rather than rolled back.
- Direct `Engine.resume(...)` callers that provide a `run_folder` should receive the same topology mismatch protection as the filesystem runner.

## Preserved Invariants

- Runtime remains a compiled FSM lowered through existing validation/compiler paths.
- Route legality, provider retry behavior, child workflow invocation, and artifact validation stay centralized in the engine.
- Resume still restores checkpoint state/session/worklist state before continuing.
- Legacy compatibility aliases and additive static graph outputs remain in place.

## Intended Behavior Changes

- Hook-based route/event redirection is no longer supported; returning route overrides from `after*` hooks now fails loudly.
- `on_route` and route `on_taken` execute after route validation and before final required-write enforcement.
- Route hooks now see refreshed `ctx.artifacts` after earlier route-hook state mutations, so state-derived artifact paths remain consistent across `on_route`, route `on_taken`, and final required-write validation.
- Workflow and step descriptor defaults now materialize into runtime state/parameter models and persist through checkpoints.
- Run metadata now records topology/source hashes plus emitted topology artifact filenames, and resume fails clearly when the saved topology hash differs.

## Known Non-Changes

- Feedforward `llm()` / `classify()` operations are still out of scope.
- No top-level parallel FSM execution was added.
- Legacy `StrictWorkflow` behavior beyond compatibility identity was not refactored in this phase.
- Step visit metadata is exposed per in-memory execution segment; no new persisted visit counter was introduced.

## Expected Side Effects

- Filesystem `run.json` gains a `topology` section.
- Filesystem checkpoints now carry step/item/step-item state dictionaries.
- Event logs can now include `hook_started`, `hook_finished`, and `hook_failed` entries when a runtime sink is present.
- Topology artifact payloads include source/topology hashes and richer hook/state/session metadata.

## Deduplication / Centralization Decisions

- Descriptor-backed workflow state/params were centralized in `core/descriptors.py` rather than duplicated across validation and loader code.
- Hook execution semantics were centralized in `core/engine.py` helpers instead of adding separate per-step implementations.
- Route-hook artifact refresh stays centralized inside `Engine._finalize_step_result` so both `on_route` and route `on_taken` share the same state-driven artifact re-resolution path.
- Resume mismatch guarding is enforced both in the generic runner and the engine path to cover filesystem and direct-engine callers consistently.

## Validation Performed

- `python3 -m py_compile core/engine.py core/validation.py runtime/runner.py runtime/static_graph.py runtime/workspace.py runtime/tracing.py`
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py -q`
- `./.venv/bin/python -m pytest tests/runtime/test_runtime_static_graph.py tests/runtime/test_workspace_and_context.py tests/contract/test_engine_contracts.py -q`
- `python3 -m py_compile core/engine.py tests/contract/test_engine_contracts.py`
- `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -q`
- `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -q -k "route_hook or on_route_hook_runs_before_required_output_validation or after_hook_state_mutation_re_resolves_artifact_paths_before_final_output_validation"`
- `./.venv/bin/python -m pytest tests/runtime/test_workspace_and_context.py -q`
