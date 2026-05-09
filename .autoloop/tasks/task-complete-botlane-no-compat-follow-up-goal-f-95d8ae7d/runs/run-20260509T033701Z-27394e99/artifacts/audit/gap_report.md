# Original intent considered

- Close the repo-root artifact-tree scan loophole in `tests/strictness/test_no_compat.py`.
- Enforce an explicit exact-path policy for maintained recursive-memory files and the active current-run artifact tree.
- Remove remaining legacy-name literals from maintained active artifact files.
- Keep historical allowances narrow and explicit.
- Leave the final codebase with scoped strictness validation and full-suite validation green.

# Clarifications / superseding decisions

- The plan and implementation decisions narrowed the recursive-memory contract to six maintained top-level files plus exact operational-record exceptions.
- The active current-run policy was also narrowed to an exact file inventory rather than any `.autoloop/**`-style prefix exclusion.
- No later clarification authorized omitting end-of-run audit artifacts from the active current-run inventory, and no later decision relaxed the requirement that the final strictness validation remain green.

# Implemented behavior

- `tests/strictness/test_no_compat.py` now contains a dedicated repo-root artifact-policy walker, explicit inventory assertions, and direct legacy-token regression coverage.
- Maintained recursive-memory files were rewritten to current Botlane vocabulary, including the charter, gap ledger, roadmap, and rerun helper.
- The final strictness contract for the active current run is encoded through `ACTIVE_CURRENT_RUN_REQUIRED_CLEAN_RELATIVE_PATHS` and `ACTIVE_CURRENT_RUN_EXCEPTION_RELATIVE_PATHS`.
- Earlier phase artifacts recorded scoped validation and full-suite validation as passing before the final audit artifacts were written.

# Unresolved gaps

- Material gap: the encoded active current-run inventory is still incomplete in the final audited state.
  The live drift set is six files, not five:
  - `artifacts/audit/audit_result.json`
  - `artifacts/audit/criteria.md`
  - `artifacts/audit/feedback.md`
  - `artifacts/audit/gap_report.md`
  - `artifacts/audit/revised_request.md`
  - `sessions/audit.json`
- Evidence: live inventory comparison against `ACTIVE_CURRENT_RUN_REQUIRED_CLEAN_PATHS | ACTIVE_CURRENT_RUN_EXACT_EXCEPTION_PATHS` shows those six extra files and no missing expected files.
- Evidence: `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q` now fails with `2 failed, 70 passed`, not a single inventory failure.
- The first live failure is `test_active_repo_root_artifact_policy_inventories_are_explicit`, caused by the six-file inventory drift above.
- The second live failure is `test_active_repo_root_artifact_files_do_not_emit_removed_legacy_branding_outside_exact_operational_exceptions`, and its current failure set contains `artifacts/audit/audit_result.json`.
- `artifacts/audit/audit_result.json` cannot realistically be a required-clean file under the current schema because its mandatory `revised_request_path` field stores an absolute run-local path under `.autoloop/...`.
- `sessions/audit.json` is plain session metadata and does not itself carry legacy branding in the current state, so it looks like a required-clean inventory file rather than a necessary branding exception.
- Consequence: the final audited state does not satisfy the requested validation contract, and the full suite cannot be treated as green until the active current-run policy covers these end-of-run files correctly.

# Differences justified by later clarification or analysis

- Leaving bootstrap seed, recovery state, lock state, and archived recursive task prompts as exact operational exceptions remains consistent with the recorded decisions and does not silently remove requested behavior.
- Keeping the maintained product-root scan tuples unchanged while adding a separate repo-root artifact-policy walker also remains consistent with the request, because the loophole was closed through explicit additive coverage rather than by broadening the maintained-root tuples.

# Recommended next run

- Update the active current-run policy in `tests/strictness/test_no_compat.py` so the final run-local inventory includes all six currently unmodeled files:
  - the five `artifacts/audit/*` outputs
  - `sessions/audit.json`
- Classify those files explicitly instead of using any broader prefix rule:
  - `sessions/audit.json` should likely be added to the required-clean set.
  - `artifacts/audit/audit_result.json` should likely become an exact per-file exception unless its schema changes, because the required absolute path field currently emits legacy branding.
  - The remaining audit markdown files should be classified according to their final live contents, with required-clean preferred when feasible.
- Re-run `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q` after the audit inventory and exception policy are updated.
- Re-run the literal legacy-name scan over the maintained tree plus the final active artifact contract.
- Re-run `./.venv/bin/python -m pytest` only after the scoped strictness slice is green again.
