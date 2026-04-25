# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: test
- Phase ID: public-surface-docs-regression
- Phase Directory Key: public-surface-docs-regression
- Phase Title: Public Surface, Docs, And Regression
- Scope: phase-local authoritative verifier artifact

- Added unit regression coverage in `tests/unit/test_primitives_and_stores.py` for three public-surface-adjacent failure modes: typed child input against legacy invokers now fails loudly, schema-bearing directory artifacts are rejected, and mid-chain `None` `state.*` placeholders resolve safely instead of being mistaken for missing work-item scope.
- Re-ran `.venv/bin/pytest -q`; suite passed with `682 passed`.
- TST-000 | non-blocking | No findings. The added low-level guards complement the existing runtime suites in the right places, the phase-local strategy maps changed behavior to concrete coverage, and the final full-suite proof (`682 passed`) keeps the phase deterministic and regression-resistant.
