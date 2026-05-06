# Implementation Notes

- Task ID: revised-standalone-spec-second-pass-cleanup-for-dd5e2acb
- Pair: implement
- Phase ID: async-branch-group-cleanup
- Phase Directory Key: async-branch-group-cleanup
- Phase Title: Async Branch-Group Cleanup
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/branch_groups/runtime.py`
- `autoloop/core/branch_groups/sessions.py`
- `autoloop/core/providers/rendered.py`
- `tests/unit/test_branch_group_context_sessions.py`
- `tests/contract/test_branch_group_runtime.py`
- `tests/runtime/test_runtime_providers.py`
- `tests/strictness/test_no_compat.py`

## Symbols touched
- `BranchGroupRuntime.run`
- `BranchGroupRuntime._execute_branch`
- `BranchGroupRuntime._branch_result_from_step_result`
- `BranchGroupRuntime._failed_branch_result`
- `BranchSessionStoreView.open`
- `BranchSessionStoreView.get`
- `BranchSessionStoreView.snapshot`
- `BranchSessionStoreView._binding_for_key`
- `BranchSessionStoreView._resolve_key`
- `RenderedLLMProvider._run_operation_turn`
- strictness scanner helpers for runtime provider turn execution
- `_provider_turn_execution_primitive_label`

## Checklist mapping
- Workstream 1 / AC-1: removed duplicate capture-mode final-state mutation from branch result payload building; failed branch results now read provider session snapshots once.
- Workstream 1 / AC-3: removed branch item-state and step-item-state initialization; scoped compiled branches now raise an internal assertion before execution.
- Workstream 2 / AC-2: branch session overlay get/open/snapshot paths are branch-local only and no longer expose parent active bindings.
- Workstream 3 / AC-6: retained sync operation bridge comment is narrowed to explicit non-parallel compatibility only; added targeted strictness coverage for `run_turn` bodies and runtime tests that provider turn execution does not reach `subprocess.run`.
- Workstream 4 / AC-4/AC-5: added regression coverage for parent-session isolation, fan-in exact-once `on_taken`, direct branch payload invariants, and defensive scoped runtime rejection.

## Assumptions
- Capture-mode final-state bookkeeping is already owned by `RouteFinalizer.capture(...)`, so branch payload construction should observe state rather than mutate it.
- Branch-group v1 keeps shared workflow state/value visibility, but not branch-local worklist/item-state runtime support.

## Preserved invariants
- Branch and fan-in execution still run through `execute_async(..., route_mode="capture")`.
- Public sync entrypoints remain outer wrappers only; no thread fallback or sync-provider fallback was added.
- Provider turn execution still uses async subprocess execution; probe-time `subprocess.run(...)` remains allowed outside `run_turn`.

## Intended behavior changes
- Branch provider/session manifests can no longer read parent active sessions when a branch never received a provider-returned session id.
- Manually constructed scoped compiled branches now fail fast with an internal assertion instead of drifting into partial worklist runtime setup.

## Known non-changes
- No provider architecture redesign, operation runtime redesign, fan-in redesign, worklist fan-out, child workflow branch/fan-in support, or async filesystem refactor.
- Compile-time branch/fan-in rejection rules remain in their existing validation paths; this phase only added focused verification around them.

## Expected side effects
- Branch hook snapshots/restores now round-trip only branch-local session bindings.
- New strictness coverage will flag sync subprocess/thread fallbacks only when they appear in provider `run_turn` execution paths, not in explicit CLI probing helpers.

## Validation performed
- `PYTHONPATH=/tmp/autoloop-test-deps:$PYTHONPATH python3 -m pytest -q tests/unit/test_branch_group_context_sessions.py tests/contract/test_branch_group_runtime.py tests/runtime/test_runtime_providers.py tests/strictness/test_no_compat.py`
- `PYTHONPATH=/tmp/autoloop-test-deps:$PYTHONPATH python3 -m pytest -q tests/unit/test_simple_surface.py::test_provider_backed_branch_steps_require_explicit_fresh_sessions_only_inside_branch_groups tests/unit/test_simple_surface.py::test_branch_group_rejects_non_fresh_verifier_sessions_inside_branch_groups tests/unit/test_simple_surface.py::test_branch_group_rejects_unsafe_names_child_workflow_fan_in_and_non_serializable_fan_out_inputs tests/unit/test_simple_surface.py::test_branch_group_rejects_operation_fan_in_steps tests/unit/test_simple_surface.py::test_branch_group_fan_in_helpers_are_rejected_outside_fan_in tests/unit/test_simple_surface.py::test_fan_in_placeholder_is_rejected_outside_fan_in_steps`
- `PYTHONPATH=/tmp/autoloop-test-deps:$PYTHONPATH python3 -m pytest -q tests/strictness/test_no_compat.py`

## Deduplication / centralization decisions
- Kept failed-branch provider session snapshot collection in one local tuple assignment instead of repeated reads.
- Added one targeted strictness scanner for provider `run_turn` bodies rather than broadening existing repo-wide subprocess restrictions.
- Normalized provider-turn primitive detection through one label helper so direct-import and attribute forms stay covered by the same strictness rule.
