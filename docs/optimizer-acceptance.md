# Optimizer v2 acceptance inventory

This matrix maps the scenarios in
[`requirements/optimizer-v2.md`](requirements/optimizer-v2.md) to native
durable-function regression tests. It records test intent, not the result of a
particular CI run. Release status comes from the final Linux, Windows,
wheel/sdist, and full-suite jobs.

| ID | Native regression tests | Contract exercised |
| --- | --- | --- |
| T01 | `test_invalid_candidate_cannot_hide_behind_imported_original`; `test_imported_original_cannot_hide_invalid_native_candidate` | A pre-imported or installed original cannot satisfy candidate compilation. |
| T02 | `test_native_candidate_uses_staged_behavior_and_package_origins`; `test_installed_selected_workflow_is_captured_and_candidate_overlay_executes` | Flat, `src`, namespace, and installed-package candidates execute from staging while authoritative files remain unchanged. |
| T03 | `test_t03_surface_manifest_rejects_forged_derived_fields`; `test_validation_entrypoint_rejects_forged_surface_id_before_launch` | Roots, change metadata, hashes, counts, and surface IDs are independently derived. |
| T04 | `test_t04_execution_arm_detects_new_file_and_source_anchor_drift`; `test_native_validation_rejects_source_or_snapshot_drift_before_launch`; paired-resume cache tests | Source, snapshot, candidate, evaluator, and saved-result drift fail closed. |
| T05 | `test_v2_evidence_and_candidate_bytes_are_bounded_and_identities_are_verified` | Complete bounded evidence and content IDs are required; no partial parse or invented citation is accepted. |
| T06 | `test_resume_retains_recorded_start_provenance_and_exposes_source_drift`; `test_v2_reliability_groups_surfaces_and_ranks_distinct_affected_runs` | Unknown/mixed provenance stays isolated and current verified surfaces group exactly. |
| T07 | `test_v2_reliability_groups_surfaces_and_ranks_distinct_affected_runs` | Reliability counts distinct affected runs without inventing one cross-run loop. |
| T08 | `test_optimizer_consumes_real_journaled_typed_outcome_and_usage`; `test_client_inspection_links_nested_and_parallel_scopes_to_exact_parent_operations` | Observed scopes and exact parentage prevent cross-branch lineage invention. |
| T09 | `test_v2_objective_eligibility_keeps_missing_usage_distinct_from_zero`; provider repair/retry budget tests | Complete, partial, unknown, zero, repair, and retry dispatch evidence remain distinct. |
| T10 | provenance tests plus `test_v2_reliability_groups_surfaces_and_ranks_distinct_affected_runs` | Exact source identities group; changed or unknown identities do not inherit current metadata. |
| T11 | `test_optimizer_ranks_only_observed_operations_and_preserves_evidence`; `test_source_manifest_marks_unvisited_dynamic_paths_without_scoring_them` | Filters and denominators use observed operations; source is not execution proof. |
| T12 | objective eligibility/ranking tests in `tests/test_optimizer.py` | Reliability, token, and latency ranking are reconstructible with one total shortlist cap. |
| T13 | `test_candidate_validation_rejects_fabricated_evidence`; `test_v2_evidence_and_candidate_bytes_are_bounded_and_identities_are_verified`; strict handoff tests | Invented citations, identities, deterministic facts, and unsupported kinds are rejected. |
| T14 | `test_v2_no_eligible_evidence_uses_zero_provider_turns`; `test_v2_eligible_evidence_uses_one_producer_and_independent_verifier` | No evidence means zero provider calls; normal evidence means one proposal and fresh independent review. |
| T15 | all `tests/test_budgets.py` cases | Repairs and manual retries consume turns; children/parallel branches share atomic limits; resume preserves the non-extending deadline. |
| T16 | execution-isolation T16 tests; `tests/test_processes.py` | File/tree/log bounds and timeout/cancellation terminate owned descendants on supported platforms. |
| T17 | paired protocol-failure, frozen-evaluator, invalid-result, and paired-resume tests | Invalid identity, case coverage, metrics, output, or frozen bytes cannot produce improvement. |
| T18 | paired comparison, stochastic-scope, noncomparable-environment, and per-arm budget tests | Improvement/regression/tie/guardrail states use one symmetric frozen plan and never auto-promote. |
| T19 | `test_t19_cleanup_refuses_unowned_overlapping_and_wrong_marker_paths`; callable/eval-manifest validation tests | Unsafe ownership paths and invalid eval input leave unrelated or prior accepted data untouched. |
| T20 | `test_refinement_requires_one_complete_input_form`; `test_handoff_and_eval_suite_identities_are_exact`; `test_strict_optimizer_receipt_routes_candidate_kind` | Both refinement input forms, evaluation-case routing, and strict receipts stay coherent. Deprecated aliases and packaged-import smoke remain release gates. |

Focused helper tests are insufficient by themselves. Final verification must
also exercise the default optimizer workflow, strict receipt loading through
`load_optimization_candidate(...)`, both downstream handoffs, isolated real
subprocesses, resume behavior, and packaged imports. A passing contract proves
integrity and bounded behavior; it does not prove that a recommendation improves
an unseen workload. Recommendation receipts therefore remain
`improvement = not_evaluated` unless refinement completes a valid paired
comparison.
