# Implementation Notes

- Task ID: revised-sdk-implementation-spec-1-scope-implemen-1e1a7513
- Pair: implement
- Phase ID: sdk-acceptance-regression-tests
- Phase Directory Key: sdk-acceptance-regression-tests
- Phase Title: SDK Acceptance Regression Tests
- Scope: phase-local producer artifact

## Files changed
- `tests/unit/test_sdk_facade.py`
- `autoloop/core/artifacts.py`
- `autoloop/sdk.py`
- `decisions.txt`

## Symbols touched
- `_SDKDeclaredWriteContextWorkflow`
- `test_sdk_public_exports_include_revised_sdk_surface`
- `test_sdk_run_retention_collects_declared_writes_with_runtime_param_context`
- `autoloop.core.artifacts._resolve_placeholder`
- `autoloop.sdk._sdk_artifact_context`

## Checklist mapping
- Plan M4 / phase objective: extended `tests/unit/test_sdk_facade.py` with export coverage and runtime-equivalent declared-write retention coverage.
- Plan M3 seam coverage: kept prompt/input placeholder regression coverage green while validating adjacent artifact-template placeholder behavior.
- Phase deliverable: focused SDK-facing regression tests added; no checklist items intentionally deferred in this phase.

## Assumptions
- Local phase scope permits a minimal adjacent fix when a newly added acceptance regression exposes a request-relevant implementation gap.

## Preserved invariants
- SDK retention remains a thin facade over existing runtime execution.
- Artifact-path `ctx.*` restrictions were not widened.
- Existing SDK facade tests and placeholder tests continue to pass unchanged.

## Intended behavior changes
- Bare artifact placeholders `params.*`, `workflow_params.*`, and `request_file` now resolve instead of silently collapsing during runtime artifact rendering.
- Draft SDK result artifact resolution now uses the same runtime-equivalent context surface as retained artifact resolution.

## Known non-changes
- No broad runtime/refactor work outside the SDK-facing placeholder seam.
- No new cleanup semantics, route semantics, or llm/classify retention behavior added in this phase.

## Expected side effects
- SDK workflows that declare artifact paths from `params.*` or `workflow_params.*` now retain artifacts at the authored destinations instead of malformed empty-segment paths.

## Validation performed
- `.venv/bin/python -m pytest -q tests/unit/test_sdk_facade.py`
- `.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py -k 'artifact_template or render_runtime_template or workflow_params'`

## Deduplication / centralization
- Reused the existing runtime-equivalent SDK artifact context for draft `WorkflowResult` artifact resolution instead of maintaining a second partial context surface.
