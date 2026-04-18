# Test Strategy

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: test
- Phase ID: layered-tests-and-parity-proof
- Phase Directory Key: layered-tests-and-parity-proof
- Phase Title: Prove Strictness, Neutrality, And Parity
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Strict public surface and no-compat guarantees:
  `autoloop_v3/tests/unit/test_primitives_and_stores.py`,
  `autoloop_v3/tests/unit/test_validation.py`,
  `autoloop_v3/tests/strictness/test_no_compat.py`,
  `autoloop_v3/tests/test_architecture_baseline_docs.py`
- Engine contracts and extension lifecycle semantics:
  `autoloop_v3/tests/contract/test_engine_contracts.py`
- Generic runtime neutrality, config compatibility, prompt/session handling:
  `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
- Optional extension opt-in, invisibility, and git/tracing behavior:
  `autoloop_v3/tests/runtime/test_optional_extensions.py`,
  `autoloop_v3/tests/unit/test_stdlib_and_extensions.py`
- Workflow behavior and legacy Autoloop-v1 parity:
  `autoloop_v3/tests/runtime/test_workflow_integration_parity.py`

## Preserved invariants checked
- Runtime stays phase-agnostic and free of Autoloop-v1 topology semantics.
- Removed compat modules and symbols stay absent from canonical workflow/runtime code.
- Loader does not inject symbols and workflows must declare explicit entry points and imports.
- Session payload compatibility for legacy `thread_id` and `superloop.*` config discovery remains intact.
- Workflow-declared extensions remain the only opt-in surface; undeclared workflows stay extension-invisible.

## Edge cases and failure paths
- Missing `SessionPaths(...)` fails before workspace creation in the Autoloop-v1 harness.
- Resume without checkpoint rejects stale persisted session state.
- Duplicate session-path strategies fail before run creation.
- Malformed extension bindings, missing sessions, missing required artifacts, and handler exceptions checkpoint cleanly.
- Git empty-scope handling distinguishes no-op from explicit empty commits.

## Validation run
- `pytest -q autoloop_v3/tests/strictness/test_no_compat.py`
- `pytest -q autoloop_v3/tests`

## Flake risk / stabilization
- Tests use filesystem-local tempdirs, scripted fake providers, and source scans only; no network, clocks, or nondeterministic ordering are required.

## Known gaps
- Repo-wide `pytest -q` verification is tracked by the implement/verifier artifacts for this phase; this strategy focuses on the package-local proof matrix and the added strictness layer.
