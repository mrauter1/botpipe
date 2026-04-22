# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: docs-tests-and-legacy-removal
- Phase Directory Key: docs-tests-and-legacy-removal
- Phase Title: Docs Tests And Legacy Removal
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — `runtime.loader._import_discovered_module` still resolves discovered packages through the shared `workflows.*` module cache, so explicit `root` is not authoritative once one workflow package has already been imported in the current Python process. Repro: resolve `"demo"` from one temp root, then resolve `"demo"` from a different temp root in the same process; the second resolution returns the first root’s class (`WorkflowA` twice). The new optional-extension and package-cli tests avoid this only by manually clearing `sys.modules`, which masks a real runtime bug for library callers and long-lived processes. Minimal fix: centralize root-scoped module isolation in `runtime.loader` (for example by evicting stale `workflows` modules for the active root or importing discovered workflow modules under a root-specific namespace) instead of relying on callers/tests to clear caches.
