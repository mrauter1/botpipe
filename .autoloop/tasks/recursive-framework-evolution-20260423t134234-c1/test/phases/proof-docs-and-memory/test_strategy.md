# Test Strategy

- Task ID: recursive-framework-evolution-20260423t134234-c1
- Pair: test
- Phase ID: proof-docs-and-memory
- Phase Directory Key: proof-docs-and-memory
- Phase Title: Close With Proof And Memory
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Authoring-doc control-contract closeout:
  `tests/test_architecture_baseline_docs.py::test_authoring_doc_freezes_the_root_workflow_import_surface`
  and `::test_authoring_doc_explains_step_control_contract_boundaries`
  lock the public authoring surface for `expected_output_schema`, `available_routes`, `route_contracts`, `Outcome.payload`, `Outcome.tag`, and the `SystemStep` restriction.
- Recursive memory closeout baseline:
  `tests/test_architecture_baseline_docs.py::test_recursive_memory_files_record_cycle_one_closeout_baseline`
  locks the shipped builder, shipped framework improvement, deferred domain workflows, and the documented wrapper/template follow-up seam across `.autoloop_recursive/`.

## Preserved Invariants Checked

- Public architecture/authoring docs remain package-CLI-only and avoid legacy `src/autoloop/` repo-layout guidance.
- The runtime/provider boundary remains documented as narrow and mechanical rather than moving provider-facing SOP into runtime metadata.
- Recursive memory continues to point future cycles at the builder-first baseline and does not silently lose the known package-CLI residual.

## Edge Cases And Failure Paths

- Text-surface regressions where docs mention only `Outcome.payload` but omit `Outcome.tag`, `needs_rework`, `needs_replan`, or the `SystemStep` control-contract restriction.
- Recursive-memory drift where a future edit removes the deferred domain candidates or the documented `require_package_autoloop_cli` / `src/autoloop/...` wrapper-template gap.

## Validation Run

- `.venv/bin/python -m pytest -q tests/test_architecture_baseline_docs.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_workflow_integration_parity.py tests/test_architecture_baseline_docs.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_package_cli.py` -> expected residual failures limited to untouched `recursive_autoloop/` wrapper/template drift already documented in standing memory and implement-phase proof notes

## Known Gaps

- This phase does not fix `recursive_autoloop/run_recursive_autoloop.sh` or the recursive templates; it only locks the documented residual so a future cycle can target that cleanup explicitly.
