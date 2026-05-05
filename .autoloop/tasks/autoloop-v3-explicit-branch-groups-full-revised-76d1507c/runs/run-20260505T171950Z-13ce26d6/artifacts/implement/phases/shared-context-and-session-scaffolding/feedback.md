# Implement ↔ Code Reviewer Feedback

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: implement
- Phase ID: shared-context-and-session-scaffolding
- Phase Directory Key: shared-context-and-session-scaffolding
- Phase Title: Shared Context And Session Scaffolding
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — [autoloop/core/branch_groups/context.py:85](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/branch_groups/context.py:85) and [autoloop/core/context.py:245](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/context.py:245): `create_branch_context(...)` / `create_fan_in_context(...)` do not preserve branch-scoped worklist bookkeeping correctly. They pass the parent `_selections` and `_selection_snapshots` dictionaries by reference, while the new child `Context` starts with fresh `_worklist_selection_resolver`, `_worklist_selection_sync`, and `_worklist_items_cache` defaults. Concrete failure: a branch step that uses `ctx.selection(...)`, `ctx.current_worklist`, or worklist effects can either fail immediately because the resolver callback is gone, or bleed selection mutations into the parent/sibling branches because the selection dictionaries are shared. That contradicts the requested branch-scoped bookkeeping semantics and makes the new context factory unsafe for real branch execution. Minimal fix: centralize child-context cloning so branch/fan-in contexts get their own selection bookkeeping containers plus copied resolver/sync/cache hooks where needed, instead of reusing the parent dictionaries and default-initialized runtime hooks.
