# Test Strategy

- Task ID: standalone-implementation-plan-final-autoloop-v3-95d375e8
- Pair: test
- Phase ID: strictness-docs-and-proof
- Phase Directory Key: strictness-docs-and-proof
- Phase Title: Strictness Docs And Proof
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Maintained docs stay on the public authoring surface:
  Covered by `tests/test_architecture_baseline_docs.py::test_active_docs_keep_example_imports_on_public_autoloop_surfaces`, now scanning `docs/*.md`, `Workflow_Instructions.md`, and `cleanup.md` for removed `workflow*`, `workflows.*`, and package-local executable-module import examples.
- Maintained docs and notes keep removed route-contract vocabulary out of the active surface:
  Covered by `test_active_docs_do_not_use_removed_route_contract_terms` and `test_active_working_tree_notes_and_recursive_templates_do_not_use_removed_route_contract_terms`.
- Strictness suite keeps removed workflow compatibility surfaces out of maintained source/docs:
  Covered by `tests/strictness/test_no_compat.py`, including deleted `workflow/` path assertions, forbidden-symbol scan, and deleted-import regex checks.

## Preserved Invariants Checked

- `workflow_package` remains allowed because the strictness/docs guards do not forbid the general `workflow` term.
- `contracts.py` remains allowed as a support/spec filename; only removed `contracts_path*` payload terms stay forbidden.
- The phase keeps relying on deterministic text scans and path existence checks; no timing/network behavior is introduced.

## Edge Cases / Failure Paths

- A future regression that reintroduces `from workflows...`, `import workflows`, `from .flow import`, or `from .workflow import` in `cleanup.md` now fails the docs-baseline suite instead of slipping past the maintained-doc scan.
- A future regression that reintroduces deleted `workflow` package imports or removed compatibility tokens in the maintained tree still fails `tests/strictness/test_no_compat.py`.

## Validation Run

- `.venv/bin/python -m pytest tests/test_architecture_baseline_docs.py`
- `.venv/bin/python -m pytest tests/strictness/test_no_compat.py`

## Known Gaps

- This turn did not rerun the full targeted list or full suite because that proof was already completed and recorded in the implementation phase; this turn only extended the maintained-doc import-surface guard and revalidated the affected proof slice.
