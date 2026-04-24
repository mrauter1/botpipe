# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260424t163807-c4
- Pair: test
- Phase ID: prompt-contract-doctrine
- Phase Directory Key: prompt-contract-doctrine
- Phase Title: Define Compact Prompt Contract Style
- Scope: phase-local authoritative verifier artifact

- Added baseline coverage in `tests/test_architecture_baseline_docs.py` for shared route/payload table markers across all scoped prompt READMEs, so the builder and selected-workflow families are pinned beyond section-heading presence.
- `TST-000` | `non-blocking` | No audit findings. The added baseline-doc assertion closes the remaining cross-family README coverage gap without introducing flake risk, and the phase-local strategy correctly keeps prompt-body wording out of scope.
