# Test Strategy

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: branch-typed-evidence
- Phase Directory Key: branch-typed-evidence
- Phase Title: Branch Typed Evidence
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 internal branch runtime authority is typed:
  Covered by `tests/contract/test_branch_result_runtime.py::test_run_branches_returns_typed_branch_results_and_fail_fast_skips_unscheduled`
  Covered by `tests/unit/test_branch_group_context_sessions.py::test_rework_route_branch_result_preserves_branch_step_state`
  Covered by `tests/unit/test_branch_group_context_sessions.py::test_failed_branch_result_reads_provider_session_snapshot_once`

- AC-2 serialization is limited to canonical branch serializers:
  Covered by `tests/contract/test_branch_result_serialization.py::test_branch_result_to_manifest_dict_matches_current_completed_shape`
  Covered by `tests/contract/test_branch_result_serialization.py::test_branch_result_to_manifest_dict_matches_current_skipped_shape`
  Covered by `tests/contract/test_branch_result_serialization.py::test_branch_result_to_manifest_dict_matches_current_cancelled_shape`
  Covered by `tests/contract/test_branch_result_runtime.py::test_typed_branch_manifest_drives_rendering_and_outcome_without_shape_changes`

- Typed manifest drives built-in render/outcome behavior:
  Covered by `tests/contract/test_branch_result_runtime.py::test_typed_branch_manifest_drives_rendering_and_outcome_without_shape_changes`
  Covered by `tests/contract/test_branch_result_serialization.py::test_branch_manifest_schema_context_and_outcome_remain_stable`

- Preserved custom-outcome callback boundary stays mapping-shaped:
  Covered by `tests/contract/test_branch_result_serialization.py::test_branch_manifest_custom_outcome_still_receives_mapping_payload_when_manifest_is_typed`

- Preserved public fan-in metadata boundary stays public-neutral:
  Covered by `tests/contract/test_branch_group_runtime.py::test_parallel_branch_group_with_fan_in_routes_through_fan_in_and_exposes_helpers`
  Explicit assertions: `ctx.fan_in.results` is `NamespaceProxy`, schema stays `botlane.branch_results/v1`, and branch entries remain dict payloads.

## Happy paths

- Typed branch results aggregate into a typed `BranchManifest`.
- Provider-backed fan-in execution still reads branch evidence files and fan-in metadata.
- Rendered branch context and mechanical outcomes still match the stable manifest semantics.

## Edge cases

- `fail_fast` leaves unscheduled branches as typed `skipped` results.
- `needs_input` branches still surface questions/reasons in typed manifest and rendered context.
- Scoped branch step rejection remains defensive and explicit.

## Failure paths

- Failed branch helper still snapshots provider sessions once and returns typed `BranchResult`.
- Cancelled/skipped manifest shapes remain stable through `to_manifest_dict()`.
- Custom outcome callbacks still receive mapping payloads, guarding against accidental internal-type leaks.

## Preserved invariants checked

- Persisted schema remains `botlane.branch_results/v1`.
- `results.json` and `context.md` contract shape remain unchanged.
- Public fan-in payloads do not expose `BranchManifest` or `BranchResult`.

## Flake risk and stabilization

- Concurrency coverage uses deterministic fake providers and fixed branch ordering assertions already present in contract tests.
- The focused suite avoids network and wall-clock assertions beyond stable, bounded branch-duration fields already normalized in existing tests.

## Known gaps

- This phase-focused suite does not run full repo `pytest`.
- No dedicated Python fan-in step asserts `ctx.fan_in.results` directly outside provider request context; the contract test covers the same public surface through the provider-execution path where the regression was observed.
