# Test Strategy

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: migrate-exported-workflow-contracts
- Phase Directory Key: migrate-exported-workflow-contracts
- Phase Title: Migrate Exported Workflow Packages
- Scope: phase-local producer artifact

## Coverage Map

- AC-1 compile compatibility for exported packages:
  `tests/runtime/test_workflow_integration_parity.py::test_all_repo_workflow_packages_resolve_and_compile_under_canonical_simple_surface`
  `tests/unit/test_simple_surface.py::test_exported_public_simple_workflows_no_longer_fail_for_legacy_class_handlers`
- AC-2 removed public-contract forms:
  `tests/unit/test_simple_surface.py::test_discovered_exported_workflow_sources_avoid_removed_public_contract_forms`
  Covers multi-argument hooks, `python_step(state, ctx)`, direct hook returns of `ctx.state` / `state.model_copy(...)` / `ctx.state.model_copy(...)`, and aliased replacement-state returns via `return state` / `return next_state`.
- AC-3 preserved ctx-only behavior for migrated package surfaces:
  Runtime suites use compiled public handlers through `tests/runtime/workflow_contract_helpers.py` to exercise `python_step(ctx)` and `after_verifier(ctx)` behavior without reintroducing legacy class-handler shims.
  Primary package coverage lives in:
  `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  `tests/runtime/test_security_finding_to_verified_remediation.py`
  `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  `tests/runtime/test_workflow_to_eval_suite.py`

## Preserved Invariants Checked

- Exported workflows still compile from discovered manifests without legacy-handler validation failures.
- Publication and routing behavior remains explicit:
  hidden downstream execution is still rejected in portfolio and run-history package tests.
- Question/await-input propagation remains normalized through runtime metadata:
  package tests assert `pending_input` and the explicit `handoff: None` event shape rather than legacy `pending_question` payloads.
- Workflow-builder publication regression coverage still exercises the runnable-repo-root path through existing builder package tests.

## Edge Cases / Failure Paths

- Blocked and question child-workflow outcomes in `test_security_finding_to_verified_remediation.py`.
- Invalid lifecycle posture, summary drift, and hidden execution wording in `test_workflow_portfolio_to_operating_system.py`.
- Incomplete authoritative artifacts and hidden execution wording in `test_workflow_run_history_to_failure_modes.py`.
- Direct contract-audit failures if a workflow reintroduces removed hook/python-step forms in source.

## Flake Control

- Filesystem-only tests, deterministic fake providers, and seeded timestamps / run IDs.
- No network access, no timing assertions, and no ordering assumptions beyond explicitly seeded fixtures.

## Known Gaps

- No standalone per-workflow unit test asserts every bootstrap implementation avoids local `model_copy` state staging; coverage is intentionally anchored on public contract compliance plus package-level behavior instead.
