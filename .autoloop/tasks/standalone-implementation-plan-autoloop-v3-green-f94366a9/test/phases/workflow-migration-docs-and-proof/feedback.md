# Test Author ↔ Test Auditor Feedback

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: test
- Phase ID: workflow-migration-docs-and-proof
- Phase Directory Key: workflow-migration-docs-and-proof
- Phase Title: Workflow migration, docs, and proof
- Scope: phase-local authoritative verifier artifact

- Added a focused regression test in `tests/test_architecture_baseline_docs.py` so the active docs vocabulary boundary now explicitly includes the root `cleanup.md` note and the recursive template docs that were scrubbed during implementation.
- Updated `test_strategy.md` with the behavior-to-test coverage map for simple authoring, provider/engine contract enforcement, bundled workflow parity, capability/stdlib payloads, and active-doc terminology checks.
