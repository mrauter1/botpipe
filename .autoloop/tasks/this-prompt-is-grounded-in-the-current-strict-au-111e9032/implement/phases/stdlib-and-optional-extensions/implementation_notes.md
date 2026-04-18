# Implementation Notes

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: implement
- Phase ID: stdlib-and-optional-extensions
- Phase Directory Key: stdlib-and-optional-extensions
- Phase Title: Add Tiny `stdlib` And Optional `extensions`
- Scope: phase-local producer artifact

## Files changed
- `autoloop_v3/extensions/__init__.py`
- `autoloop_v3/extensions/tracing.py`
- `autoloop_v3/extensions/git/{__init__,declaration,policy,repo,runtime,filters}.py`
- `autoloop_v3/stdlib/{__init__,control,prompts,steps}.py`
- `autoloop_v3/stdlib/state/{__init__,cursor}.py`
- `autoloop_v3/tests/runtime/test_optional_extensions.py`
- `autoloop_v3/tests/unit/test_stdlib_and_extensions.py`
- `.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/decisions.txt`
- `.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/implement/phases/stdlib-and-optional-extensions/implementation_notes.md`

## Symbols touched
- `PromptBundle`
- `PromptPair`
- `global_routes(...)`
- `merge_transitions(...)`
- `pause_on_outcome_tags(...)`
- `event_on_outcome_tags(...)`
- `pair_step(...)`
- `SequenceCursor`
- `Tracing`
- `TracingConfig`
- `GitTracking`
- `GitTrackingConfig`
- `GitChange.status`
- `GitPolicy`
- `GitCommitPlan`
- `GitDelta`
- `GitRepo`
- `GitRepo.raw_delta(...)`
- `GitRepo.commit(...)`

## Checklist mapping
- Milestone 4 / AC-1: added the requested tiny `stdlib` modules only, with pure helper behavior that compiles down to strict workflow primitives.
- Milestone 4 / AC-2: added only the requested optional extension families and kept them workflow-declared and invisible by default through `Workflow.extensions`.
- Milestone 4 / AC-3: separated raw git repo inspection, delta filtering, and workflow-owned commit policy, then covered that split with unit tests.
- Milestone 4 / AC-4: added runtime tests that prove `Tracing(...)` and `GitTracking(...)` activate only when explicitly declared on the workflow.
- Reviewer feedback `IMP-001` / `IMP-002`: fixed empty-selected-scope git commits so they no-op instead of committing unrelated staged changes, and preserved raw two-column git porcelain status semantics in `GitDelta`.

## Assumptions
- `track_task_workspace_artifacts=True` scopes git commits to the task workspace root (`binding.task_folder`), which includes nested run artifacts because the generic run directory lives under that root.

## Preserved invariants
- Runtime core stays git-agnostic and tracing-agnostic; it still only binds declared workflow extensions.
- `events.jsonl` remains the generic always-on history artifact.
- `SessionPaths(...)` remains the existing explicit session-path opt-in surface.
- `stdlib` imports only standard library modules plus `autoloop_v3.workflow` surfaces.
- Git policies still receive raw repository delta objects before any commit-scope narrowing is applied.

## Intended behavior changes
- Workflows can now import and use the tiny stdlib helpers instead of repeating small prompt/control boilerplate.
- Workflows can now opt into tracing sidecar output with `Tracing(...)`.
- Workflows can now opt into generic git tracking with workflow-owned commit policy via `GitTracking(...)`.
- Empty selected git scope is now a safe no-op unless the plan is an explicit empty commit with nothing staged.
- `GitChange.status` now preserves git porcelain v1 `XY` semantics so policies can distinguish staged-only vs unstaged-only changes.

## Known non-changes
- No workflow-specific git policy was added to the reusable git extension.
- No runtime config path auto-enables git or tracing.
- No workflow migrations were done in this phase.

## Expected side effects
- New optional import surfaces under `autoloop_v3.stdlib` and `autoloop_v3.extensions`.
- Git tracking may create commits only when the workflow explicitly declares it and the policy returns commit plans.
- Tracing may create a run-relative JSONL sidecar only when the workflow explicitly declares it.

## Validation performed
- `pytest autoloop_v3/tests/unit/test_stdlib_and_extensions.py autoloop_v3/tests/runtime/test_optional_extensions.py`
- `pytest autoloop_v3/tests`

## Deduplication / centralization
- Centralized stdlib authoring helpers in `autoloop_v3.stdlib` instead of repeating route/prompt glue in workflows.
- Centralized git repo mechanics in `extensions/git/repo.py`, kept raw-delta filtering in `extensions/git/filters.py`, and kept commit timing/messages in workflow-owned policy objects.
