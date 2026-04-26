# Test Strategy

- Task ID: recursive-framework-evolution-20260426t124100-c1
- Pair: test
- Phase ID: proof-docs-memory-closeout
- Phase Directory Key: proof-docs-memory-closeout
- Phase Title: Proof And Memory Closeout
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Typed publication-authoring preference:
  - Coverage: `tests/test_architecture_baseline_docs.py::test_authoring_doc_describes_typed_json_artifact_boundary`
  - Checks: the authoring guide now preserves the "default publish-handler entrypoint" wording for workflow-local typed artifact reads.
- Current-cycle recursive-memory closeout:
  - Coverage: `tests/test_architecture_baseline_docs.py::test_recursive_memory_records_current_typed_publication_closeout`
  - Checks: charter, roadmap, gap ledger, workflow candidate ledger, and validation debt ledger all record the current typed-publication boundary, the `200 passed` proof bundle, preserved compatibility invariants, and deferred portfolio/helper cleanup debt.
- Preserved migrated publish-handler behavior:
  - Coverage: `tests/unit/test_stdlib_and_extensions.py`, `tests/runtime/test_workflow_portfolio_to_operating_system.py`, `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`, `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - Checks: typed artifact seams, publish-time validation behavior, and docs-baseline invariants still pass together.

## Edge Cases And Failure Paths

- Docs drift:
  - The new docs-baseline assertions fail if the typed-publication preference wording or current-cycle closeout compatibility claims are removed.
- Recursive-memory drift:
  - The new recursive-memory assertions fail if one ledger omits the closeout section, the `200 passed` proof record, or the deferred-debt statement.

## Preserved Invariants Checked

- No CLI behavior change is normalized in tests.
- No `workflow.toml` semantic change is normalized in tests.
- No runtime/provider or `ctx.invoke_workflow(...)` compatibility regression is normalized in tests.

## Flake Risk

- None expected. The suite is deterministic string-presence verification plus existing unit/runtime coverage with no time, network, or ordering dependence.

## Known Gaps

- No new workflow/runtime behavior was introduced in this phase, so no additional workflow test fixtures were necessary beyond the existing targeted proof bundle.

## Validation Run

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/test_architecture_baseline_docs.py`
  - Result: `201 passed`
