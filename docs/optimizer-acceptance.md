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
| T06 | `test_execution_revision_history_does_not_collapse_a_b_a_to_endpoints`; `test_unavailable_execution_revision_is_sticky`; `test_incomplete_execution_revision_boundaries_are_unknown`; `test_v2_reliability_groups_surfaces_and_ranks_distinct_affected_runs` | Full execution history determines provenance. Unknown/mixed runs remain diagnostic, and only focused observations from one verified revision may support comparisons. |
| T07 | `test_v2_reliability_groups_surfaces_and_ranks_distinct_affected_runs`; `test_reliability_dedupes_run_and_step_across_profile_observations` | Reliability counts each affected run/step once without inventing one cross-run loop or multiplying a failure across profile strata. |
| T08 | `test_optimizer_consumes_real_journaled_typed_outcome_and_usage`; `test_client_inspection_links_nested_and_parallel_scopes_to_exact_parent_operations` | Observed scopes and exact parentage prevent cross-branch lineage invention. |
| T09 | `test_v2_objective_eligibility_keeps_missing_usage_distinct_from_zero`; `test_unknown_profile_with_complete_usage_ranks_but_unknown_usage_measures_first`; `test_latency_uses_physical_dispatch_seconds_not_generic_activity_duration`; provider repair/retry budget tests | Complete, partial, unknown, zero, repair, and retry dispatch evidence remain distinct; objective eligibility requires complete per-dispatch facts and latency never falls back to generic operation duration. |
| T10 | provenance tests plus `test_mixed_profile_retry_keeps_strata_and_ranks_literal_step_total`; `test_full_policy_hash_is_audit_only_for_semantic_profile`; `test_effort_known_unset_and_absent_do_not_share_a_profile`; `test_unknown_profiles_are_distinct_when_dispatch_ids_repeat_across_runs` | Exact source groups remain unchanged; provider/model/effort strata stay visible; full policy hashes remain audit-only; each incomplete profile identity is noncomparable and distinct. |
| T11 | `test_optimizer_ranks_only_observed_operations_and_preserves_evidence`; `test_source_manifest_marks_unvisited_dynamic_paths_without_scoring_them` | Filters and denominators use observed operations; source is not execution proof. |
| T12 | objective eligibility/ranking tests in `tests/test_optimizer.py`; `test_top_k_is_one_global_cap_over_unique_steps_not_profile_strata` | Reliability, token, and additive provider-dispatch-second ranking are reconstructible with one literal-burden shortlist cap and no per-profile allocation. |
| T13 | `test_candidate_validation_rejects_fabricated_evidence`; `test_v2_evidence_and_candidate_bytes_are_bounded_and_identities_are_verified`; strict handoff tests | Invented citations, identities, deterministic facts, and unsupported kinds are rejected. |
| T14 | `test_improvement_without_eligible_evidence_uses_zero_provider_turns`; `test_rejected_proposal_never_edits_a_candidate`; `test_independent_review_can_reject_a_candidate_that_passes_checks` | No evidence means zero provider calls; eligible evidence produces a proposal and fresh independent reviews before editing or accepting a candidate. |
| T15 | all `tests/test_budgets.py` cases | Repairs and manual retries consume turns; children/parallel branches share atomic limits; resume preserves the non-extending deadline. |
| T16 | execution-isolation T16 tests; `tests/test_processes.py` | File/tree/log bounds and timeout/cancellation terminate owned descendants on supported platforms. |
| T17 | paired protocol-failure, frozen-evaluator, invalid-result, and paired-resume tests | Invalid identity, case coverage, metrics, output, or frozen bytes cannot produce improvement. |
| T18 | paired comparison, stochastic-scope, noncomparable-environment, and per-arm budget tests | Improvement/regression/tie/guardrail states use one symmetric frozen plan and never auto-promote. |
| T19 | `test_t19_cleanup_refuses_unowned_overlapping_and_wrong_marker_paths`; `test_publication_rejects_symlinked_generation_root_before_writes`; publication generation failure tests; callable/eval-manifest validation tests | Unsafe ownership paths, interrupted publication, and invalid eval input leave unrelated or prior accepted data untouched. |
| T20 | `test_eval_selection_requires_complete_receipt_identity`; `test_handoff_and_eval_suite_identities_are_exact`; `test_strict_optimizer_receipt_routes_candidate_kind` | Evaluation-case consumers require complete receipt identity, preserve exact handoff identities, and route strict receipts by candidate kind. Packaged-import smoke remains a release gate. |

Focused helper tests are insufficient by themselves. Final verification must
also exercise the default optimizer workflow, strict receipt loading through
`load_optimization_candidate(...)`, both downstream handoffs, isolated real
subprocesses, resume behavior, and packaged imports. A passing contract proves
integrity and bounded behavior; it does not prove that a recommendation improves
an unseen workload. Recommendation receipts therefore remain
`improvement = not_evaluated` unless the optional evaluator completes a valid
paired comparison.
