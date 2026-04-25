# Recursive Architecture Improvement Cycle 1 Plan

## Cycle Mode

- `consolidate`
- Rationale: the strongest remaining leverage is still inside the existing selected-workflow/evaluation helper family. `stdlib/evaluation.py` reimplements generic validation and selected-workflow snapshot checks that the repo already standardized in `stdlib/validation.py`, so a consolidation pass reduces authoring noise without adding workflow surface area.

## Pre-Change Audit

- Three most relevant existing workflows/helpers:
  - `stdlib/validation.py`: authoritative generic validation seam for JSON object reads, text/list normalization, snapshot alignment, and model-file validation.
  - `stdlib/evaluation.py`: current outlier helper that still carries private `_require_*` and `_read_json(...)` mechanics while validating eval manifests.
  - `workflows/workflow_to_eval_suite/workflow.py`: primary consumer of the eval helper and the workflow whose publish path depends on the validated manifest contract.
- Repeated patterns identified:
  - `stdlib/evaluation.py` still defines local `_require_mapping`, `_require_string_list`, `_require_text`, and `_read_json`.
  - `stdlib/evaluation.py` manually checks `selected_workflow_name` / nested `workflow_name` alignment instead of using `validate_selected_workflow_capability_snapshot(...)`.
  - The eval helper mixes generic JSON-shape validation with eval-specific case policy, making the helper harder to read than the rest of the selected-workflow family.
- Simplification opportunity:
  - Reduce `write_validated_eval_case_manifest(...)` to a thin wrapper over the shared validation seam plus eval-specific policy.
- Is a new workflow necessary?
  - No. This is an internal helper consolidation inside an already-shipped workflow family, and the new-workflow gate stays closed.
- What would make this family 10x easier to author/read/reason about?
  - Future selected-workflow helpers should read as `load authoritative snapshot -> run shared mechanical validation -> apply local policy -> write artifact`, without reintroducing raw JSON plumbing in each helper.
- Cycle decision:
  - Change and consolidate existing helper code. Do not add, merge, split, or retire workflow packages in this cycle.

## Candidate Options Considered

1. Converge `stdlib/evaluation.py` on the shared validation seam and existing selected-workflow snapshot validator.
   - Chosen because it removes a real remaining outlier with the smallest regression surface.
2. Extract a shared selected-workflow context-capture helper across adaptation/eval/diagnostic/refinement/decomposition workflows.
   - Deferred because it would touch more workflows at once and risks hiding core flow for less immediate payoff.
3. Add a new assessment/remediation workflow or building block.
   - Rejected because the request explicitly biases toward consolidation and the new-workflow gate does not pass.

## Chosen Improvement

- Refactor `stdlib/evaluation.py` to consume shared validation helpers from `stdlib.validation.py` for JSON object reads, text/list validation, and selected-workflow snapshot alignment.
- Keep eval-specific logic local:
  - case-kind allow-list and ordering
  - expected-artifact membership checks against the selected workflow's declared artifact surface
  - workflow-parameter coercion through the existing runtime loader path
- Prefer not to add a new helper seam if the current shared validation exports are sufficient.
- Preserve existing artifact filenames and payload keys:
  - `selected_workflow_capability.json`
  - `validated_eval_case_manifest.json`
  - `workflow_eval_suite_summary.json`
- Preserve CLI, runtime/provider, workspace, and `ctx.invoke_workflow(...)` behavior.

## Implementation Milestones

1. Helper convergence
   - Update `stdlib/evaluation.py` to import and use the shared validation seam instead of private `_require_*` / `_read_json` helpers.
   - Replace manual selected-workflow name alignment with `validate_selected_workflow_capability_snapshot(...)`.
   - Keep `_workflow_artifact_surface(...)` local unless implementation proves a second consumer exists and the extraction stays mechanical.
