# Test Author ↔ Test Auditor Feedback

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: test
- Phase ID: builtins-packaging-docs-verification
- Phase Directory Key: builtins-packaging-docs-verification
- Phase Title: Relocate Built-Ins, Package Assets, And Close Verification
- Scope: phase-local authoritative verifier artifact

- Added `test_authoring_and_workflow_docs_keep_current_workflow_root_references` to `tests/test_architecture_baseline_docs.py` to catch the reviewer-found stale `` `workflows/` `` guidance and malformed `docs/autoloop/workflows/...` citations.
- Local validation used a deterministic `python3` doc-assertion script because `pytest` is not installed in the base shell.
