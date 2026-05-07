# Test Cleanup Plan

## Objective
Clean `tests/` so it covers shared Autoloop v3 framework behavior only. Remove tests whose real ownership belongs to repo-owned workflow packages, `recursive_autoloop`, or repo docs, and repair the remaining shared tests so they rely only on synthetic fixtures created under `tmp_path`.

## Confirmed Scope
- In scope: edits under `tests/` only.
- In scope: deleting misowned or stale tests from `tests/`, rewriting shared tests that currently import or copy repo-owned workflow/docs assets, and splitting oversized retained test modules when the move is mechanical.
- Out of scope: re-homing tests into `autoloop/workflows/*`, `recursive_autoloop/*`, or docs-owned folders; modifying product code, packaging config, or CI config outside `tests/`.

## Ownership Boundaries
- `tests/` should contain framework-shared contracts only: engine/runtime, loader/catalog/workspace behavior, SDK facade, stdlib helpers, extensions, optimizer helpers, and workflow discovery/authoring behavior exercised through generated fixtures.
- Tests in `tests/` must not read repo-owned `docs/*`, `recursive_autoloop/*`, or concrete workflow package contents under `autoloop/workflows/*`.
- Remaining tests may still assert canonical repo-relative labels such as `autoloop/workflows/<name>/...` when those labels are emitted from synthetic fixtures under `tmp_path`, not from repo-owned assets.

## Milestones
### 1. Unblock collection and remove obviously out-of-scope coverage
- Delete `tests/runtime/test_workflow_integration_parity.py`.
- Delete `tests/test_architecture_baseline_docs.py`.
- Rewrite `tests/runtime/test_wheel_packaging_smoke.py` to cover wheel build, install, CLI/help exposure, and `import autoloop` only; drop packaged workflow asset assertions.
- Remove the recursive-wrapper tests from `tests/runtime/test_package_cli.py`.
- Remove `test_ctx_runtime_prompt_docs_describe_preferred_bindings_and_snapshot_semantics` from `tests/contract/test_engine_contracts.py`.
- Remove the two bundled-workflow export tests from `tests/unit/test_simple_surface.py`.
- Remove top-level `autoloop.workflows.*.contracts` imports from `tests/unit/test_stdlib_and_extensions.py` and replace those constants with local test fixtures/spec objects.

### 2. Remove misowned workflow/docs suites from `tests/` and repair shared survivors
- Delete the workflow-package/runtime owner suites from `tests/runtime/`:
  `test_candidate_workflow_to_adapted_execution_plan.py`,
  `test_company_operation_to_recursive_improvement_cycle.py`,
  `test_incident_to_hardening_program.py`,
  `test_investigation_request_to_evidence_pack.py`,
  `test_release_candidate_to_go_no_go.py`,
  `test_security_finding_to_verified_remediation.py`,
  `test_task_to_candidate_workflow_set.py`,
  `test_task_to_workflow_strategy.py`,
  `test_workflow_and_eval_to_refined_workflow_package.py`,
  `test_workflow_builder_package.py`,
  `test_workflow_package_to_composable_building_blocks.py`,
  `test_workflow_portfolio_to_operating_system.py`,
  `test_workflow_run_history_to_failure_modes.py`,
  `test_workflow_run_traces_to_optimization_candidates.py`,
  `test_workflow_to_eval_suite.py`.
- Rewrite `tests/unit/test_optimization_helpers.py` so `_install_selected_workflow()` creates a minimal synthetic workflow package under `tmp_path / "workflows"` and any needed doc fixture content locally instead of `copytree()` from repo roots.
- Continue trimming `tests/unit/test_stdlib_and_extensions.py` so shared helper tests that survive do not read repo docs directly; keep tests that generate their own workflow package/docs fixtures under `tmp_path`.
- Narrow `tests/strictness/test_no_compat.py` to maintained shared roots (`autoloop/`, `autoloop_optimizer/`, `tests/`) and remove assertions that expect docs, packaged workflows, or recursive assets to remain part of the shared test scan.
- Do not add a marker-based optional suite under `tests/`; the clarified intent is to remove misowned coverage from `tests/`, not to keep it hidden behind collection hooks.

### 3. Split retained monoliths after behavior is stable
- Split `tests/unit/test_stdlib_and_extensions.py` into domain-aligned files such as `tests/unit/stdlib/`, `tests/unit/extensions/`, and `tests/unit/optimizer/`, moving helpers only when that reduces repeated imports and keeps ownership obvious.
- Split `tests/contract/test_engine_contracts.py` into `tests/contract/engine/*` modules grouped by artifacts, routes, sessions, hooks, worklists, child workflows, runtime controls, prompt context, and errors/retries.
- Keep the split mechanical: preserve assertions, helper behavior, and import surfaces except for the intentional removals already listed above.

## Validation
- Run `pytest --collect-only tests` after Milestone 1 to confirm collection is unblocked.
- Run targeted suites after Milestone 2:
  `pytest tests/unit/test_simple_surface.py tests/unit/test_stdlib_and_extensions.py tests/unit/test_optimization_helpers.py tests/runtime/test_wheel_packaging_smoke.py tests/runtime/test_package_cli.py tests/strictness/test_no_compat.py -q`
- Re-run the retained runtime/shared workflow coverage that should continue to protect current behavior:
  `pytest tests/runtime/test_golden_workflow.py tests/runtime/test_workflow_catalog_roots.py tests/runtime/test_workflow_reference_resolution.py tests/runtime/test_workspace_and_context.py -q`
- After Milestone 3, run `pytest --collect-only tests/contract tests/unit` plus the moved modules' direct invocations to catch import or helper-scope regressions.

## Compatibility Notes
- Intentional behavior change: `tests/` will stop validating repo docs, recursive wrapper assets, and concrete repo-owned workflow package contents.
- No runtime/public API behavior is changed by this task; only the ownership and scope of shared tests changes.
- Re-homing any deleted coverage into workflow-owned or recursive-owned directories is a separate follow-up outside this task because edits are restricted to `tests/`.

## Regression Controls
- Preserve tests that create workflow packages under `tmp_path` and exercise current loader/catalog/workspace behavior; they remain in scope even if expected payloads use canonical `autoloop/workflows/...` labels.
- Treat direct reads from `REPO_ROOT / "docs"`, `REPO_ROOT / "recursive_autoloop"`, or `REPO_ROOT / "autoloop" / "workflows"` as the removal criterion for shared tests, not mere string mentions.
- Prefer local fixture replacement over broad assertion removal when a shared test is still validating current framework behavior.

## Risk Register
- R1: Over-deleting legitimate workflow runtime coverage.
  Control: keep generated-fixture workflow tests and only remove suites that assert owner-specific repo assets or package contents.
- R2: Breaking collection while refactoring large files.
  Control: remove top-level blockers first, then run `pytest --collect-only tests` before deeper structural moves.
- R3: Under-testing wheel/package exposure after smoke-test rewrite.
  Control: retain wheel build, install, CLI help, and `import autoloop` checks; only drop bundled asset expectations.
- R4: Narrowing strictness scans too far.
  Control: keep all compatibility bans against maintained shared roots and remove only asset-scope expectations that no longer belong in `tests/`.

## Rollback
- If a deletion removes needed shared coverage, restore the specific test file from git and convert it to synthetic fixtures instead of repo-root asset reads.
- If monolith splitting introduces import churn, revert the file moves while keeping the intentional stale-test removals.
- If a fixture rewrite misses required metadata, keep the existing assertion payload shape but source it from locally-created `tmp_path` content.
