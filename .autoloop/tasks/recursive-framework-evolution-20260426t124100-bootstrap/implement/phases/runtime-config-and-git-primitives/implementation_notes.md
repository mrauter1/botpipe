# Implementation Notes

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: implement
- Phase ID: runtime-config-and-git-primitives
- Phase Directory Key: runtime-config-and-git-primitives
- Phase Title: Runtime Config And Git Primitives
- Scope: phase-local producer artifact

## Files Changed
- `runtime/config.py`
- `runtime/cli.py`
- `extensions/git/repo.py`
- `tests/runtime/test_provider_backends.py`
- `tests/runtime/test_package_cli.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `.autoloop/tasks/recursive-framework-evolution-20260426t124100-bootstrap/decisions.txt`

## Symbols Touched
- `GitCommitPolicy`
- `FailureMode`
- `GitTrackingRuntimeConfig`
- `TracingRuntimeConfig`
- `RuntimeConfig`
- `GitTrackingRuntimeConfigOverride`
- `TracingRuntimeConfigOverride`
- `parse_runtime_config`
- `resolve_runtime_config`
- `_merge_runtime_config`
- `build_arg_parser`
- `GitRepo.status_porcelain`
- `GitRepo.is_dirty`
- `GitRepo.add_all`
- `GitRepo.commit_all`

## Checklist Mapping
- Plan milestone 2 / checklist items 5-7: completed in this phase.
- Later observability wiring, runtime tracker/tracer modules, static graph writing, and resume sequencing: intentionally deferred to later phases.

## Assumptions
- CLI override precedence for combined git flags must be deterministic without relying on argv order.
- This phase only needs config/CLI/git primitives; runner execution behavior remains unchanged until later observability phases consume the new runtime config.

## Preserved Invariants
- Existing provider config merge precedence remains unchanged.
- Workflow-scoped git commit behavior in `GitRepo.commit(...)` remains intact for compatibility.
- No runtime observability binding or workflow-extension filtering was added in this phase.

## Intended Behavior Changes
- Resolved runtime config now defaults `runtime.git_tracking.enabled=true`, `commit_policy=step`, `failure_mode=raise`.
- Resolved runtime config now defaults `runtime.tracing.enabled=true`, `path=trace.jsonl`, `failure_mode=raise`, `include_state_snapshots=true`.
- Nested runtime config sections now treat only `null` / omission as missing; falsy non-mapping values for `runtime.git_tracking` and `runtime.tracing` are rejected instead of silently falling back to defaults.
- Mutating CLI commands now accept `--no-git`, `--git-commit-policy`, and `--no-trace`.
- `GitRepo` now exposes full-workspace status/dirty helpers plus `commit_all()` with `git add --all` semantics and no empty commits.

## Known Non-Changes
- `RunnerOptions`, runner execution, and engine binding do not consume the new runtime git/tracing config yet.
- No runtime git tracking files, trace files, or workspace-order changes were implemented in this phase.
- No documentation updates were made in this phase.

## Expected Side Effects
- Provider factories invoked by CLI tests now receive a richer `ResolvedRuntimeConfig.runtime` structure.
- Future phases can consume runtime git/tracing settings without changing the config surface again.

## Validation Performed
- `python3 -m compileall runtime extensions tests`
- Direct smoke script for `runtime/config.py` defaults and CLI override precedence, loaded from file path to avoid missing package dependencies.
- Direct smoke script for `runtime/config.py` nested section validation, confirming falsy non-mapping values for `runtime.git_tracking` and `runtime.tracing` now raise `ConfigError`.
- Direct smoke script for `extensions/git/repo.py` `is_dirty()` and `commit_all()` behavior in a temporary git repo, loaded with a minimal stub policy module because the full test dependency set is unavailable.
- Full `pytest` execution was not possible in this environment because `pytest` is not installed.

## Deduplication / Centralization
- Nested runtime git/tracing parsing and merge logic was added inside the existing config layer instead of creating a separate observability config parser.
- Commit-all behavior was added to `GitRepo` directly so later runtime-owned tracking can reuse the existing git abstraction instead of duplicating subprocess logic.
