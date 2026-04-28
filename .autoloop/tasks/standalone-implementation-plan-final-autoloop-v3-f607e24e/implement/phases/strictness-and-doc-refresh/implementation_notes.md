# Implementation Notes

- Task ID: standalone-implementation-plan-final-autoloop-v3-f607e24e
- Pair: implement
- Phase ID: strictness-and-doc-refresh
- Phase Directory Key: strictness-and-doc-refresh
- Phase Title: Strictness And Documentation Refresh
- Scope: phase-local producer artifact

## Files changed

- `tests/strictness/test_no_compat.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/runtime/test_package_cli.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `autoloop/__init__.py`
- `autoloop/simple.py`
- `workflow/__init__.py`
- `core/compiler.py`
- `docs/architecture.md`
- `docs/authoring.md`
- `cleanup.md`
- `core/engine.py`

## Symbols touched

- `tests.strictness.test_no_compat._iter_active_text_files`
- `tests.strictness.test_no_compat.test_active_tree_does_not_reintroduce_removed_compatibility_surfaces`
- `workflow.primitives.__all__` expectations
- `CompiledWorkflow.artifact_items`
- `Engine._ensure_retry_failure_context`
- simple-surface declaration docstrings in `autoloop/simple.py`

## Checklist mapping

- Plan Step 6 / AC-1: expanded strictness scan to maintained roots, added forbidden-term coverage for removed route-contract, `contracts_path`, `BoardMutation`, and generated-handler identifiers, and added public API assertions for `BoardMutation` absence plus `workflow.primitives` restrictions.
- Plan Step 7 / AC-2: refreshed active docstrings and docs to describe `autoloop.simple` / `autoloop` as the authoring surface and removed stale future-lowering and compatibility phrasing in active maintained files.
- Plan Step 7 / AC-3: kept `workflow.primitives` as a runtime-only primitive shim and tightened tests to reject authoring helpers and step classes there.
- Out-of-phase verification fix: updated `Engine._ensure_retry_failure_context` so retry-exhaustion checkpoints backfill `provider_attributable=True` for `ProviderExecutionError`, matching the earlier retry-aware event-validation contract during full-suite regression verification.

## Assumptions

- The maintained-tree anti-regression scan should target framework-owned roots, not user workflow packages or archived docs.
- `cleanup.md` is part of the active maintained documentation surface expected by the repo baseline tests.

## Preserved invariants

- `workflow/` remains non-authoring; `workflow.primitives` exports runtime primitives only.
- `contracts.py` remains allowed only as a user support/spec filename, not as a public payload key or compatibility surface.
- Public workflow docs continue to point authors at `autoloop.simple` or `autoloop`.

## Intended behavior changes

- Repo-wide strictness now fails if removed route-contract terminology, `contracts_path` payload names, `BoardMutation`, or generated workflow-step handler identifiers reappear in maintained source/docs/tests.
- Active docs and module docstrings now describe the current greenfield model without future-lowering or compatibility-surface framing.
- Provider retry exhaustion checkpoints now reliably retain `provider_attributable=True` in failure context.

## Known non-changes

- Did not broaden the strictness scan into `legacy_docs/`, `recursive_autoloop/`, or `workflows/` package content.
- Did not change runtime semantics beyond the retry-failure-context metadata backfill required by the existing contract tests.

## Expected side effects

- Tests that need to assert removed payload keys now construct those keys indirectly so the maintained-tree token scan can include `tests/`.
- `cleanup.md` now exists as an active working-tree note for doc-baseline coverage.

## Validation performed

- `rg -n "RouteContract|route_contracts|route_required_artifacts|route contract|route-contract|review_gate_contracts|publication_gate_contracts|contracts_path|contracts_path_repo_relative|BoardMutation|_install_simple_workflow_step_handler" autoloop core runtime stdlib workflow tests docs Workflow_Instructions.md cleanup.md`
- `rg -n "Additive public authoring surface|Foundation declaration for future|compatibility alias|legacy workflow shim|legacy workflow path|preferred progressive authoring surface|compatibility/raw-mapping|legacy support files|legacy package conventions|Legacy packages may continue|additive public|future simple-step lowering" autoloop core runtime stdlib workflow docs tests Workflow_Instructions.md cleanup.md`
- `.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/test_architecture_baseline_docs.py tests/unit/test_primitives_and_stores.py tests/runtime/test_package_cli.py tests/runtime/test_compatibility_runtime.py tests/unit/test_stdlib_and_extensions.py -q`
- `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py::test_provider_invalid_question_retry_exhaustion_marks_failure_context -q`
- `.venv/bin/python -m pytest -q`

## Deduplication / centralization decisions

- Centralized the removed-token policy in `tests/strictness/test_no_compat.py` and converted other test assertions to indirect token construction instead of excluding large portions of `tests/` from the scan.
