# Implement ↔ Code Reviewer Feedback

- Task ID: revised-sdk-implementation-spec-1-scope-implemen-1e1a7513
- Pair: implement
- Phase ID: sdk-retention-and-safe-cleanup
- Phase Directory Key: sdk-retention-and-safe-cleanup
- Phase Title: SDK Retention And Safe Cleanup
- Scope: phase-local authoritative verifier artifact

- IMP-001 [blocking] `autoloop/sdk.py::_promote_declared_write`
  The collision-avoidance branch is unreachable because `destination` is always constructed under `base_dir`, so `destination.exists() and not _is_inside_path(destination, base_dir)` can never be true. If a caller sets `RetentionPolicy(promoted_writes_dir=shared_dir)` and two SDK runs promote the same task-local artifact path, the later run will silently overwrite the earlier promoted output. That violates the spec’s overwrite/unique-suffix rule for promoted writes and creates a real data-integrity regression for retained artifacts. Minimal fix: centralize destination selection so the code distinguishes the current task’s promotion directory from a caller-supplied shared base, and call `_uniquify_path(...)` whenever an existing destination was not created for the current task.

- IMP-001 follow-up [non-blocking]
  Re-reviewed in verifier cycle 2 attempt 1: the implementation now routes promotion through `_promotion_destination(...)`, uniquifies collisions for caller-supplied shared `promoted_writes_dir` bases, and adds regression coverage for the two-run shared-directory overwrite case. No additional findings were identified in this pass.
