# Implementation Notes

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: implement
- Phase ID: regression-cleanup
- Phase Directory Key: regression-cleanup
- Phase Title: Regression Cleanup And Validation
- Scope: phase-local producer artifact

## Files Changed

- `autoloop/sdk.py`
- `tests/unit/test_policy.py`
- `tests/unit/test_sdk_facade.py`
- `.autoloop/tasks/final-standalone-implementation-spec-shared-inhe-c4aa316d/runs/run-20260508T141115Z-6c430e1a/decisions.txt`

## Symbols Touched

- `autoloop.sdk.Autoloop.run`
- `autoloop.sdk.Autoloop.llm`
- `autoloop.sdk.Autoloop.classify`
- `autoloop.sdk.Autoloop.step`
- `autoloop.sdk.Autoloop.prompt_step`
- `autoloop.sdk.Autoloop.produce_verify_step`
- `autoloop.sdk.Autoloop.python_step`
- `autoloop.sdk.Autoloop.workflow_step`
- `tests.unit.test_policy.test_policy_docstring_describes_sparse_inheriting_public_contract`
- `tests.unit.test_sdk_facade.test_sdk_public_docstrings_encode_workspace_policy_and_runtime_behavior_contract`

## Checklist Mapping

- Plan milestone 4 / AC-1: kept the focused policy/simple/SDK/runtime suites aligned with the greenfield contract and reran the required targeted test list.
- Plan milestone 4 / AC-2: tightened SDK public docstrings so `workspace`, `Policy`, `prompt`, `message`, `provider_questions`, and `control_routes` are described consistently; added unit tests that pin those docstrings.
- Plan milestone 4 / AC-3: validated the required targeted suites after the docstring/test updates and recorded the results below.

## Assumptions

- Prior phases had already completed the functional API and resolver changes; this phase only needed regression cleanup plus docstring/public-surface hardening.

## Preserved Invariants

- No public compatibility was reintroduced for `root=`, `typed_input=`, `parameters=`, or public `PolicyOverride`.
- No provider emitters, runtime config syntax, strict-policy semantics, or core provider-policy schema definitions were changed.
- Runtime merge-order behavior and workspace-vs-state-root semantics remained unchanged; this phase only documented and pinned them more explicitly.

## Intended Behavior Changes

- None at runtime. The only user-visible change is clearer SDK docstrings for the already-implemented public contract.

## Known Non-Changes

- No CLI/config documentation migration was attempted.
- No additional runtime or compiler logic changes were made.

## Expected Side Effects

- Future regressions that blur `prompt` vs `message` or `provider_questions` vs `control_routes` should now fail focused unit tests instead of silently drifting.

## Deduplication / Centralization Decisions

- Reused existing public docstrings on the canonical SDK methods rather than adding parallel documentation surfaces elsewhere.
- Pinned the contract with focused unit tests instead of duplicating narrative examples in unrelated test modules.

## Validation Performed

- `.venv/bin/pytest tests/unit/test_policy.py tests/unit/test_sdk_facade.py tests/runtime/test_sdk_policy.py tests/unit/test_simple_surface.py -q`
- `.venv/bin/pytest tests/unit/test_provider_policy.py tests/runtime/test_provider_policy_steps.py tests/runtime/test_provider_policy_emitters.py tests/runtime/test_provider_policy_config.py tests/unit/test_simple_surface.py tests/unit/test_sdk_facade.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py -q`

## Validation Results

- Focused rerun after edits: `155 passed`
- Required targeted suites: `212 passed`
