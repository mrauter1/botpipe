# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: execution-frame-authority
- Phase Directory Key: execution-frame-authority
- Phase Title: ExecutionFrame Authority
- Scope: phase-local authoritative verifier artifact

- IMP-001 [blocking] `botlane/core/context.py::_ContextRuntime`, `botlane/core/context.py::context_runtime`, `botlane/core/engine.py::_configure_context_runtime`, `botlane/core/branch_groups/context.py::_inherit_child_runtime_bookkeeping`: the phase contract explicitly scoped removal of `context_runtime(...)` mutation helpers, but the implementation preserves that helper object and keeps the mutation call sites alive. This means ExecutionFrame is still mutated through a parallel compatibility facade instead of only through canonical frame-backed paths, so the phase objective is not actually complete and later phases still have to preserve or unwind this indirection. Minimal fix: remove `_ContextRuntime` / `context_runtime(...)` mutation entrypoints for this phase, rewrite the remaining engine/worklist/branch callers to use `ExecutionFrame` methods or explicit frame-backed helpers directly, and extend validation to assert the helper no longer exists.
