# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: migrate-exported-workflow-contracts
- Phase Directory Key: migrate-exported-workflow-contracts
- Phase Title: Migrate Exported Workflow Packages
- Scope: phase-local authoritative verifier artifact

- TEST-001 | Strengthened the repo-level raw contract audit in `tests/unit/test_simple_surface.py` to also fail on aliased replacement-state returns (`return state` / `return next_state`) in exported workflow sources, then revalidated the source-audit and discovered-package compile gates with `./.venv/bin/pytest -q tests/unit/test_simple_surface.py::test_discovered_exported_workflow_sources_avoid_removed_public_contract_forms tests/runtime/test_workflow_integration_parity.py::test_all_repo_workflow_packages_resolve_and_compile_under_canonical_simple_surface` (`2 passed`).
- TST-000 | non-blocking | No additional audit findings. Independent auditor reran `./.venv/bin/pytest -q tests/unit/test_simple_surface.py::test_discovered_exported_workflow_sources_avoid_removed_public_contract_forms tests/runtime/test_workflow_integration_parity.py::test_all_repo_workflow_packages_resolve_and_compile_under_canonical_simple_surface` and confirmed the tightened raw-contract guard plus discovered-package compile gate still pass (`2 passed`).
