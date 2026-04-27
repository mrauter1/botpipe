# Test Strategy

- Task ID: recursive-framework-evolution-20260427t121046-c1
- Pair: test
- Phase ID: optimization-helper-consolidation
- Phase Directory Key: optimization-helper-consolidation
- Phase Title: Consolidate Optimizer Helpers
- Scope: phase-local producer artifact

## Coverage Map

- Behavior: deterministic frame-context capture stays helper-backed while preserving optimizer artifacts and filtered/public vs internal trace handling.
  Coverage:
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py::test_capture_frame_context_excludes_old_runs_missing_plan1_observability`
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py::test_capture_frame_context_normalizes_trace_corpus_from_seeded_runs`
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py::test_capture_frame_context_keeps_public_trace_filtered_but_internal_trace_complete`

- Behavior: optional-pass finalization preserves accepted-route validation and writes deterministic empty payloads only for not-applicable/skip routes.
  Coverage:
  - `tests/unit/test_optimization_helpers.py::test_finalize_optional_optimization_artifact_writes_empty_payload_for_missing_skipped_route`
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py::test_optional_skip_routes_preserve_existing_artifacts_when_present`
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py::test_not_applicable_candidate_handlers_preserve_existing_artifacts`

- Behavior: publication-surface aggregation and scorecard publication validation stay centralized and reject drift between scorecard metadata and validated candidate artifacts.
  Coverage:
  - `tests/unit/test_optimization_helpers.py::test_collect_and_validate_optimization_publication_surface_aggregates_counts_ids_and_ablation`
  - `tests/unit/test_optimization_helpers.py::test_validate_optimization_scorecard_publication_rejects_unknown_high_priority_candidate_ids`
  - `tests/unit/test_optimization_helpers.py::test_validate_optimization_scorecard_publication_rejects_ablation_flag_mismatch`
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py::test_package_rejects_candidate_count_mismatch`
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py::test_package_rejects_malformed_candidate_artifact`

- Behavior: publication still rejects selected-workflow source drift and keeps the no-hidden-execution refinement boundary intact.
  Coverage:
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py::test_publish_optimization_packet_rejects_selected_workflow_source_mutation`
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py::test_workflow_never_mutates_selected_workflow_source`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`

## Preserved Invariants Checked

- Artifact filenames, route tags, and candidate-only publication boundary remain unchanged.
- Skipped optional passes still produce deterministic empty artifacts instead of hidden execution or missing-file publication failures.
- Scorecard publication remains coupled to validated candidate artifacts rather than trusting provider-authored counts or IDs.
- Optimization publication continues to fail on selected-workflow source mutation before any refinement handoff can treat the packet as authoritative.

## Edge Cases And Failure Paths

- Historical runs missing Plan-1 observability are excluded with an explicit report instead of corrupting the corpus.
- Public trace output can be filtered while the internal ranking corpus remains complete enough for upstream ranking.
- Skipped/not-applicable passes preserve already-written artifacts when present, avoiding destructive overwrites.
- Scorecard publication rejects unknown `highest_priority_candidate_ids`, ablation-flag drift, malformed candidate artifacts, and count mismatches.

## Known Gaps

- No new full runtime test was added for the helper-level unknown-priority-id or ablation-flag mismatch branches because those paths are deterministic and fully exercised at the unit-helper seam.
- This phase does not broaden coverage for future optimizer-family adopters of the stdlib seam; that remains follow-on portfolio work.
