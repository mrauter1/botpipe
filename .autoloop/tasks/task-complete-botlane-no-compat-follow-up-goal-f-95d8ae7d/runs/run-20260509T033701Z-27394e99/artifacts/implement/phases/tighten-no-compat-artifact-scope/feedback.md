# Implement ↔ Code Reviewer Feedback

- Task ID: task-complete-botlane-no-compat-follow-up-goal-f-95d8ae7d
- Pair: implement
- Phase ID: tighten-no-compat-artifact-scope
- Phase Directory Key: tighten-no-compat-artifact-scope
- Phase Title: Tighten Repo-Root Artifact No-Compat Enforcement
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `tests/strictness/test_no_compat.py:383-389`, `.autoloop_recursive/framework_gap_ledger.md:216` | The new repo-root artifact scan still misses the legacy wrapper token `recursive_autoloop`. One maintained in-contract recursive-memory file still contains `recursive_autoloop/`, but `LEGACY_BRANDING_PATTERNS` only checks `autoloop`, `Autoloop`, `AUTOLOOP`, `.autoloop`, `autoloop_optimizer`, and `_autoloop_workspace_workflows`. Concrete failure: `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py` passes while `.autoloop_recursive/framework_gap_ledger.md` still violates the requested no-compat cleanup, and future `recursive_autoloop` regressions in maintained artifact files would also slip through. Minimal fix: remove the remaining `recursive_autoloop/` literal from the maintained gap ledger and extend the repo-root branding scan to treat `recursive_autoloop` as a forbidden legacy token alongside the other exact legacy-name checks.
