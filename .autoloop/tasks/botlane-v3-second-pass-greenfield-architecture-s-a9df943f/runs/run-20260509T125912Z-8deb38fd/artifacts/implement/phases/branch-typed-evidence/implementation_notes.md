# Implementation Notes

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: branch-typed-evidence
- Phase Directory Key: branch-typed-evidence
- Phase Title: Branch Typed Evidence
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/branch_groups/runtime.py`
- `botlane/core/branch_groups/manifest.py`
- `botlane/core/branch_groups/outcomes.py`
- `tests/unit/test_branch_group_context_sessions.py`
- `tests/contract/test_branch_result_runtime.py`
- `tests/contract/test_branch_group_runtime.py`

## Symbols touched

- `BranchGroupRuntime._run_branches`
- `BranchGroupRuntime._execute_branch`
- `BranchGroupRuntime._emit_branch_result_event`
- `BranchGroupRuntime._branch_result_from_step_result`
- `BranchGroupRuntime._failed_branch_result`
- `_cancelled_branch_result`
- `_unexpected_branch_failure_result`
- `_skipped_branch_result`
- `BranchManifest`
- `build_branch_manifest`
- `render_branch_group_context`
- `coerce_branch_manifest`
- `select_branch_group_outcome`

## Checklist mapping

- Phase 4 / AC-1: branch runtime helpers now return and store `BranchResult` internally.
- Phase 4 / AC-2: serialization is limited to `BranchResult.to_manifest_dict()` and `BranchManifest.to_dict()`; runtime rendering/outcome code consumes typed values.
- Plan validation slice: added `tests/contract/test_branch_result_runtime.py` and updated branch helper tests to assert typed return values.

## Assumptions

- Keeping custom branch outcome callbacks on a mapping-shaped manifest payload is still required by existing tests and earlier phase decisions.
- `ctx.fan_in.results` is part of the public fan-in execution surface and must stay public-neutral even while typed `BranchManifest` remains the internal authority.

## Preserved invariants

- Persisted branch evidence schema remains `botlane.branch_results/v1`.
- Persisted `results.json` and `context.md` shapes/content remain compatible with existing contract tests.
- Fail-fast skipped/cancelled semantics are unchanged.
- `ctx.fan_in.results` remains mapping-shaped for user code instead of leaking `BranchManifest`.

## Intended behavior changes

- In-memory branch runtime authority is now typed (`BranchResult` / `BranchManifest`) instead of dict-shaped.

## Known non-changes

- No public branch-group exports changed in this phase.
- No branch evidence JSON schema changes were introduced.
- No broader route/action or provider-turn refactor was pulled into this phase.

## Expected side effects

- Built-in branch outcome aggregation and branch context rendering avoid redundant manifest dict round-trips.
- Fan-in metadata keeps a mapping-shaped results payload at the public context boundary while readable evidence files and typed internal manifest behavior stay unchanged.

## Validation performed

- `.venv/bin/python -m pytest tests/contract/test_branch_result_runtime.py tests/contract/test_branch_result_serialization.py tests/contract/test_branch_group_runtime.py tests/unit/test_branch_group_context_sessions.py -q`
- Result: `43 passed`

## Deduplication / centralization decisions

- Centralized mapping-to-typed coercion in `coerce_branch_manifest(...)` and `_coerce_branch_result(...)` so runtime consumers stop reimplementing manifest parsing.
- Public fan-in results now use the canonical `BranchManifest.to_dict()` serializer instead of a separate ad hoc payload builder.
