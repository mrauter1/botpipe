# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: test
- Phase ID: compatibility-bridge-removal
- Phase Directory Key: compatibility-bridge-removal
- Phase Title: Remove Compatibility Bridges
- Scope: phase-local authoritative verifier artifact

- Added strictness coverage that scans maintained Python roots for deleted non-core `autoloop_v3` namespace imports (`runtime`, `extensions`, `stdlib`, `workflows`, `autoloop_optimizer`), alongside the existing `autoloop_v3.core` / `core._compat` scan.
- Updated `test_strategy.md` with the behavior-to-test map, preserved invariants, failure-path handling, and current validation gap caused by missing local test dependencies.
- Follow-up: widened the maintained-source scan to cover the full `tests/` tree, including top-level files such as `tests/conftest.py` and `tests/test_architecture_baseline_docs.py`, while still excluding the strictness file itself to avoid a false positive on the intentional `autoloop_v3.core` failed-import assertion.

- TST-001 `blocking` — [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py) claims to scan the maintained Python surface for forbidden compatibility imports, but `MAINTAINED_PYTHON_SCAN_ROOTS` omits the top-level `tests/` files. That excludes maintained files such as [tests/conftest.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/conftest.py) and [tests/test_architecture_baseline_docs.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/test_architecture_baseline_docs.py). Missed-regression scenario: one of those files can reintroduce `autoloop_v3.core`, `core._compat`, or deleted `autoloop_v3.runtime` / `extensions` / `stdlib` / `workflows` / `autoloop_optimizer` imports and the new strictness tests still pass, even though those files are part of the maintained regression surface and `tests/conftest.py` can break the whole suite at import time. Minimal correction: expand the maintained Python scan to include top-level `tests/*.py` coverage, either by scanning `REPO_ROOT / "tests"` with explicit self-exclusion rules or by adding the missing top-level files to the maintained scan roots.
