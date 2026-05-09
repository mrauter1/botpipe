# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: freeze-public-compatibility
- Phase Directory Key: freeze-public-compatibility
- Phase Title: Freeze Public Compatibility
- Scope: phase-local producer artifact

## Files changed

- `tests/unit/test_simple_surface.py`
- `tests/unit/test_sdk_facade.py`
- `tests/strictness/test_no_compat.py`

## Symbols touched

- `botlane.core.__all__`
- `botlane.core.branch_groups.__all__`
- `botlane.core.context.ChildWorkflowResult`
- `botlane.sdk.SDKDebugInfo`
- `botlane.sdk.RetentionInfo`
- `botlane.sdk.CleanupResult`
- `botlane.sdk.WorkflowResult`
- `botlane.sdk.InputRequest`
- `botlane.sdk.HandledInput`
- `botlane.sdk.StepResult`
- `botlane.sdk.SDK_TASK_SENTINEL_FILENAME`
- `tests.strictness.test_no_compat.EXPLICIT_HISTORY_FILE_ALLOWLIST`
- `tests.strictness.test_no_compat.OPTIONAL_SCAN_FILES`

## Checklist mapping

- Phase 0 / public-surface freeze: added exact snapshots for `botlane.core.__all__` and `botlane.core.branch_groups.__all__`.
- Phase 0 / dataclass compatibility: added positional-construction regression coverage for `ChildWorkflowResult` and the public SDK result dataclasses.
- Phase 0 / persistence identity: added canonical `.botlane/tasks/.../.botlane-sdk-task.json` identity assertions.
- Phase 0 / validated baseline: reconciled strictness doc-inventory expectations with the repo state so the required `test_no_compat` bucket passes.

## Assumptions

- Current repo-local doc inventory is part of the phase baseline because `tests/strictness/test_no_compat.py` is a required freeze bucket.

## Preserved invariants

- No runtime or SDK production code changed.
- Public root exports and runtime behavior remain untouched.
- Unsupported `client.step(...)` and branch-group constraints remain enforced by existing coverage.

## Intended behavior changes

- None.

## Known non-changes

- Did not absorb unrelated dirty documentation files into this phase.

## Expected side effects

- Later internal refactors now have direct regression checks for internal module export drift and positional dataclass compatibility.

## Validation performed

- Passed: `.venv/bin/python -m pytest tests/unit/test_simple_surface.py`
- Passed: `.venv/bin/python -m pytest tests/unit/test_sdk_facade.py`
- Passed: `.venv/bin/python -m pytest tests/unit/stdlib/test_composition_helpers.py`
- Passed: `.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q`

## Dedup / centralization notes

- Kept the freeze additions inside existing public-surface suites instead of creating new phase-only test files.
- Adjusted the strictness suite's existing allowlists instead of adding new one-off exclusions or file-system shims.
