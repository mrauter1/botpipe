# Implement ↔ Code Reviewer Feedback

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: reconcile-optimizer-source-contracts
- Phase Directory Key: reconcile-optimizer-source-contracts
- Phase Title: Reconcile Optimizer Source Contracts
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` `autoloop_optimizer/optimization.py:_canonical_selected_workflow_manifest_dir`
  A read-only manifest write now mutates the target repo by creating `autoloop/workflows/<workflow_name>` whenever the selected workflow only exists under repo-local `workflows/`. A minimal reproduction with `write_selected_workflow_source_manifest(...)` creates that tree even before publication. This violates the selected-workflow non-mutation contract and will dirty user repos during plain optimizer framing. Minimal fix: keep canonicalization logical only. Normalize the stored manifest paths against the canonical package surface, or materialize any baseline copy under the workflow run folder, but do not write into the repo root.

- IMP-002 `blocking` `autoloop_optimizer/optimization.py:_first_party_workflow_source_dir`, `write_selected_workflow_source_manifest`
  The manifest no longer hashes the selected repo's actual workflow bytes for first-party workflow names. After a repo-local `workflows/release_candidate_to_go_no_go/workflow.toml` drift, the new helper still copies and hashes the executing checkout's `autoloop/workflows/release_candidate_to_go_no_go` tree instead, so mutation checks can miss or misreport changes in the selected source. Minimal fix: hash the resolved workflow files from the current repo and only canonicalize the published relative-path contract. If a shared helper is needed, centralize it around "actual source bytes + canonical manifest path labels" rather than importing bytes from the installed source tree.

## Cycle 2 Review Update

- Prior blocking findings `IMP-001` and `IMP-002` no longer reproduce after the manifest-label / actual-source-byte fix.
- No new findings in scoped review.
