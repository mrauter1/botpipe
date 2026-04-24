# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c7
- Pair: implement
- Phase ID: evaluation-helper-seam
- Phase Directory Key: evaluation-helper-seam
- Phase Title: Evaluation Helper Seam
- Scope: phase-local producer artifact

## Files Changed

- `stdlib/evaluation.py`
- `stdlib/__init__.py`
- `docs/authoring.md`
- `tests/unit/test_stdlib_and_extensions.py`

## Symbols Touched

- `write_validated_eval_case_manifest(...)`
- `stdlib.__all__`
- authoring-only evaluation helper documentation
- unit coverage for evaluation-helper validation and boundary docs

## Checklist Mapping

- Phase 1 / add `stdlib/evaluation.py` and exports: complete
- Phase 1 / implement `write_validated_eval_case_manifest(...)` on top of shared loader and selected-workflow surfaces: complete
- Phase 1 / document the seam in `docs/authoring.md`: complete
- Phase 1 / extend unit coverage in `tests/unit/test_stdlib_and_extensions.py`: complete
- Phase 1 / no CLI, runtime, or manifest contract changes: preserved

## Assumptions

- Proposed eval-case manifests are workflow-local JSON objects with a top-level `cases` array.
- Each case uses `case_id`, `case_kind`, `prompt`, `expected_artifacts`, and optional `workflow_parameters`.

## Preserved Invariants

- The helper writes only under `ctx.workflow_folder`.
- Selected-workflow inspection still flows through `write_selected_workflow_capability_snapshot(...)`.
- Per-case workflow-parameter validation still flows through `coerce_workflow_parameter_mapping(...)`.
- No CLI flags, runtime-owned routing/execution, or `workflow.toml` semantics changed.

## Intended Behavior Changes

- Added an authoring-only helper that validates and canonicalizes workflow-local eval-case manifests against one selected workflow.
- The validated manifest now publishes deterministic `case_ids`, `case_kinds`, and `validated_cases` metadata, and normalizes per-case workflow parameter defaults through the shared loader path.

## Known Non-Changes

- No runtime-owned evaluation execution.
- No selected-workflow route validation beyond expected-artifact surface checks.
- No workflow package, runtime test, or recursive-memory changes in this phase-local implementation.

## Expected Side Effects

- Validation refreshes `selected_workflow_capability.json` under the workflow workspace before writing `validated_eval_case_manifest.json`.
- Unknown expected artifacts and invalid per-case workflow parameters now fail early through the helper instead of being deferred to workflow-local ad hoc validation.

## Validation Performed

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`

## Deduplication / Centralization Decisions

- Reused the existing selected-workflow snapshot helper instead of adding eval-specific workflow inspection logic.
- Reused the shared loader coercion function instead of adding eval-specific parameter validation code.