2. Proof and compatibility checks
   - Expand `tests/unit/test_stdlib_and_extensions.py` around `write_validated_eval_case_manifest(...)` so payload shape, path safety, parameter coercion, and failure cases remain stable.
   - Run `tests/runtime/test_workflow_to_eval_suite.py` to confirm the consumer workflow still publishes the same artifacts and receipts.
   - If implementation touches `stdlib/validation.py`, also run `tests/unit/test_validation.py` plus the directly affected selected-workflow consumer suites that rely on the same shared validation surface: `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`, `tests/runtime/test_workflow_run_history_to_failure_modes.py`, and `tests/runtime/test_workflow_to_eval_suite.py`.
3. Docs and recursive memory closeout
   - Update `docs/authoring.md` only if the shared-vs-local validation boundary needs a new explicit note for authoring helpers.
   - Update `.autoloop_recursive/framework_evolution_charter.md`, `.autoloop_recursive/framework_roadmap.md`, `.autoloop_recursive/framework_gap_ledger.md`, `.autoloop_recursive/workflow_candidate_ledger.md`, and `.autoloop_recursive/validation_debt_ledger.md` with the audit result, chosen consolidation, and any remaining deferred debt.

## Interfaces And Files Expected To Change

- Likely code:
  - `stdlib/evaluation.py`
  - `stdlib/validation.py` only if one narrowly scoped mechanical helper is unavoidable
- Likely tests:
  - `tests/unit/test_validation.py` if `stdlib/validation.py` changes
  - `tests/unit/test_stdlib_and_extensions.py`
  - `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py` if `stdlib/validation.py` changes
  - `tests/runtime/test_workflow_to_eval_suite.py`
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py` if `stdlib/validation.py` changes
  - `tests/test_architecture_baseline_docs.py` only if docs wording changes
- Likely docs and memory:
  - `docs/authoring.md` if boundary wording changes
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`

## Regression Prevention

- Preserve existing artifact filenames, top-level JSON keys, case ordering, and loader-based parameter coercion.
- Treat error-message drift as acceptable only when the new wording is clearer and the tests are updated intentionally; do not silently weaken validation coverage.
- Avoid expanding the root `workflow` shim or adding runtime-owned evaluation behavior.
- Treat `.autoloop_recursive/framework_evolution_charter.md` as required closeout scope, not optional documentation.
- If `stdlib/validation.py` changes, treat the regression surface as shared and require the broader proof set above before considering the slice safe.
- Keep the seam additive: no `workflow.toml`, CLI, session, provider, or workspace contract changes.

## Compatibility Notes

- No public CLI, runtime, provider, workspace, or composition contract change is planned.
- `ctx.invoke_workflow(...)` compatibility remains unchanged.
- Existing `workflow_to_eval_suite` routes, prompts, and durable artifact contracts remain unchanged.

## Boilerplate And Clarity Budget Target

- Files added: `0` expected
- Files deleted: `0` expected
- Net line change: target flat or negative
- Repeated validation idioms removed: helper-local JSON/text/list/snapshot checks in `stdlib/evaluation.py`
- Repeated prompt sections removed or shortened: `0` expected
- Workflows changed to use shared helpers: `workflow_to_eval_suite` indirectly through its eval helper; direct workflow edits should be avoided unless proof requires them
- New helper functions introduced: `0` preferred, `1` maximum if the current seam is genuinely insufficient
- Old workflow-local validation blocks replaced: none in workflow files; one helper-local validation block family in `stdlib/evaluation.py`
- Core flow readability before/after: eval manifest validation should read as shared mechanical checks plus local eval policy, not raw schema plumbing
- Required memory files updated in implementation: all five standing recursive-memory files, including `framework_evolution_charter.md`

## Deferred Debt After This Slice

- Shared selected-workflow context-capture helpers remain a possible later authoring-surface cleanup, but only if another cycle proves the repetition still obscures flow across multiple workflows.
- Portfolio expansion candidates remain deferred until consolidation and authoring-surface cleanup stop beating them on leverage.
