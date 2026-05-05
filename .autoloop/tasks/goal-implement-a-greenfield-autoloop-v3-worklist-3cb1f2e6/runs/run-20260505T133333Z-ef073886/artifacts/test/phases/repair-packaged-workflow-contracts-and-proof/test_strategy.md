# Test Strategy

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: test
- Phase ID: repair-packaged-workflow-contracts-and-proof
- Phase Directory Key: repair-packaged-workflow-contracts-and-proof
- Phase Title: Repair Packaged Workflow Contracts And Proof
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- Shared candidate-surface manifest helpers:
  baseline validation accepts canonical first-party publication labels such as `autoloop/workflows/...` while copying and hashing repo-local `workflows/...` source files via explicit `source_path`.
- Shared candidate-surface drift protection:
  authoritative-source drift checks continue to hash the recorded `source_path` bytes and report the canonical published `relative_path` on failure.
- Preserved packaged-workflow contract:
  the test stays at the shared helper layer so workflow-package/refinement/decomposition callers inherit the same canonical-label versus actual-source-path contract without workflow-specific shims.

## Edge Cases And Failure Paths

- Canonical `relative_path` differs from the actual repo-local source location but remains repo-relative and valid.
- Drift after baseline capture is detected from the actual source file, not from the canonical published label alone.

## Validation Plan

- Run the focused candidate-surface helper tests in `tests/unit/test_stdlib_and_extensions.py`.

## Known Gaps

- This phase artifact does not duplicate the full packaged-workflow/runtime proof already exercised by the implementation-phase repository and targeted suite runs.
