# Gap Report

## Original intent considered

- Close the remaining framework-authoring-flexibility acceptance gaps from `request.md`.
- Restore late-bound runtime payload placeholder rendering for `{item.payload.<path>}` and `{worklist.<name>.current.payload.<path>}`, while keeping missing-path failures placeholder-specific.
- Reconcile the remaining route/artifact contract regressions, including the artifact-ownership diagnostic and the route-order contract.
- Finish the `full_auto` acceptance path for runtime config loading and plain-string compiled prompt specs on the runner prompt-registry path.
- Reconcile the remaining `tests/runtime/test_workspace_and_context.py` fixture regressions around canonical `python_step(ctx)` handlers.
- Re-run the audited regression slice named in the request and reach a green result.

## Clarifications / superseding decisions

- `raw_phase_log.md` contains no later user clarification entries that changed the requested behavior.
- `decisions.txt` made the following scope-defining choices authoritative for this run:
  - preserve the dual-role artifact ownership diagnostic rather than weakening validation
  - treat provider route ordering as contractual: authored step-local routes first, authored global routes next, runtime-control routes last
  - preserve the existing placeholder-specific `WorkflowExecutionError` wording for missing payload paths
  - keep `python_step(ctx)` as the canonical temporary workflow-package handler surface; do not restore legacy `python_step(state, ctx)` compatibility in this follow-up
  - keep the public typed runtime-config schema and precedence unchanged while making the file-backed config path executable without optional PyYAML

## Implemented behavior

- Payload placeholders:
  - `autoloop/core/artifacts.py` now resolves mapping-backed work item envelopes through `_work_item_payload_root(...)`, so `{item.payload.foo}` and `{worklist.gate.current.payload.foo}` render against the nested authored payload object.
  - `tests/contract/test_engine_contracts.py` directly covers the happy path plus separate missing-path failures for both placeholder forms.
- Route and artifact contracts:
  - `autoloop/core/lowering.py::step_available_route_tags(...)` now derives `available_routes` from authored step-local routes, then authored global routes, then runtime-control routes.
  - `docs/authoring.md` documents that stable ordering contract.
  - `tests/contract/test_engine_contracts.py` and `tests/unit/test_validation.py` assert the shipped route-order and artifact-ownership behavior.
- `full_auto` runner/config path:
  - `autoloop/runtime/config.py::_load_narrow_yaml_mapping(...)` accepts the supported nested mapping/scalar config shape without PyYAML and rejects malformed indentation with `ConfigError`.
  - `tests/runtime/test_provider_backends.py` covers the no-PyYAML happy path and the malformed-indentation failure paths.
  - `autoloop/runtime/runner.py::_prompt_registry_roots(...)` already handles plain-string compiled prompt specs, and `tests/unit/test_primitives_and_stores.py` now pins that contract directly.
- Workspace/context fixtures:
  - `tests/runtime/test_workspace_and_context.py` temporary workflow-package sources use canonical `python_step(ctx)` handlers.
  - `tests/runtime/test_workspace_and_context.py::test_temporary_workspace_workflow_packages_keep_ctx_only_python_step_handlers` prevents silent drift back to `python_step(state, ctx)`.
- Validation:
  - Re-ran the exact audited slice from the request.
  - Result: `575 passed, 14 warnings in 5.36s`.

## Unresolved gaps

- None found.
- The final codebase and regression suite satisfy the requested behavior for all four acceptance areas, and the audited slice is green.

## Differences justified by later clarification or analysis

- No `autoloop/runtime/runner.py` code change was needed for the plain-string prompt-spec requirement because the final code already satisfied that behavior; later phases added direct regression coverage instead of forcing an unnecessary implementation diff.
- The fixture-alignment phase was validation-only in final state because the temporary workflow-package fixtures were already on the canonical `python_step(ctx)` surface; this is consistent with the request’s “update those fixtures accordingly” requirement once the current file already matches the accepted contract.
- The no-PyYAML fallback remains intentionally narrow to mappings plus scalar values. That matches `decisions.txt` and does not remove any behavior requested in `request.md`.

## Recommended next run

- No follow-up implementation run is required for this request.
- Optional future work outside this request: clean up the pre-existing Pydantic `schema`-field warnings in `workflows/workflow_run_traces_to_optimization_candidates/contracts.py`.
