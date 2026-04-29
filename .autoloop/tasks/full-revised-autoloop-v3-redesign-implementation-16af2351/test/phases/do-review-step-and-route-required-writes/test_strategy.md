# Test Strategy

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: test
- Phase ID: do-review-step-and-route-required-writes
- Phase Directory Key: do-review-step-and-route-required-writes
- Phase Title: Do review step and route required writes
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- AC-1 canonical `do_review_step` surface and compatibility:
  `tests/unit/test_simple_surface.py`
  Covers canonical `do`/`review`, `review_requires`, `review_writes`, `review_session`, and `review_step`/signature compatibility.
- AC-1 runtime review-session override:
  `tests/contract/test_engine_contracts.py::test_do_review_step_review_session_override_uses_distinct_verifier_session_slot`
  Verifies producer and verifier use separate session slots and persist them independently.
- AC-2 permissive review path without implicit do-write requirement:
  `tests/contract/test_engine_contracts.py::test_do_review_step_sends_split_phase_contracts_without_implicitly_requiring_do_writes`
  Verifies producer/verifier contracts split by phase and verifier does not require the do artifact unless declared.
- AC-2 strict review path when author declares `review_requires`:
  `tests/contract/test_engine_contracts.py::test_do_review_step_review_requires_fail_before_verifier_when_declared`
  Verifies runtime stops before verifier execution when the declared do artifact precondition is missing.
- AC-3 route-specific `required_writes` across do and review artifacts:
  `tests/unit/test_validation.py::test_validation_allows_pair_route_required_outputs_across_do_and_review_artifacts`
  `tests/contract/test_engine_contracts.py::test_do_review_step_validates_selected_route_required_writes_per_route`
  Covers compile-time normalization plus runtime route-by-route enforcement.
- Preserved invariant for explicit empty override:
  `tests/contract/test_engine_contracts.py::test_explicit_empty_required_writes_override_skips_artifact_level_required_defaults`
  Verifies `required_writes=[]` disables artifact-level required defaults only for that route.

## Edge Cases And Failure Paths

- Missing `review_requires` artifact fails after producer and before verifier.
- Rejected routes can require only review-phase artifacts while accepted routes require both phases.
- Explicit empty route requirements remain distinct from unspecified route requirements.

## Reliability Notes

- Tests use `ScriptedLLMProvider`, `InMemorySessionStore`, and temp workspaces only.
- No network, timing, or ordering assumptions are introduced.
- Session assertions key off stable slot names and persisted bindings rather than provider-specific metadata.

## Known Gaps

- Phase-specific lifecycle hooks remain out of scope until the later hook/state phase.
