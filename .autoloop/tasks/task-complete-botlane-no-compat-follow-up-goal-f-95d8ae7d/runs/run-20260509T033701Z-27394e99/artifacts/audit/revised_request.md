Task: Finish the active current-run inventory contract for the repo-root artifact strictness policy

Goal
Make the final end-of-run strictness contract hold after audit artifacts exist. The maintained recursive-memory cleanup and additive artifact-policy walker are already in place; the remaining gap is that the active current-run inventory encoded in `tests/strictness/test_no_compat.py` omits the audit outputs created later in the run.

Scope

- `tests/strictness/test_no_compat.py`
- the active current-run audit outputs under `artifacts/audit/`

Required changes

1. Extend the active current-run exact inventory so it includes these files:
   - `artifacts/audit/audit_result.json`
   - `artifacts/audit/criteria.md`
   - `artifacts/audit/feedback.md`
   - `artifacts/audit/gap_report.md`
   - `artifacts/audit/revised_request.md`

2. Classify each of those files explicitly in the strictness policy:
   - Preferred: add them to the required-clean set if their contents can remain free of legacy-name literals.
   - `artifacts/audit/audit_result.json` is likely an exact per-file exception under the current schema, because its required `revised_request_path` field stores an absolute run-local path.
   - Only if necessary: add specific files to the exact exception set when they must preserve legacy-name evidence as operational records.
   - Do not use any broader prefix exclusion.

3. Keep the active current-run policy correct for the final run state.
   - The inventory assertion must pass after audit outputs are present.
   - The artifact-policy walker and legacy-branding checks must reflect the chosen classification for the audit files.

Validation

- `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q`
- literal legacy-name scan over the maintained tree plus the final active artifact contract
- `./.venv/bin/python -m pytest`

Acceptance criteria

1. `test_active_repo_root_artifact_policy_inventories_are_explicit` passes in the final run state after audit outputs exist.
2. The active current-run inventory no longer omits `artifacts/audit/*`.
3. Any audit file that can remain clean is enforced as clean; any unavoidable operational record remains covered only by an exact per-file exception.
4. The scoped strictness slice and the full suite both pass after the inventory correction.
