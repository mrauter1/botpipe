# Implementation Notes

- Task ID: standalone-implementation-plan-final-autoloop-v3-95d375e8
- Pair: implement
- Phase ID: strictness-docs-and-proof
- Phase Directory Key: strictness-docs-and-proof
- Phase Title: Strictness Docs And Proof
- Scope: phase-local producer artifact

## Files Changed

- `docs/architecture.md`
- `docs/authoring.md`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop/tasks/standalone-implementation-plan-final-autoloop-v3-95d375e8/decisions.txt`

## Symbols Touched

- `test_active_docs_keep_example_imports_on_public_autoloop_surfaces`
- doc text covering package reuse and child-workflow invocation examples

## Checklist Mapping

- Phase AC-1: preserved existing strictness coverage; verified `tests/strictness/test_no_compat.py` passes against the maintained tree.
- Phase AC-2: removed remaining maintained-doc examples that imported from `workflows.*` or package-local executable modules; added a docs baseline guard for those patterns.
- Phase AC-3: ran the required targeted tests and full `pytest`.

## Assumptions

- `legacy_docs/` and `cleanup3.md` remain out of the maintained-doc scan surface for this phase.

## Preserved Invariants

- No workflow-step execution behavior changed.
- No runtime or loader behavior changed in this phase.
- `workflow_package` terminology remains allowed and unchanged.
- `contracts.py` remains allowed as a support/spec filename surfaced via `spec_paths`.

## Intended Behavior Changes

- Maintained docs no longer show import examples from `workflows.*`, `.flow`, or `.workflow`; public examples stay on `autoloop` / `autoloop.simple`.

## Known Non-Changes

- Did not broaden the strictness scan into `legacy_docs/` or request-planning artifacts.
- Did not modify provider retry logic, runtime surfaces, or workflow-step handling in this phase.

## Validation Performed

- `.venv/bin/python -m pytest tests/test_architecture_baseline_docs.py`
- `.venv/bin/python -m pytest tests/strictness/test_no_compat.py`
- `.venv/bin/python -m pytest tests/unit/test_simple_surface.py`
- `.venv/bin/python -m pytest tests/unit/test_provider_retries.py`
- `.venv/bin/python -m pytest tests/runtime/test_package_cli.py`
- `.venv/bin/python -m pytest tests/runtime/test_workflow_reference_resolution.py`
- `.venv/bin/python -m pytest`

## Expected Side Effects

- Future maintained-doc changes that reintroduce non-public import examples will fail `tests/test_architecture_baseline_docs.py`.

## Deduplication / Centralization Decisions

- Centralized the maintained-doc import-surface guard in `tests/test_architecture_baseline_docs.py` instead of duplicating similar checks across per-doc tests.
