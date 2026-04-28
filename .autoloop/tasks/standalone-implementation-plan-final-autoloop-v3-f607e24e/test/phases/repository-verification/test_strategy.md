# Test Strategy

- Task ID: standalone-implementation-plan-final-autoloop-v3-f607e24e
- Pair: test
- Phase ID: repository-verification
- Phase Directory Key: repository-verification
- Phase Title: Repository Verification
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Verification sequencing:
  - Focused suites must run before full `pytest`.
  - Coverage source: implementer phase notes for the recorded command order and outcomes.
- Retry-aware event validation invariants:
  - Focused coverage comes from `tests/contract/test_engine_contracts.py` and `tests/unit/test_provider_retries.py`.
  - Preserved checks: provider-attributable invalid events retry, deterministic invalid events hard-fail, retry exhaustion retains failure context.
- Simple-surface lowering and workflow-step cleanup:
  - Focused coverage comes from `tests/unit/test_simple_surface.py`.
  - Preserved checks: simple workflow lowering remains direct, no generated handler regression.
- Stdlib route-info rename and payload cleanup:
  - Focused coverage comes from `tests/unit/test_stdlib_and_extensions.py`, `tests/runtime/test_package_cli.py`, and `tests/runtime/test_compatibility_runtime.py`.
  - Preserved checks: route-info exports remain current, removed payload fields stay removed, capability/runtime surfaces still serialize correctly.
- Strictness and docs:
  - Focused coverage comes from `tests/strictness/test_no_compat.py` and `tests/test_architecture_baseline_docs.py`.
  - Preserved checks: forbidden compatibility vocabulary stays absent from maintained roots, public docs/examples stay aligned with the greenfield surface.

## Edge cases and failure paths covered

- Environment fallback:
  - `pytest` is not on `PATH`, so verification uses `.venv/bin/python -m pytest`.
  - Stabilization: use the repository virtualenv explicitly instead of relying on shell-global tooling.
- No repo-standard lint/type command:
  - `pyproject.toml` does not declare a lightweight lint/type command for this package surface.
  - Coverage approach: test-led verification only; do not invent extra infrastructure in this phase.
- Residual warnings:
  - Full `pytest` emits repeated existing Pydantic `UserWarning` entries for `schema` field names in user workflow `contracts.py` models.
  - Guardrail: warnings are documented but not normalized into failures or hidden rollback pressure.

## Preserved invariants checked

- Deprecated surfaces remain removed after focused and full verification.
- Targeted suites cover the edited surfaces before the full suite runs.
- Any caller breakage would be fixed without restoring removed compatibility fields or exports.

## Known gaps

- No new repository test files or fixtures were added in this phase because the acceptance criteria are satisfied by executing and recording the existing focused suites plus the full suite.
