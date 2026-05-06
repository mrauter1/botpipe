# Test Author ↔ Test Auditor Feedback

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: test
- Phase ID: tests-and-docs-migration
- Phase Directory Key: tests-and-docs-migration
- Phase Title: Migrate Tests And Docs
- Scope: phase-local authoritative verifier artifact

- Added docs-regression hardening in `tests/test_architecture_baseline_docs.py` so the shared `Workflow_Instructions.md` contract must name `ControlRoutes(question=...)` and top-level `question` / `reason` as compatibility-only migration surfaces, while still forbidding the stale reserved-route phrasing.

- Audit C1: No blocking or non-blocking test findings. The new assertion meaningfully tightens regression protection by requiring the exact compatibility-only sentence, the strategy artifact maps the covered behavior and known gaps clearly, and `./.venv/bin/python -m pytest -q tests/test_architecture_baseline_docs.py` passes without introducing flake risk.
