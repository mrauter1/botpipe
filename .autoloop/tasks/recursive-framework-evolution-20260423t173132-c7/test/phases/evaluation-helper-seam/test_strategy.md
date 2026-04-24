# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c7
- Pair: test
- Phase ID: evaluation-helper-seam
- Phase Directory Key: evaluation-helper-seam
- Phase Title: Evaluation Helper Seam
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- Happy path:
- `write_validated_eval_case_manifest(...)` refreshes the selected-workflow capability snapshot, delegates per-case parameter coercion to the shared loader path, canonicalizes case ordering, and writes `validated_eval_case_manifest.json`.
- Covered by `test_evaluation_helper_validates_eval_cases_via_selected_workflow_snapshot_and_loader_paths`.

- Preserved invariants:
- The helper stays workflow-local (`ctx.workflow_folder` only) and still requires `.json` output paths.
- The helper remains authoring-only and the docs freeze its non-goals instead of normalizing CLI/runtime/workflow-manifest expansion.
- Covered by `test_evaluation_helper_validates_eval_cases_via_selected_workflow_snapshot_and_loader_paths`, `test_authoring_doc_describes_additive_evaluation_helper_boundary`, and `tests/test_architecture_baseline_docs.py`.

- Edge cases:
- Missing or non-array `cases` manifests are rejected.
- Empty `cases` manifests are rejected.
- Duplicate case ids, unsupported case kinds, blank prompts, empty expected-artifact lists, and unknown expected artifacts are rejected.
- Covered by `test_evaluation_helper_rejects_invalid_case_shapes_and_unknown_expected_artifacts` and `test_evaluation_helper_rejects_missing_case_arrays_and_non_mapping_case_parameters`.

- Failure paths:
- Non-mapping `workflow_parameters` are rejected before parameter coercion.
- Unknown workflow parameters still fail through the shared loader error path.
- Covered by `test_evaluation_helper_rejects_missing_case_arrays_and_non_mapping_case_parameters` and `test_evaluation_helper_preserves_shared_loader_failure_for_invalid_case_parameters`.

- Known gaps:
- The helper's defensive branches for malformed `selected_workflow_capability.json` payloads are not force-injected here; they remain low-priority because the phase reuses the existing snapshot helper and the phase scope excludes runtime-owned evaluation execution.

- Flake risk / stabilization:
- No timing, network, or environment-sensitive cases were added.
- All new coverage uses deterministic `tmp_path` fixtures and local monkeypatching only.
