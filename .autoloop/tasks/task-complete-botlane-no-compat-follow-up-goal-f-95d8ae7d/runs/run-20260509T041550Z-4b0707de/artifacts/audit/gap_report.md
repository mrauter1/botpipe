# Original intent considered

- Close the repo-root artifact-tree scan loophole in `tests/strictness/test_no_compat.py`.
- Enforce an explicit exact-path policy for maintained recursive-memory files and the active current-run artifact tree.
- Keep removable legacy-name literals out of maintained active artifact files.
- Keep historical allowances narrow and explicit.
- Leave the final codebase with scoped strictness validation and full-suite validation green.

# Clarifications / superseding decisions

- The current-run contract stays exact-path-based rather than using any directory-level exclusion.
- Clean treatment remains preferred for audit/session files whose live contents do not require removed legacy-name literals.
- The path-bearing audit result remains the only exact per-file operational exception in the final audited state.

# Implemented behavior

- `tests/strictness/test_no_compat.py` now points at `run-20260509T041550Z-4b0707de` for the active current-run contract.
- The final inventory explicitly covers the five audit artifacts plus `sessions/audit.json`.
- Required-clean treatment now covers the audit markdown files, `request.md`, the audit session record, the runtime-written phase session record, and the clean test-phase artifacts written later in the same run.
- The repo-root artifact walker still scans every clean-classified current-run file directly from the explicit inventory.
- Final validation is green in the live tree:
  - `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q` -> `72 passed`
  - `./.venv/bin/python -m pytest` -> `1204 passed, 1 warning`

# Unresolved gaps

- None. The final active current-run inventory matches the live file set after the audit artifacts and audit session record were written.
- The strictness policy keeps the unavoidable path-bearing audit result as a single exact-file exception without widening to a broader path rule.

# Differences justified by later clarification or analysis

- Later implementation/test analysis extended the required-clean inventory beyond the originally named six files to include the post-runtime phase session record and the test-phase artifacts, because the final contract must match the live current-run file set after all pair-owned records exist.
- Retaining the audit result as an exact exception is necessary because its schema stores an absolute run-local path to the revised request record.
- Rewriting the gap report to describe that exception without removed legacy tokens keeps the contract narrow while preserving the audit rationale.

# Recommended next run

- No follow-up implementation run is required for this strictness slice if the repository state stays unchanged.
