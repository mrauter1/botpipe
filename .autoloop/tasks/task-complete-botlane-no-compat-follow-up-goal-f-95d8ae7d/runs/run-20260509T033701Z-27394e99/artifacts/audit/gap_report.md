# Original intent considered

- Close the repo-root artifact-tree scan loophole in `tests/strictness/test_no_compat.py`.
- Enforce an explicit exact-path policy for maintained recursive-memory files and the active current-run artifact tree.
- Remove remaining legacy-name literals from maintained active artifact files.
- Keep historical allowances narrow and explicit.
- Leave the final codebase with scoped strictness validation and full-suite validation green.

# Clarifications / superseding decisions

- The planning and implementation ledgers narrowed the recursive-memory contract to six maintained top-level files plus exact operational-record exceptions.
- The active current-run policy was also narrowed to an exact file inventory rather than any directory-prefix exclusion.
- No later clarification authorized omitting end-of-run audit outputs from the active current-run inventory, and no later decision relaxed the final validation requirement.

# Implemented behavior

- `tests/strictness/test_no_compat.py` now contains a dedicated repo-root artifact-policy walker, explicit inventory assertions, and direct legacy-token regression coverage.
- Maintained recursive-memory files were rewritten to the current Botlane vocabulary, including the charter, gap ledger, roadmap, and rerun helper.
- The live strictness helper constants encode an exact active current-run contract through `ACTIVE_CURRENT_RUN_REQUIRED_CLEAN_RELATIVE_PATHS` and `ACTIVE_CURRENT_RUN_EXCEPTION_RELATIVE_PATHS`.
- Phase artifacts claim scoped validation and full-suite validation succeeded earlier in the run.

# Unresolved gaps

- Material gap: the encoded active current-run inventory does not include the five audit outputs under `artifacts/audit/`:
  - `artifacts/audit/audit_result.json`
  - `artifacts/audit/criteria.md`
  - `artifacts/audit/feedback.md`
  - `artifacts/audit/gap_report.md`
  - `artifacts/audit/revised_request.md`
- Evidence: live inventory comparison shows those five files in `current_run_inventory - expected`, with no missing expected files.
- Evidence: `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q` now fails at `test_active_repo_root_artifact_policy_inventories_are_explicit` with `1 failed, 71 passed`.
- Evidence: `artifacts/audit/audit_result.json` cannot realistically be a required-clean file under the current schema because its mandatory `revised_request_path` field stores an absolute run-local path.
- Consequence: the final state no longer satisfies the requested validation contract. Because the strictness slice fails, the full suite cannot be considered green in the final audited state.
- Scope impact: this is a narrow follow-up. The maintained recursive-memory cleanup and the additive artifact-policy walker appear to be in place; the remaining defect is that the active current-run policy stopped short of the final run-local audit inventory.

# Differences justified by later clarification or analysis

- Leaving bootstrap seed, recovery state, lock state, and archived recursive task prompts as exact operational exceptions is consistent with the recorded decisions and does not silently remove requested behavior.
- Keeping the maintained product-root scan tuples unchanged while adding a separate repo-root artifact-policy walker is also consistent with the request, because the loophole was closed by explicit additive coverage rather than by broadening the existing maintained-root tuples.

# Recommended next run

- Update the active current-run inventory in `tests/strictness/test_no_compat.py` so the final run-local audit files are part of the explicit contract.
- Classify each audit file deliberately:
  - Prefer `required clean` when the file can remain free of legacy-name literals.
  - Treat `artifacts/audit/audit_result.json` as the likely exact per-file exception unless its schema changes, because the required absolute path field is itself legacy-name-bearing in this repository layout.
  - Use an exact per-file exception only if the file must preserve legacy-name evidence as an operational record.
- Re-run `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q` after the audit files exist.
- Re-run the literal legacy-name scan over the maintained tree plus the final active artifact contract.
- Re-run `./.venv/bin/python -m pytest` only after the strictness slice is green again.
