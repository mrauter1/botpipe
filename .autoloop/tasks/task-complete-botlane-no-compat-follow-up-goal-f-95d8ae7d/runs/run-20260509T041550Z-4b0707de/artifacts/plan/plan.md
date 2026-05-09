# Final Active Current-Run Artifact Contract Plan

## Objective

Make the final audited run state pass strictness by updating the active current-run contract in `tests/strictness/test_no_compat.py` for `run-20260509T041550Z-4b0707de`, keeping cleanable audit/session files in the required-clean set and limiting exact exceptions to unavoidable operational records.

## Current State

- `tests/strictness/test_no_compat.py` still hard-codes the previous active run root `run-20260509T033701Z-27394e99`.
- The live strictness slice against that prior run fails `2` assertions: the final inventory omits six end-of-run files, and the repo-root artifact branding walk reports `artifacts/audit/audit_result.json` plus `artifacts/audit/gap_report.md`.
- This planning run currently contains only plan artifacts; the implementation must model the final state after the audit pair writes `artifacts/audit/*` outputs and `sessions/audit.json`.

## Implementation Contract

### 1. Repoint the active current-run contract

- Update `ACTIVE_CURRENT_RUN_RELATIVE_ROOT` and all derived exact-path sets to `run-20260509T041550Z-4b0707de`.
- Keep the current exact-inventory contract style: explicit required-clean paths plus explicit exact per-file exceptions only.
- Do not introduce `.autoloop/**`, `artifacts/audit/**`, or other prefix exclusions.

### 2. Encode the final six-file inventory explicitly

- Add these final-state files to the active current-run inventory:
  - `artifacts/audit/audit_result.json`
  - `artifacts/audit/criteria.md`
  - `artifacts/audit/feedback.md`
  - `artifacts/audit/gap_report.md`
  - `artifacts/audit/revised_request.md`
  - `sessions/audit.json`
- Default classification target:
  - required-clean: `artifacts/audit/criteria.md`, `artifacts/audit/feedback.md`, `artifacts/audit/revised_request.md`, `sessions/audit.json`
  - exact per-file exception: `artifacts/audit/audit_result.json` unless its schema changes to remove the required absolute `revised_request_path`
- Inspect live final `artifacts/audit/gap_report.md` before locking classification. Prefer required-clean, but allow one exact per-file exception only if the final audit text cannot preserve meaning without literal legacy-name strings.

### 3. Keep final audit artifacts clean where possible

- If any current run-local audit/session file that is intended to stay required-clean still emits legacy literals after the audit pair runs, rewrite that run-local artifact text to neutral wording instead of widening the exception list.
- The prior completed run shows `gap_report.md` can drift into `.autoloop` wording when it explains the JSON-path exception, so implementation must recheck that file specifically in the final run state.
- Do not broaden the artifact-policy walker or change audit JSON schema unless a narrower file-level fix is impossible.

### 4. Revalidate the final audited state

- Re-run `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q`.
- Re-run the literal legacy-name scan over the maintained tree plus the final active artifact contract, confirming only exact exceptions still contain allowed operational literals.
- Re-run `./.venv/bin/python -m pytest` after the scoped strictness slice is green.

## Milestones

1. Repoint the active current-run root and update the exact required-clean versus exact-exception file sets for the six final audit/session files.
2. Clean or narrowly except any final run-local audit content that still emits legacy branding, with `audit_result.json` as the expected unavoidable exception and `gap_report.md` rechecked against live content.
3. Re-run the scoped strictness suite, literal artifact scan, and full pytest suite in the final audited state.

## Interfaces And Compatibility

- No runtime, provider, CLI, or persisted-schema behavior changes are planned.
- The only intended behavior change is stricter final-run repository policy for the current active run inventory.
- The current-run contract remains tied to the authoritative run-local path for `run-20260509T041550Z-4b0707de`; do not generalize this into broader task-history rules.

## Regression Risks And Controls

- Risk: planning before audit outputs exist can misclassify final file contents.
  Control: inspect the live `artifacts/audit/*` files and `sessions/audit.json` after they are present, especially `gap_report.md`, before finalizing the exact sets.
- Risk: oversized exceptions can make the tests pass while weakening the strictness contract.
  Control: prefer required-clean for every file except records whose operational schema forces a legacy path literal.
- Risk: stale active-run constants can pass local edits but point strictness at the wrong run inventory.
  Control: update the run root constant and both derived path sets together, then verify the inventory assertion against the authoritative current run directory.

## Rollback

- Revert only the active current-run inventory/exception edits if the final audit content differs from expectations.
- If a markdown audit artifact cannot stay clean, move only that exact file to the exception set rather than adding a broader exclusion.
- Do not keep any partial state that updates the root constant without also updating the final required-clean and exact-exception inventories.
