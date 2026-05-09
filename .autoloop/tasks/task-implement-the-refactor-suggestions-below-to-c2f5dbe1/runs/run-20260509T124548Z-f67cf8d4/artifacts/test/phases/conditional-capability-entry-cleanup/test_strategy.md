# Test Strategy

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: test
- Phase ID: conditional-capability-entry-cleanup
- Phase Directory Key: conditional-capability-entry-cleanup
- Phase Title: Conditional Workflow Capability Entry Cleanup
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Activation gate: confirmed `botlane/core/workflow_capabilities.py` was not opened by adjacent source work in this run, so no new repository tests were added for `_capability_entry_from_resolved`.
- Preserved capability-inspection surface: existing coverage remains anchored on `tests/runtime/test_workflow_reference_resolution.py`, especially the `inspect_workflow_reference(...)` paths at lines 424, 434, and 468.
- Preserved invariants checked: hotspot 9 remains explicit and deferred in the ordered phase plan and run decisions; no source diff exists for `botlane/core/workflow_capabilities.py`.

## Edge Cases And Failure Paths

- Deferred-slice guard: later turns must not add standalone readability tests for `_capability_entry_from_resolved` unless the source file is already open for adjacent work.
- If the slice activates later, add focused parity tests for catalog fallback fields, inferred support-path lists, non-default session projection, and compiled route/artifact/step payload shape.

## Validation Performed

- `py_compile`: `.venv/bin/python -m py_compile botlane/core/workflow_capabilities.py tests/runtime/test_workflow_reference_resolution.py`
- Attempted targeted pytest: `.venv/bin/python -m pytest tests/runtime/test_workflow_reference_resolution.py -k 'inspect_workflow_reference or capability_inspection or simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection' -q`

## Stabilization And Flake Notes

- No timing, network, or ordering flake risk was introduced because no new tests were added.
- The targeted pytest path is currently blocked during module collection by an unrelated import failure: `ImportError: cannot import name 'context_runtime' from 'botlane.core.context'` via `botlane.sdk`. This phase does not normalize that broader runtime issue into new expectations.

## Known Gaps

- No new capability-entry parity tests were authored in this phase because the conditional slice never activated.
- Full runtime validation of the existing capability-inspection surface remains blocked until the unrelated `botlane.sdk` import drift is resolved elsewhere.
