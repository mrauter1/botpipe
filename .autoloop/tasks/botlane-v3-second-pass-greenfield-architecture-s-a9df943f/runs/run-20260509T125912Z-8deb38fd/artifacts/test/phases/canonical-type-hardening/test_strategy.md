# Test Strategy

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: canonical-type-hardening
- Phase Directory Key: canonical-type-hardening
- Phase Title: Canonical Type Hardening
- Scope: phase-local producer artifact

## Behavior to coverage map

- Typed `BranchManifest` can be passed directly to `select_branch_group_outcome(...)`:
  Covered in `tests/contract/test_branch_result_serialization.py::test_branch_manifest_schema_context_and_outcome_remain_stable`.
- Custom branch outcome aggregators still receive mapping-shaped manifest payloads even when the runtime now builds typed manifests:
  Covered in `tests/contract/test_branch_result_serialization.py::test_branch_manifest_custom_outcome_still_receives_mapping_payload_when_manifest_is_typed`.
- Existing branch runtime still executes through async dispatch and fan-in/mechanical outcome paths with typed-manifest normalization in place:
  Revalidated with `tests/contract/test_async_step_dispatcher.py` and `tests/contract/test_branch_group_runtime.py`.

## Preserved invariants checked

- Branch manifest schema remains `botlane.branch_results/v1`.
- Manifest branch ordering and needs-input question text remain unchanged.
- Custom outcome hooks keep the pre-existing mapping contract.

## Edge cases

- Manifest built from mixed branch inputs (`BranchResult` and serialized branch dicts).
- Typed manifest passed through the built-in `all_settled` outcome path.

## Failure paths

- Regression target from `IMP-001`: typed manifest must not trigger `manifest.get(...)` or `dict(manifest)` crashes inside outcome selection and downstream branch runtime flows.

## Stabilization / flake control

- Tests are deterministic and use fixed in-memory branch results plus synchronous assertion on payload shape; no timing-sensitive assertions were added.

## Known gaps

- This phase does not add strictness tests for later removal of mapping normalization; that belongs to the later typed branch-runtime cutover phase.
