# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: workflow-package-foundation
- Phase Directory Key: workflow-package-foundation
- Phase Title: Workflow Package Foundation
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `runtime/loader.py:_load_resolved_workflow`, `tests/conftest.py`
  Package-name resolution still depends on ambient `sys.path` instead of loading from the explicit `<root>` the helper already receives. Repro: from a neutral working directory with only the repository parent on `PYTHONPATH`, `discover_workflow_packages(root)` succeeds but `resolve_workflow_reference(root, "autoloop_v1")` fails with `ModuleNotFoundError: No module named 'workflows'`. That misses AC-1 and the phase deliverable to support package-name workflow resolution for CLI entry. The new tests mask the gap by globally prepending the repo root in `tests/conftest.py`, so they do not actually prove the intended contract. Minimal fix: centralize repo-root package loading inside `runtime.loader` (for example by temporarily adding `<root>` to `sys.path` or by file-loading `package_dir/__init__.py` and `workflow.py`), then add a regression test that resolves a package name from outside the repo root without pre-importable top-level `workflows`.

- IMP-002 | non-blocking | `runtime/loader.py:_import_discovered_module`, `runtime/loader.py:_repo_root_on_syspath`, `tests/runtime/test_workflow_integration_parity.py`
  Reviewer recheck: the prior blocker is resolved. Discovered package imports are now anchored to the explicit repo root supplied to the loader, and the new neutral-cwd regression test proves `resolve_workflow_reference(root, "autoloop_v1")` works without ambient repo-root `sys.path` state. No additional phase-local findings remain after rerunning the workflow-package foundation validation slice.
