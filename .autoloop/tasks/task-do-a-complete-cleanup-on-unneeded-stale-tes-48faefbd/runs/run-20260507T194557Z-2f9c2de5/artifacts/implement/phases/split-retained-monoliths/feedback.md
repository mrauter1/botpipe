# Implement ↔ Code Reviewer Feedback

- Task ID: task-do-a-complete-cleanup-on-unneeded-stale-tes-48faefbd
- Pair: implement
- Phase ID: split-retained-monoliths
- Phase Directory Key: split-retained-monoliths
- Phase Title: Split Retained Monoliths
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` `tests/conftest.py:collect_ignore`, `tests/contract/test_engine_contracts.py`, `tests/unit/test_stdlib_and_extensions.py`: the phase objective was to split the two oversized retained suites into ownership-aligned modules, but the implementation only adds import-only wrapper modules and then hides the real source files from pytest collection via `collect_ignore`. This leaves the 10k-line and 5.6k-line monoliths as the actual maintenance surface, so the requested ownership split never happens, and it introduces a concrete regression risk: any future retained test added or edited in those real source files will be silently skipped by collection because the files are ignored. Minimal fix: move the retained test definitions into the new domain modules, extract only genuinely shared helpers into adjacent helper modules if needed, and retire or rename the original monolith files so pytest no longer depends on `collect_ignore` to suppress them.
