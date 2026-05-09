# Test Strategy

- Task ID: task-complete-botlane-no-compat-follow-up-goal-f-95d8ae7d
- Pair: test
- Phase ID: finalize-current-run-artifact-contract
- Phase Directory Key: finalize-current-run-artifact-contract
- Phase Title: Finalize Active Current-Run Artifact Contract
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- Active current-run inventory stays exact and up to date for `run-20260509T041550Z-4b0707de`.
  Coverage: `test_active_repo_root_artifact_policy_inventories_are_explicit`
- Clean-classified current-run files are walked by the repo-root artifact scanner even though they live outside the maintained source roots.
  Coverage: `test_active_repo_root_artifact_policy_walks_exact_contract_files_even_without_scan_root_membership`
- Exact exceptions remain narrow and content-driven, while clean files stay subject to branding checks.
  Coverage: `test_active_repo_root_artifact_files_do_not_emit_removed_legacy_branding_outside_exact_operational_exceptions`

## Preserved Invariants Checked

- No broad directory exclusion replaces the explicit exact-path contract.
- `artifacts/audit/audit_result.json` remains the only unavoidable audit JSON exact exception.
- `sessions/phases/finalize-current-run-artifact-contract.json` remains required-clean and scanner-visible.
- The test-phase artifact set remains required-clean and scanner-visible once this pair writes `criteria.md`, `feedback.md`, and `test_strategy.md`.

## Edge Cases

- Post-runtime file creation after an earlier mid-turn snapshot.
- Clean phase-session metadata living under the current-run state tree rather than under maintained source roots.

## Failure Paths

- Inventory drift when a runtime-owned file appears after the initial contract update.
- Misclassifying a clean phase-session file as an exact exception while still satisfying raw inventory equality.
- Omitting the test-phase artifacts from the active current-run inventory after the test pair materializes them.

## Known Gaps

- The contract is intentionally pinned to this active run root and does not generalize future run inventories.
