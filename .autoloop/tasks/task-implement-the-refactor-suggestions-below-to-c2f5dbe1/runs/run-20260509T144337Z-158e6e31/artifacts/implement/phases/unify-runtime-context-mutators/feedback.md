# Implement ↔ Code Reviewer Feedback

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: implement
- Phase ID: unify-runtime-context-mutators
- Phase Directory Key: unify-runtime-context-mutators
- Phase Title: Unify Runtime Context Mutators
- Scope: phase-local authoritative verifier artifact

- IMP-001 `non-blocking` [botlane/core/branch_groups/context.py::_inherit_child_frame_bookkeeping]: The branch-child bookkeeping path still assigns `child._execution_frame.worklist_items_cache` directly instead of going through a `Context` helper. This does not affect the selection/state contract repaired by this phase, but it leaves one frame-backed cache mutation outside the new mutator surface. Minimal follow-up: only if this area is reopened, add a tiny private `Context` cache-bookkeeping helper or document this cache copy as an intentional exception.
- IMP-002 `non-blocking` [validation]: Independent rerun of the required acceptance command is currently blocked by an unrelated dirty-file syntax error in `botlane/core/branch_groups/outcomes.py`, which is outside this phase’s scoped files. The implementation notes contain a prior green run for the exact acceptance batch, and this review treated the current collection failure as workspace noise rather than an implementation defect. Minimal follow-up: fix or revert the unrelated `outcomes.py` edit before relying on fresh end-to-end validation in this workspace.
