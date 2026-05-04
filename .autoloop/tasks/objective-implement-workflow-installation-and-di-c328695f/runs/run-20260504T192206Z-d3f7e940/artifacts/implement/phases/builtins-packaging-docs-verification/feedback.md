# Implement ↔ Code Reviewer Feedback

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: implement
- Phase ID: builtins-packaging-docs-verification
- Phase Directory Key: builtins-packaging-docs-verification
- Phase Title: Relocate Built-Ins, Package Assets, And Close Verification
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [docs/authoring.md:1169]: The recursive/workflow-reference guidance still tells readers to look at `workflows/`, which contradicts the requested package root contract (`autoloop/workflows/`) and fails AC-3's requirement that documentation consistently state the new roots and the absence of `{workspace}/workflows/` discovery. Concrete failure scenario: an operator following the updated authoring guide is pointed at the removed legacy root immediately after this phase's migration. Minimal fix: finish the docs sweep by replacing that stale repo-root reference with `autoloop/workflows/` (and keep `.autoloop/workflows/` alongside it where the section is enumerating discovery-relevant paths).
- IMP-002 `non-blocking` [docs/workflows/workflow_package_to_composable_building_blocks.md:53]: The bulk path rewrite introduced a malformed doc path, `docs/autoloop/workflows/workflow_idea_to_workflow_package.md`, which does not exist in the relocated layout. This does not break runtime behavior, but it leaves one of the updated workflow docs with a dead reference. Minimal fix: rewrite that citation to the real documentation path, `docs/workflows/workflow_idea_to_workflow_package.md`.
