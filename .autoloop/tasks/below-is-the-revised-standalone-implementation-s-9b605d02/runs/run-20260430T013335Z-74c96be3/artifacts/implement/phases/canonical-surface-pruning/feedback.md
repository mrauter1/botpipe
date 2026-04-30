# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: canonical-surface-pruning
- Phase Directory Key: canonical-surface-pruning
- Phase Title: Prune Public And Top-Level Surfaces
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` `[autoloop_v3/core/__init__.py:5-15]`: Replacing the old `sys.modules` bridge with a package-level wrapper only aliases `autoloop_v3.core` itself; it does not unify `core.*` and `autoloop_v3.core.*` submodules. That splits class identity for `Step`, `WorkflowMeta`, and validation helpers, so workflows authored against `core.Workflow` are no longer recognized on the `autoloop_v3.core` loader path. Concrete repro: `autoloop_v3.core.validation.is_workflow_class(Demo)` is `False` while `core.validation.is_workflow_class(Demo)` is `True`, and `./.venv/bin/pytest tests/runtime/test_compatibility_runtime.py::test_resolve_workflow_reference_preserves_same_root_workflow_class_identity -q` now fails with `WorkflowDiscoveryError: no workflow class was found in module 'workflows.demo.workflow'` at [tests/runtime/test_compatibility_runtime.py:830-840](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_compatibility_runtime.py:830). Minimal fix: keep the alias replacement centralized in one compatibility bridge that also aliases `autoloop_v3.core.*` submodules to the already-loaded `core.*` modules, or replace the bridge with real wrapper modules that preserve shared object identity instead of creating a parallel package tree.

- IMP-002 `blocking` `[tests/unit/test_validation.py:7-15] [tests/contract/test_engine_contracts.py:10-33]`: The phase decisions explicitly restrict `SUCCESS`, `RouteInfo`, `route_infos`, and related legacy names to `tests/runtime/test_compatibility_runtime.py` and explicitly renamed compatibility fixtures only, but this change rewires active suites onto `autoloop_v3.core._compat` and keeps their legacy assertions alive in the maintained test surface. That directly contradicts [decisions.txt:2-7](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/below-is-the-revised-standalone-implementation-s-9b605d02/runs/run-20260430T013335Z-74c96be3/decisions.txt:2), leaves the requested compatibility boundary unenforced in active tests, and is already reflected in the broader targeted run staying red on legacy expectations. Minimal fix: limit `_compat` imports to explicit compatibility/migration suites only, and either migrate these active suites to `FINISH` / `required_writes` / canonical public APIs or move their remaining legacy-only cases into clearly named compatibility coverage outside the maintained active surface.
