# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: async-branch-runtime
- Phase Directory Key: async-branch-runtime
- Phase Title: Async Branch Runtime
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — [autoloop/core/branch_groups/runtime.py:97](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/branch_groups/runtime.py:97), [autoloop/core/branch_groups/runtime.py:305](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/branch_groups/runtime.py:305), and [autoloop/core/branch_groups/manifest.py:10](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/branch_groups/manifest.py:10) still root branch-group evidence under `context.root / "_branch_groups"` even though the authoritative spec and run decisions require `{workflow_folder}/_branch_groups/<group>/...`. The new contract and tracing tests were also updated to assert the old root-level path, which now entrenches the superseded layout instead of migrating it. Concrete failure: any fan-in/downstream consumer implemented to the accepted contract will look under `workflow_folder/_branch_groups/...` and miss the generated evidence, and later migration must unwind the freshly-added tests in the same area. Minimal fix: centralize the path change in `branch_group_paths(...)` and the per-branch raw-output root so every runtime caller uses `context.workflow_folder`, then update the branch-group runtime/tracing tests to assert the workflow-folder-relative evidence paths rather than `tmp_path / "_branch_groups"`.
