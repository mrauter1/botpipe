Task: Finish the final active current-run inventory and exception contract for repo-root artifact strictness

Goal
Make the final end-of-run strictness contract hold after all audit artifacts exist. The maintained recursive-memory cleanup and additive repo-root artifact-policy walker are already in place; the remaining gap is that the active current-run policy encoded in `tests/strictness/test_no_compat.py` does not yet model the final audit-stage files correctly.

Scope

- `tests/strictness/test_no_compat.py`
- the active current-run audit outputs under `artifacts/audit/`
- the active current-run session record `sessions/audit.json`

Required changes

1. Extend the active current-run exact inventory so it includes all six currently unmodeled files:
   - `artifacts/audit/audit_result.json`
   - `artifacts/audit/criteria.md`
   - `artifacts/audit/feedback.md`
   - `artifacts/audit/gap_report.md`
   - `artifacts/audit/revised_request.md`
   - `sessions/audit.json`

2. Fix both currently failing strictness conditions for the final run state:
   - `test_active_repo_root_artifact_policy_inventories_are_explicit`
   - `test_active_repo_root_artifact_files_do_not_emit_removed_legacy_branding_outside_exact_operational_exceptions`

3. Classify the six files explicitly in the strictness policy:
   - Preferred: keep files in the required-clean set when their live contents can remain free of legacy-name literals.
   - `sessions/audit.json` should likely be a required-clean file under the current contents.
   - `artifacts/audit/audit_result.json` is likely an exact per-file exception under the current schema, because its required `revised_request_path` field stores an absolute run-local path.
   - Use exact per-file exceptions only where operational requirements make required-clean treatment impractical.
   - Do not use any broader prefix exclusion.

4. Keep the final active current-run policy accurate after audit artifacts exist.
   - The inventory assertion must pass after audit outputs and the audit session file are present.
   - The artifact-policy walker and branding checks must reflect the chosen classification for these files.

Validation

- `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q`
- literal legacy-name scan over the maintained tree plus the final active artifact contract
- `./.venv/bin/python -m pytest`

Acceptance criteria

1. `test_active_repo_root_artifact_policy_inventories_are_explicit` passes in the final run state after audit outputs and `sessions/audit.json` exist.
2. `test_active_repo_root_artifact_files_do_not_emit_removed_legacy_branding_outside_exact_operational_exceptions` passes in the final run state.
3. The active current-run inventory no longer omits any of the six end-of-run files listed above.
4. Any file that can remain clean is enforced as clean; any unavoidable operational record remains covered only by an exact per-file exception.
5. The scoped strictness slice and the full suite both pass after the inventory and exception correction.
