# Framework Authoring Flexibility Follow-up Plan

## Objective
Close the remaining acceptance gap by running the framework authoring-flexibility regression slice in the repository's normal Python environment, fixing only the failures exposed by that slice, correcting the stale managed-artifact diagnostic text in `autoloop/core/inventory.py`, and recording exact rerun evidence in this run's artifacts.

## Current feasibility facts
- The repository already contains a runnable local environment at `./.venv`.
- Verified in planning: `./.venv/bin/python` is Python `3.12.3`, `./.venv/bin/python -m pytest --version` reports `pytest 9.0.3`, and `pydantic 2.13.3` imports successfully.
- Because the normal environment is already present, implementation should reuse `./.venv` instead of introducing a new toolchain or changing workflow-package plumbing.

## In scope
- Run the requested suites:
  - `tests/contract/test_engine_contracts.py`
  - `tests/unit/test_simple_surface.py`
  - `tests/unit/test_primitives_and_stores.py`
  - `tests/unit/test_validation.py`
- Run the affected runtime/static-graph regression suite for provider-visible route metadata:
  - `tests/runtime/test_runtime_static_graph.py`
- Fix failures revealed by those runs with small local changes only.
- Update the ownership ambiguity diagnostic in `autoloop/core/inventory.py` so its recommendation points to the implemented managed-artifact surface: `Artifact.managed(...)` and `role="managed"`.
- Record the exact commands executed and the observed passing results in run-local artifacts.

## Out of scope
- Broad refactors across compiler/runtime/provider plumbing.
- Workflow-package scaffolding or unrelated developer-workflow changes.
- Expanding the regression slice beyond the listed suites unless a failure proves another directly dependent suite is required to validate the fix.

## Implementation milestones
1. Environment and baseline execution
   - Run the regression slice with the repository interpreter, preferably:
     - `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py tests/runtime/test_runtime_static_graph.py`
   - If that combined command obscures failure isolation, split it into per-file reruns, but keep using `./.venv/bin/python -m pytest -q`.
   - If an import/runtime dependency is unexpectedly missing at execution time, repair only that dependency inside `./.venv`; do not introduce alternate environment managers or workflow-package changes.
2. Minimal repair
   - Constrain edits to the failure surface:
     - likely code: `autoloop/core/inventory.py`, route-metadata compilation/serialization files already exercised by the failing test, or closely related helpers
     - likely tests: only the targeted suites when a message expectation or regression assertion must be updated
   - Preserve current behavior for:
     - compiled `runtime_control_routes`
     - `provider_visible_routes_interactive`
     - `provider_visible_routes_full_auto`
     - normalized `required_writes` / effective required-write payloads
     - artifact ownership detection semantics
   - The inventory diagnostic change is wording-only unless a failing test proves the existing managed-artifact path is not actually recognized.
3. Evidence rerun and artifact recording
   - Re-run the full targeted slice after fixes.
   - Record every executed command and its observed result line (for example, `N passed`) in the implementation-phase artifact for this run; prefer the implementation notes artifact if runtime creates one, otherwise use the phase feedback artifact.
   - Keep the same commands visible in commentary so they are also preserved in `raw_phase_log.md`.

## Interfaces and invariants
- Public authoring contract:
  - Managed artifacts must continue to be represented through the existing public surface (`Artifact.managed(...)` / `role="managed"`).
  - The ambiguity diagnostic should stop implying the feature is future work.
- Provider-visible route metadata contract:
  - Unit/contract/static-graph outputs must stay aligned on route visibility and required-write reporting.
  - `question` remains runtime-controlled and hidden from full-auto provider contracts unless explicitly enabled.
- Compatibility:
  - No persisted data migration or CLI contract change is planned.
  - Any test-only message assertion updates must remain consistent with the existing runtime behavior, not redefine it.

## Validation approach
- Primary acceptance run:
  - `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py tests/runtime/test_runtime_static_graph.py`
- Accept per-file reruns during debugging, but final evidence must include a passing run covering the full targeted slice.
- If a failure shows another route-metadata regression seam is directly impacted, add only that suite to the rerun evidence and explain why in the implementation artifact.

## Risk register
- Hidden environment drift: a dependency may still be missing despite the current `.venv` checks.
  - Mitigation: use the verified repo interpreter first and install only the missing package into that same venv if execution proves it necessary.
- Over-broad regression chasing: failures in large suites could tempt unrelated cleanup.
  - Mitigation: keep edits local to the failing assertion/code path and avoid touching workflow-package or general provider-backend infrastructure unless the targeted slice proves it is required.
- Diagnostic wording regressions: tests may pin the old message text.
  - Mitigation: update only the assertions that intentionally cover the ownership ambiguity recommendation and keep the exception type/trigger conditions unchanged.

## Rollback
- Revert only the narrow repair if it changes route-visibility or required-write semantics beyond the targeted tests.
- If a newly added dependency step destabilizes the repo environment, remove only that dependency change and fall back to the already verified `.venv` baseline.
