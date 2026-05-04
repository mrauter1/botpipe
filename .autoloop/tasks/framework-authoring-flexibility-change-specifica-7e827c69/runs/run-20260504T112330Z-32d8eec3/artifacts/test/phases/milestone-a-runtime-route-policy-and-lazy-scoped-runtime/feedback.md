# Test Author ↔ Test Auditor Feedback

- Task ID: framework-authoring-flexibility-change-specifica-7e827c69
- Pair: test
- Phase ID: milestone-a-runtime-route-policy-and-lazy-scoped-runtime
- Phase Directory Key: milestone-a-runtime-route-policy-and-lazy-scoped-runtime
- Phase Title: Milestone A Runtime Semantics
- Scope: phase-local authoritative verifier artifact

- Added explicit contract coverage for child-workflow undeclared `failed` / `blocked` mappings, additive `worklist_selection_resolved` payload fields, and ensure-capable source behavior across first use, resume restore, and refresh.
- Coverage map in `test_strategy.md` now ties Milestone A behaviors to concrete tests and calls out the remaining environment-backed execution gap (`pytest` / runtime deps unavailable in this shell).
- TST-001 `non-blocking` — Coverage shape is adequate for the changed Milestone A behaviors and the preserved invariants with material regression risk. The remaining caveat is execution only: this shell still lacks `pytest` and installed runtime deps, so the documented suites need an external run to convert coverage intent into observed passing status.
