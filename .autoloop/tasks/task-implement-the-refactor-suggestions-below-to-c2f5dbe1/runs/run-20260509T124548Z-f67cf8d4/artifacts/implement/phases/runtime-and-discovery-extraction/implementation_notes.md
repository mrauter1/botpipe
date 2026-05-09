# Implementation Notes

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: implement
- Phase ID: runtime-and-discovery-extraction
- Phase Directory Key: runtime-and-discovery-extraction
- Phase Title: Runtime And Discovery Extraction
- Scope: phase-local producer artifact

## Files Changed
- `botlane/core/engine.py`
- `botlane/core/discovery.py`
- `tests/unit/test_runtime_and_discovery_extraction.py`
- `.autoloop/tasks/task-implement-the-refactor-suggestions-below-to-c2f5dbe1/runs/run-20260509T124548Z-f67cf8d4/decisions.txt`

## Symbols Touched
- `Engine.run_async`
- `Engine._prepare_run_environment`
- `Engine._new_run_loop_state`
- `Engine._restore_or_initialize_run_loop`
- `Engine._restore_run_loop`
- `Engine._initialize_run_loop`
- `Engine._build_run_context`
- `Engine._configure_context_runtime`
- `Engine._run_loop`
- `Engine._prepare_step_frame`
- `Engine._execute_step_frame`
- `Engine._emit_after_step_notification`
- `Engine._handle_step_result`
- `Engine._finish_terminal`
- `Engine._await_input_terminal`
- `Engine._fail_terminal`
- `Engine._terminal_run_result`
- `Engine._terminal_event`
- `Engine._save_loop_checkpoint`
- `Engine._handle_run_failure`
- `describe_workflow_class`
- `_discover_workflow_description_base`
- `WorkflowNamespaceScan`
- `_scan_workflow_namespace`
- `_lower_discovered_simple_steps`
- `_resolve_workflow_graph`
- `_resolve_default_session`
- `_build_workflow_definition`

## Checklist Mapping
- Phase 3 / runtime loop extraction: completed in `botlane/core/engine.py` via private environment, loop-state, step-frame, terminal, and fatal helpers.
- Phase 3 / workflow discovery extraction: completed in `botlane/core/discovery.py` via base, namespace-scan, simple-step-lowering, graph-resolution, session-resolution, and final-builder helpers.
- Phase 3 / targeted parity coverage: added focused engine and discovery tests in `tests/unit/test_runtime_and_discovery_extraction.py`.

## Assumptions
- Existing repo import failures outside this phase are not in scope for runtime/discovery extraction.
- `self.compiled.workflow_cls()` instantiation may have side effects, so the call was preserved during environment setup even though its return value is unused.

## Preserved Invariants
- Resume still restores checkpoint state, values, step/item state stores, selection snapshots, pending handoffs, and resumed input validation before entering the loop.
- Step history append timing, before/after hook notification payloads, terminal notification payloads, and fatal-notification sequencing remain unchanged.
- Fatal terminal notifications during restore/init failures still carry the partially restored `step_name` and `state`, matching the pre-refactor monolith.
- Terminal checkpoint timing remains unchanged: `FINISH` checkpoints only on terminal-notification failure; `AWAIT_INPUT` and `FAIL` checkpoint before terminal notification; `goto` still checkpoints the target stage before dispatching the next step.
- Discovery still scans visible namespace members first, lowers simple declarations second, resolves named transitions/entry after lowering, and only then applies default-entry/session resolution.

## Intended Behavior Changes
- None. This phase is internal extraction only.

## Known Non-Changes
- No checkpoint schema changes.
- No workflow graph semantics changes.
- No public runtime API changes beyond private helper extraction.
- No `build/lib/*` mirroring or package-surface cleanup.

## Expected Side Effects
- `Engine.run_async` and `describe_workflow_class` should be easier to inspect and unit-test because state setup, loop execution, and discovery passes are now separated into private phases.

## Validation Performed
- `py_compile`: `.venv/bin/python -m py_compile botlane/core/engine.py botlane/core/discovery.py tests/unit/test_runtime_and_discovery_extraction.py`
- Targeted pytest: `.venv/bin/python -m pytest tests/unit/test_runtime_and_discovery_extraction.py -q` → `3 passed`
- Revalidated after the reviewer-reported collaborator import drift: `.venv/bin/python -m py_compile botlane/core/engine.py botlane/core/discovery.py tests/unit/test_runtime_and_discovery_extraction.py && .venv/bin/python -m pytest tests/unit/test_runtime_and_discovery_extraction.py -q` → `3 passed`

## Dedup / Centralization Decisions
- Centralized context construction and checkpoint persistence in `Engine` helpers instead of repeating the same `Context(...)` and `_save_checkpoint(...)` argument lists across resume/init/terminal paths.
- Centralized workflow discovery into explicit base, scan, lower, graph, session, and build helpers instead of keeping namespace scan and graph resolution intertwined in one function.
- Kept the `botlane.sdk` stub local to the new test module so source code stays phase-scoped while the added runtime/discovery coverage remains executable.
- Kept route-finalization result typing anchored to collaborator-owned `_StepRouteResult` instead of reintroducing a second private alias in `Engine`, so branch-group runtime and engine finalization continue to share one contract.
