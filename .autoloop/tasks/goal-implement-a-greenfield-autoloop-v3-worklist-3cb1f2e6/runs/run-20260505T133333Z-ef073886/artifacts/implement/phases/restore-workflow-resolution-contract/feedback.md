# Implement ↔ Code Reviewer Feedback

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: restore-workflow-resolution-contract
- Phase Directory Key: restore-workflow-resolution-contract
- Phase Title: Restore Workflow Resolution Contract
- Scope: phase-local authoritative verifier artifact

## Findings

- `IMP-001` `blocking`
  File/symbol: `autoloop/core/workflow_catalog.py::_effective_catalog`
  The mixed-root fallback contract is still too coarse because shadowing happens at the whole-entry level instead of the resolution-key level. Repro: create `.autoloop/workflows/shared_demo` with `name = "shared_demo"` and `workflows/shared_demo` with the same name plus a unique alias such as `"repo-only"`; `resolve_workflow_reference(root, "repo-only")` currently raises `WorkflowDiscoveryError` even though the workspace catalog does not claim that alias. That contradicts the run-local decision that repo-local `workflows/` remains a named fallback surface when the workspace catalog does not claim the key. Minimal fix: centralize shadowing around claimed resolution keys, preserving still-unclaimed lower-precedence alias keys instead of dropping the entire lower-precedence entry once any one key collides.

- `IMP-002` `blocking`
  File/symbol: `autoloop/runtime/loader.py::_resolve_imported_class_reference`
  Direct repo-local class-object references still do not preserve the isolated workspace-module contract required by this phase. Repro: import `workflows.module_review.flow.ModuleReviewWorkflow` from a repo-local package and call `resolve_workflow_reference(root, ModuleReviewWorkflow)`; the resolved workflow class remains in `workflows.module_review.flow` instead of loading under `_autoloop_workspace_workflows...`. The accepted phase contract and run decisions explicitly call out explicit repo-local class references as isolated-reference behavior. Minimal fix: route direct repo-local `workflows.*` class references through the same isolated source-path load used for explicit path/class resolution, and move any named-resolution helper callers that need stable `workflows.*` metadata onto the named catalog path instead of depending on direct class-object references.
