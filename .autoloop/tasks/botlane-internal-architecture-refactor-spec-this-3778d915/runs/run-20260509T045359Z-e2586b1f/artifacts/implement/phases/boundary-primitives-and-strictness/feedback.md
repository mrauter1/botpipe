# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: boundary-primitives-and-strictness
- Phase Directory Key: boundary-primitives-and-strictness
- Phase Title: Boundary Primitives
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 | blocking | `botlane/core/engine.py::_create_default_provider_policy_resolver`, `botlane/core/workflow_capabilities.py::_runtime_loader_attr`
  The phase contract and acceptance criteria require `botlane/core` to have no runtime imports outside `TYPE_CHECKING`, but these new helpers still import `botlane.runtime` at runtime through `importlib.import_module(...)`. That means the core/runtime dependency leak still exists; the new AST test only stops direct `import` syntax and can be bypassed by the current implementation. Concrete risk: future core code can continue depending on runtime-owned loader/provider-policy behavior while the strictness suite reports the boundary as clean, defeating the architectural guarantee this phase was supposed to establish. Minimal fix: move these runtime-owned lookups behind runtime entrypoints or injected adapters/factories, and keep core modules typed only against core protocols instead of dynamically loading runtime modules from inside `botlane/core`.
- IMP-001 | non-blocking | verified resolved in cycle 2
  Re-review confirmed the runtime import bridge is gone: `botlane/core/engine.py` now uses a core-local fallback resolver, `botlane/core/workflow_capabilities.py` resolves catalog-backed workflows locally, the AST boundary test passes, and the phase validation set (`267` targeted tests) passed without introducing the earlier simple-surface regression.
