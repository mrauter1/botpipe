# Implement ↔ Code Reviewer Feedback

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: implement
- Phase ID: stdlib-and-optional-extensions
- Phase Directory Key: stdlib-and-optional-extensions
- Phase Title: Add Tiny `stdlib` And Optional `extensions`
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [autoloop_v3/extensions/git/repo.py:50 `GitRepo.commit()`]: when git tracking filters the task scope down to an empty delta, `repo.commit(..., pathspecs=())` still commits whatever is already staged in the repository. Concrete failure: with `track_task_workspace_artifacts=True`, an unrelated staged `README.md` outside the task workspace is committed even though the filtered task delta is empty. That breaks the workflow-owned scope boundary and can silently commit unrelated user work. Minimal fix: make empty filtered deltas a no-op unless the caller explicitly opts into committing pre-staged changes, and add a regression test for the empty-pathspec / staged-outside-scope case at the repo or runtime-extension layer.
- `IMP-002` `blocking` [autoloop_v3/extensions/git/repo.py:35 `GitRepo.raw_delta()`]: raw delta collection strips Git porcelain’s two-column `XY` status into collapsed tokens like `"M"`, so policies cannot distinguish staged-only, unstaged-only, and mixed changes. Concrete failure: a staged-only modification and an unstaged-only modification both surface as `GitChange(status="M", ...)`, which contradicts the phase requirement that raw delta semantics stay intact for workflow-owned policy. Minimal fix: preserve the full porcelain `XY` state or split it into explicit index/worktree status fields in `GitChange`, then add direct `raw_delta()` regression coverage for staged-only vs unstaged-only changes.

## Re-review Cycle 2

- `IMP-001` resolved: `GitRepo.commit(..., pathspecs=())` now treats an empty selected scope as a no-op unless it is an explicit empty commit with nothing staged, and repo-level regression coverage now protects the staged-outside-scope case.
- `IMP-002` resolved: `GitRepo.raw_delta()` now preserves the raw two-column porcelain `XY` token, and repo-level regression coverage now distinguishes staged-only from unstaged-only changes.
- No remaining blocking or non-blocking findings in the phase-local scope reviewed this cycle.
