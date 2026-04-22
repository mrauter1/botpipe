# Criteria

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: test
- Phase ID: docs-tests-and-legacy-removal
- Phase Directory Key: docs-tests-and-legacy-removal
- Phase Title: Docs Tests And Legacy Removal
- Scope: phase-local authoritative verifier artifact

Check these boxes (`- [x]`) only when true.

- [x] **Coverage Quality**: New or changed behavior is covered at the appropriate level, and preserved behavior is covered where regression risk is material.
- [x] **Regression Protection**: Tests would catch likely regression bugs, logical flaws, and unintended behavior in changed or adjacent behavior.
- [x] **Edge Cases / Failure Paths**: Relevant boundary cases, error cases, and failure paths are covered.
- [x] **Reliability**: Tests avoid flaky assumptions and use stable setup, timing, ordering, and environment expectations.
- [x] **Behavioral Intent**: Tests do not encode a regression, reduced behavior, or compatibility break unless that change is explicitly required by user intent and explicitly confirmed.

Audit note: the phase strategy, focused runtime/docs/strictness coverage, and the added same-root loader invariant test collectively satisfy the requested docs-tests-and-legacy-removal test contract without normalizing unapproved behavior breaks.
