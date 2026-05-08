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
