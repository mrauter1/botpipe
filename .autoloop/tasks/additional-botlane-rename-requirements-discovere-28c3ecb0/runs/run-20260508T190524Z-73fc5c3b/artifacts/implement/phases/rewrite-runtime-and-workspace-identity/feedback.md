# Implement ↔ Code Reviewer Feedback

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: implement
- Phase ID: rewrite-runtime-and-workspace-identity
- Phase Directory Key: rewrite-runtime-and-workspace-identity
- Phase Title: Rewrite Runtime And Workspace Identity
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [botlane/core/workflow_catalog.py:96-120, 438-443] The implementation adds separate search-root precedence values for `workflows/`, `.botlane/workflows`, and `.autoloop/workflows`, but the effective catalog still ignores `entry.precedence` and collapses every non-repo workspace root to the same priority via `_resolution_precedence()`. When the same workflow exists in both `.botlane/workflows` and `.autoloop/workflows`, lexicographic path ordering can let the legacy `.autoloop` workflow shadow the canonical Botlane workflow, so `resolve_workflow_reference("name")` may import stale legacy code. Minimal fix: centralize effective ordering on the declared search-root precedence (for example by using `entry.precedence` inside `_resolution_precedence()` / `_effective_catalog()`), so `.botlane` always wins over `.autoloop`.

- `IMP-002` `blocking` [botlane/runtime/runner.py:636-668] Resume fallback only checks whether the Botlane workflow root has any run (or the explicit `run_id`) before deciding to stay on `.botlane`; it never compares latest/resumable candidates across both readable roots. If a task/workflow has a newer or only-resumable legacy `.autoloop` run alongside any `.botlane` run, `botlane resume <workflow> <task>` will select the Botlane root unconditionally and can resume the wrong run or fail despite a valid legacy checkpoint existing. Minimal fix: resolve the resume candidate from a shared cross-root selector (the same logical ordering used by public run listing/lookup), then derive the workspace root from the chosen run record instead of root-presence heuristics.

- `IMP-003` `non-blocking` [validation scope] The implementation notes correctly record that neither `pytest` nor runtime dependencies such as `pydantic` are available in this environment, so this phase currently has only `compileall` proof. That leaves P2-AC1/P2-AC3 unexecuted in practice. Minimal fix: rerun the focused runtime/SDK tests in an environment with the project test dependencies before closing the phase.
