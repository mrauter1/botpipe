# Test Strategy

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: test
- Phase ID: route-and-artifact-contracts
- Phase Directory Key: route-and-artifact-contracts
- Phase Title: Route And Artifact Core
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 canonical workflow-level artifact identity:
  `tests/unit/test_validation.py::test_validation_accepts_same_identity_workflow_level_artifact_written_by_one_step`,
  `tests/unit/test_validation.py::test_validation_accepts_same_identity_workflow_level_artifact_written_by_multiple_steps`,
  and the adjacent duplicate-artifact conflict assertions cover same-object workflow-level writes, multi-producer provenance, and preserved failure on distinct-object collisions.
- AC-2 rendered/direct outcome parity with optional `reason`:
  `tests/runtime/test_runtime_providers.py::test_parse_outcome_json_accepts_plain_object`,
  `tests/runtime/test_runtime_providers.py::test_parse_outcome_json_accepts_missing_reason_for_authored_routes`,
  `tests/unit/test_provider_boundary_core.py::test_parse_outcome_json_defaults_missing_reason_to_empty_string`,
  `tests/contract/test_engine_contracts.py::test_rendered_provider_matches_direct_reason_optional_behavior_for_explicit_blocked_and_failed_routes`,
  `tests/contract/test_engine_contracts.py::test_provider_invalid_question_retries_and_recovers`,
  `tests/contract/test_engine_contracts.py::test_rendered_provider_invalid_question_retries_and_recovers`,
  `tests/contract/test_engine_contracts.py::test_provider_invalid_question_retry_exhaustion_marks_failure_context`,
  and
  `tests/contract/test_engine_contracts.py::test_rendered_provider_invalid_question_retry_exhaustion_marks_failure_context`
  cover missing-`reason` success, `question` payload rejection, retry-and-recover parity, and retry-exhaustion failure-context parity.
- AC-3 policy-gated `question` visibility with no default `blocked`/`failed`:
  `tests/unit/test_validation.py::test_validation_contract_compiles_routes_expected_output_and_retry_policy`,
  `tests/contract/test_engine_contracts.py::test_provider_question_route_is_illegal_in_full_auto_mode`,
  and
  `tests/contract/test_engine_contracts.py::test_rendered_provider_question_route_is_illegal_in_full_auto_mode`
  cover interactive/full-auto contract differences and illegal-route retry behavior when `question` is hidden.
- AC-4 authored `blocked`/`failed` remain ordinary routes:
  `tests/contract/test_engine_contracts.py::test_explicit_blocked_and_failed_routes_do_not_require_reason_field`,
  `tests/contract/test_engine_contracts.py::test_rendered_provider_matches_direct_reason_optional_behavior_for_explicit_blocked_and_failed_routes`,
  and
  `tests/unit/test_validation.py::test_authored_blocked_and_failed_routes_use_generic_fallback_summaries`
  cover direct/rendered no-`reason` success plus generic authored-route summaries instead of reserved-control wording.
- AC-5 explicit child-workflow route mapping preserved:
  the existing child-workflow route mapping coverage in `tests/contract/test_engine_contracts.py` remains the regression surface for explicit `failed`/`blocked` declarations and policy-allowed `question` propagation; this phase relies on those preserved assertions because the implementation did not change the child-step topology surface itself.

## Preserved invariants checked

- Workflow-level artifacts written by steps still resolve under one canonical public identity rather than rebinding to `step_name.artifact_name`.
- Rendered-provider invalid `question` payloads use `invalid_payload` retry semantics instead of falling back to malformed-provider-output classification.
- Full-auto mode still treats provider-emitted `question` as illegal while authored `blocked` and `failed` remain legal only when declared.

## Edge cases and failure paths

- Same-object workflow-level artifacts written by multiple steps.
- Distinct artifact objects that collide on workflow/public name.
- Rendered `{"tag":"question"}` retry-and-recover and retry-exhaustion flows.
- Direct and rendered `blocked`/`failed` outcomes without `reason`.

## Flake-risk assessment

- No timing, network, or nondeterministic ordering dependencies were added.
- The new contract test uses the existing in-memory rendered transport stub and checkpoint store, so retries and failure-state inspection remain deterministic.

## Known gaps

- This phase did not rerun the full repository suite; verification stayed on the request-relevant provider, contract, and validation slices.
- Child-workflow mapping coverage was preserved rather than expanded because the reviewer-identified regression was isolated to rendered-provider invalid-payload classification.
