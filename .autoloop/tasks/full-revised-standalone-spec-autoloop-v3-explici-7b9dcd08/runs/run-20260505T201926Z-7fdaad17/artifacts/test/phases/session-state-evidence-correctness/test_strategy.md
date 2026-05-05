# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: session-state-evidence-correctness
- Phase Directory Key: session-state-evidence-correctness
- Phase Title: Session, State, Evidence
- Scope: phase-local producer artifact

## Behavior-to-test coverage

- AC-1: branch-local fresh sessions stay isolated from the parent session store.
  - `tests/unit/test_branch_group_context_sessions.py`
    - `test_branch_session_store_view_keeps_activation_local_to_branch`
    - `test_engine_session_selection_and_persistence_follow_context_store`
  - `tests/contract/test_branch_group_runtime.py`
    - `test_fan_out_renders_branch_input_roots_artifacts_and_keeps_branch_sessions_local`

- AC-2: first fresh branch turn uses `session_id=None`, and manifests only surface real provider-returned ids.
  - Positive path:
    - `tests/contract/test_branch_group_runtime.py`
      - `test_fan_out_renders_branch_input_roots_artifacts_and_keeps_branch_sessions_local`
  - Negative path:
    - `tests/contract/test_branch_group_runtime.py`
      - `test_parallel_branch_group_leaves_manifest_provider_session_empty_without_provider_returned_id`

- AC-3: runtime-owned branch evidence and raw outputs stay under `workflow_folder/_branch_groups/...`.
  - `tests/contract/test_branch_group_runtime.py`
    - `test_fan_out_renders_branch_input_roots_artifacts_and_keeps_branch_sessions_local`
  - `tests/runtime/test_runtime_tracing.py -k branch_group`

## Preserved invariants checked

- Shared `Context.state_cell` and shared `ctx.values` behavior remain intact for branch contexts.
- Parent session activation remains unchanged after branch-local fresh selection and persistence.
- Manifest branch order and artifact path assertions remain deterministic.

## Edge cases covered

- Repeated fresh lookups in one branch execution reuse the active branch-local binding.
- Provider returns a real session id after receiving `session_id=None`.
- Provider returns no session id at all, and the manifest must not regress to synthetic or parent-derived ids.

## Failure paths / flake control

- No new timing-sensitive assertions were introduced; the new contract case is single-branch and synchronous from the test’s perspective.
- Existing concurrent branch tests remain declaration-order based when reading the manifest rather than provider call completion order.

## Known gaps

- No additional fan-in-specific session assertions were added in this phase because fan-in still runs on normal parent session semantics and the phase contract scoped the change to branch-local session overlays and evidence paths.
