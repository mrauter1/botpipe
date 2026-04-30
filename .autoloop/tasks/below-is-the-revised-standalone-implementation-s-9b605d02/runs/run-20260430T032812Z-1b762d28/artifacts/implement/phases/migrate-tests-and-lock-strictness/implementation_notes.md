# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: migrate-tests-and-lock-strictness
- Phase Directory Key: migrate-tests-and-lock-strictness
- Phase Title: Migrate Tests And Strictness
- Scope: phase-local producer artifact

## Files changed
- `tests/strictness/test_no_compat.py`

## Symbols touched
- `tests.strictness.test_no_compat.PERSISTED_COMPAT_FIXTURE_EXCLUSIONS`
- `tests.strictness.test_no_compat._iter_active_text_files`
- `tests.strictness.test_no_compat.test_removed_compatibility_scan_scope_covers_maintained_tree_only`

## Checklist mapping
- AC-1: verified
  - Repo scan confirmed maintained validation, engine-contract, runtime/provider, and fixture workflow declarations no longer use `produces`, `review_produces`, or `do_produces`.
- AC-2: completed
  - Removed the leftover `core/_compat.py` scan exclusion.
  - Made persisted-compatibility fixture exclusions explicit and currently empty, so new carve-outs must be intentional.
- AC-3: completed
  - Ran the canonical targeted pytest suite for validation, engine contracts, compatibility runtime, runtime static graph, provider backends, and strictness.

## Assumptions
- Persisted session/checkpoint/run compatibility readers remain the only allowed legacy boundary, and this phase did not need any new fixture-level exceptions for them.
- The explicit `autoloop_v3.core -> core` bridge already satisfied the alias-shim acceptance criterion before this phase started.

## Preserved invariants
- Maintained-tree strictness still scans the same active roots and continues to include the runtime compatibility suite.
- The only default scan exclusion remains the strictness file itself to avoid self-matching.

## Intended behavior changes
- `tests/strictness/test_no_compat.py` now fails if banned vocabulary appears in `core/_compat.py` or any other maintained file unless an explicit persisted-reader fixture is deliberately added to the compatibility exclusion list.

## Known non-changes
- `tests/unit/test_validation.py`, `tests/contract/test_engine_contracts.py`, `tests/runtime/test_compatibility_runtime.py`, and `tests/fixtures/toy_runtime_workflow.py` were analyzed but did not require additional edits because they already use canonical write vocabulary.
- No persisted compatibility payload readers or alias bridge code were changed in this phase.

## Expected side effects
- Future compatibility carve-outs for banned vocabulary now require editing the explicit persisted-fixture exclusion list, which keeps the strictness boundary reviewable.

## Deduplication / centralization
- Kept exclusion policy centralized in `tests/strictness/test_no_compat.py` with a dedicated persisted-fixture exclusion set instead of a broad maintained-file carve-out.

## Validation performed
- `rg -n "\\b(produces\\s*=|review_produces\\b|do_produces\\b|\\.produces\\b)" tests core runtime stdlib workflows autoloop -g '!tests/strictness/test_no_compat.py'`
- `.venv/bin/python -m pytest tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/runtime/test_compatibility_runtime.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_provider_backends.py tests/strictness/test_no_compat.py`
- Result: maintained-tree scan clean outside strictness; `259 passed`
