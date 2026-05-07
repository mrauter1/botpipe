# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: implement
- Phase ID: ctx-regression-coverage-and-docs
- Phase Directory Key: ctx-regression-coverage-and-docs
- Phase Title: Lock In Behavior With Tests And Docs
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [tests/test_architecture_baseline_docs.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/test_architecture_baseline_docs.py): the new doc-baseline assertions were added to an untracked file (`git status --short` reports `?? tests/test_architecture_baseline_docs.py`), so the claimed AC-2 regression coverage is not actually part of the tracked repository deliverable. In a follow-up branch or clean checkout, those assertions would disappear unless the file is explicitly added. Minimal fix: move the new ctx-specific doc assertions into a tracked baseline test surface or explicitly add this file to the repository.
