# Test Strategy

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: test
- Phase ID: runtime-and-discovery-extraction
- Phase Directory Key: runtime-and-discovery-extraction
- Phase Title: Runtime And Discovery Extraction
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map
- `Engine.run_async` max-step fatal path: `tests/unit/test_runtime_and_discovery_extraction.py::test_engine_max_steps_exhaustion_emits_fatal_terminal_without_checkpoint`
- `Engine.run_async` resume/init failure path after `AWAIT_INPUT`: `tests/unit/test_runtime_and_discovery_extraction.py::test_engine_resume_input_failure_preserves_fatal_terminal_step_context`
- `Engine.run_async` `FAIL` terminal checkpoint parity: `tests/unit/test_runtime_and_discovery_extraction.py::test_engine_fail_terminal_saves_checkpoint_and_emits_terminal_state`
- `Engine.run_async` `FINISH` terminal checkpoint parity: `tests/unit/test_runtime_and_discovery_extraction.py::test_engine_finish_terminal_skips_checkpoint_and_emits_terminal_state`
- `describe_workflow_class` default entry ordering and global session resolution: `tests/unit/test_runtime_and_discovery_extraction.py::test_describe_workflow_class_preserves_default_entry_order_and_global_session`
- `describe_workflow_class` duplicate detection during namespace scan: `tests/unit/test_runtime_and_discovery_extraction.py::test_describe_workflow_class_rejects_duplicate_step_names`

## Preserved Invariants Checked
- `AWAIT_INPUT` still creates a checkpoint before resume validation and still emits terminal notifications with populated step/state context.
- `FAIL` still checkpoints the mutated state before terminal completion.
- `FINISH` still emits terminal completion without leaving a checkpoint behind on the happy path.
- Max-step exhaustion still emits `fatal` without synthesizing a new checkpoint.
- Discovery still picks the first declared step as the default entry and still binds `global_session` as the default session.
- Discovery still rejects duplicate step names at workflow class construction time.

## Existing Broader Coverage Reused
- `goto` checkpoint and dispatch parity remain covered by `tests/contract/engine/test_runtime_controls.py::test_on_taken_goto_checkpoints_target_before_next_step_dispatch`
- Terminal extension delivery across pause/fail/fatal remains covered by `tests/contract/engine/test_runtime_controls.py::test_terminal_extensions_receive_pause_fail_and_fatal_events`

## Edge Cases / Failure Paths
- Invalid resumed input payload after an `AWAIT_INPUT` checkpoint
- Duplicate workflow step names during discovery scan
- Terminal paths with and without persisted checkpoints

## Known Gaps
- This phase-local file does not duplicate the broader contract suite’s `goto` and hook sequencing coverage; it relies on the existing engine contract tests listed above to avoid redundant harnesses.
