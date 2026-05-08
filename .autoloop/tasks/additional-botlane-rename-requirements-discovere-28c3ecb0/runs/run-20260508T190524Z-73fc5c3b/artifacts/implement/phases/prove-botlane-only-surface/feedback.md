# Implement ↔ Code Reviewer Feedback

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: implement
- Phase ID: prove-botlane-only-surface
- Phase Directory Key: prove-botlane-only-surface
- Phase Title: Prove Botlane Only Surface
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [tests/strictness/test_no_compat.py:44-59, 110-118, 168-189; recursive_autoloop/run_recursive_autoloop.sh:4-30; rebrand.md:1-57]
  The final grep gate does not satisfy P4-AC2 or the explicit request. The new proof only scans `botlane/`, `botlane_optimizer/`, `docs/`, `tests/`, `pyproject.toml`, and three root files, while tracked non-generated, non-history files still contain live legacy branding and CLI/workspace examples, including `recursive_autoloop/` and root spec docs like `rebrand.md`. The implementation notes acknowledge this as an unsupported assumption rather than a confirmed scope carveout. As written, the suite passes while the repository still violates the required “no active autoloop/Autoloop/.autoloop/... outside explicit historical changelog text” condition. Minimal fix: either rename the remaining maintained files/directories to Botlane-only text and extend the strictness scan to them, or explicitly move/classify the retained files into a documented changelog/history allowlist and centralize that allowlist in the strictness test.

- IMP-002 `non-blocking` [MANIFEST.in:1-3]
  `prune .auto*loop` avoids a literal legacy token, but it broadens the manifest rule beyond the actual legacy state directory and makes the packaging intent harder to audit. Prefer an explicit, documented exclusion strategy once the grep policy’s allowed generated-state exceptions are settled, so package pruning and branding proof are both obvious to future maintainers.

- IMP-001 status update
  Resolved in cycle 2 re-review. The implementation now renames the maintained recursive wrapper surface to `recursive_botlane/`, rewrites the root review/spec markdown files to Botlane-only text, and extends the strictness gate to scan those maintained files directly.

- IMP-003 `blocking` [tests/strictness/test_no_compat.py:40-61, 168-189; legacy_docs/policy.md:3-166; legacy_docs/sdk.md:59-860; legacy_docs/refactor8.md:8-770]
  P4-AC2 and the shared decisions ledger still are not fully satisfied because the final branding proof excludes `legacy_docs/**` wholesale, yet that directory contains many tracked non-generated files with live `autoloop`, `.autoloop`, `autoloop_optimizer`, and `Autoloop*` examples. The accepted rule allows exclusions only for automation-owned generated state and explicitly named changelog/history files; a blanket `legacy_docs/` carveout is broader than that policy and lets the suite pass while repository-owned docs still violate the Botlane-only grep requirement. Minimal fix: either scan `legacy_docs/**` and rewrite/archive the remaining live references, or replace the broad directory exclusion with a centralized allowlist of explicitly named history files that the strictness test enforces.

- IMP-003 status update
  Resolved in cycle 3 re-review. The proof no longer excludes `legacy_docs/**` broadly: `tests/strictness/test_no_compat.py` now inventories `legacy_docs/*.md` as an explicit per-file history allowlist and runs the branding scan from `REPO_ROOT`, skipping only generated state and those named history files.

- Cycle 3 re-review
  No blocking findings remain. `IMP-002` stays advisory only.
