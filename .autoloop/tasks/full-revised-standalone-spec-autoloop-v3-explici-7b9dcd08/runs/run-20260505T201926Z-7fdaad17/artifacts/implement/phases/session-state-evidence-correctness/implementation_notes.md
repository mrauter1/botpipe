# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: session-state-evidence-correctness
- Phase Directory Key: session-state-evidence-correctness
- Phase Title: Session, State, Evidence
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/branch_groups/sessions.py`
- `tests/unit/test_branch_group_context_sessions.py`
- `tests/contract/test_branch_group_runtime.py`

## Symbols touched
- `BranchSessionStoreView.open`
- `BranchSessionStoreView.get`
- `BranchSessionStoreView._binding_for_key`
- `BranchSessionStoreView._resolve_key`
- `BranchSessionStoreView._branch_fresh_key`

## Checklist mapping
- Plan milestone 4 / shared-context, session, and evidence correctness:
  - Completed: branch-local fresh session keys now stay branch-scoped and no longer fabricate provider ids.
  - Completed: provider-backed fresh branch lookups no longer inherit parent active sessions.
  - Verified: workflow-folder `_branch_groups/...` evidence and per-branch raw output paths remain the runtime path used by branch-group execution and tracing.
  - Verified: shared state/value semantics remain lock-free and unchanged in this phase.

## Assumptions
- `BranchSessionStoreView(namespace=...)` already receives a deterministic branch execution namespace from the branch-group runtime (`<group>:<branch>:<index>` or equivalent test namespace).
- Provider adapters will continue to treat `SessionBinding(session_id=None)` as a fresh-start request and return a real session id when resumability exists.

## Preserved invariants
- Branch-local session activation does not mutate the parent session store.
- Shared `Context.state_cell` and shared `ctx.values` behavior remain unchanged and lock-free.
- Branch-group evidence and raw output files remain rooted under `{workflow_folder}/_branch_groups/...`.

## Intended behavior changes
- Fresh branch sessions now open with `session_id=None` instead of synthetic ids.
- Fresh branch session keys are rewritten under the branch execution namespace.
- Repeated fresh lookups for the same slot within one branch execution now resolve to the active branch-local fresh binding instead of creating a sibling binding or falling back to the parent active slot.
- Branch manifests now only surface provider session ids that were actually returned by the provider.

## Known non-changes
- No workspace overlay or merge behavior was added.
- No parent/session semantics were changed for non-branch execution.
- No branch-group runtime scheduling or evidence rendering logic was refactored in this phase.

## Expected side effects
- Tests and any callers that previously assumed pre-provider synthetic branch session ids must now expect `None` on the first provider turn.
- Branch-local fresh `SessionKey.value` strings now include the branch namespace prefix.

## Validation performed
- `./.venv/bin/pytest tests/unit/test_branch_group_context_sessions.py`
- `./.venv/bin/pytest tests/contract/test_branch_group_runtime.py`
- `./.venv/bin/pytest tests/runtime/test_runtime_tracing.py -k branch_group`

## Deduplication / centralization
- Kept the fresh-session overlay fix localized to `BranchSessionStoreView` so engine/session selection code can continue using the existing `Context` and step-dispatch entrypoints without branch-specific conditionals.
