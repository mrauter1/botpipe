# Runtime Tracking And Tracing Prerequisites Plan

## Outcome
Implement runtime-owned observability for run and resume flows so a normal Autoloop v3 run in a clean git repository writes `run.json`, `events.jsonl`, `trace.jsonl`, `git_tracking.jsonl`, `static_step_graph.json`, and runtime-owned `raw/` outputs by default. This slice does not implement workflow optimization, prompt mutation, source mutation, LLM judging, ranking, or any second execution model.

## Mandatory Invariants
- Clean git preflight must happen before any run workspace file or directory is created or touched when runtime git tracking is enabled.
- Runtime git tracking is authoritative; workflow-declared `GitTracking` remains import-compatible but is not bound.
- Runtime tracing is enabled by default and does not require workflow-declared `Tracing`; workflow-declared tracing remains allowed as a sidecar.
- `trace.jsonl` records execution evidence and `commit_before_step` only; `git_tracking.jsonl` records `commit_after_step` and `commit_after_run`.
- Resume appends trace/git/raw evidence, advances the shared sequence, and never overwrites existing raw files.
- Runtime observability must not mutate workflow state or break existing workflow extension ordering and failure semantics.

## Required Execution Ordering
### New run
1. Resolve CLI and runtime config overrides.
2. Resolve the workflow reference and load enough metadata to know `workflow_name`.
3. If runtime git tracking is enabled, discover the repo, enforce the clean-start rule, and capture `commit_before_run`.
4. Create task/workflow/run workspace paths and materialize the run workspace only after git eligibility is decided.
5. Write initial `run.json`.
6. Write `static_step_graph.json`.
7. Initialize `trace.jsonl` and `git_tracking.jsonl` if missing.
8. Create the runtime init commit when `commit_policy` is `run` or `step`.
9. Start engine execution.

### Resume
1. Resolve CLI and runtime config overrides.
2. Resolve the workflow reference and load enough metadata to know `workflow_name`.
3. If runtime git tracking is enabled, discover the repo and enforce the clean-start rule before appending any resume-created evidence.
4. Open the existing run directory and load existing `run.json` if present.
5. Determine the next shared sequence from `trace.jsonl`, `git_tracking.jsonl`, and `raw/`.
6. Re-initialize append-only observability writers without overwriting prior evidence.
7. Apply resume compatibility rules for current git-tracking config versus prior run metadata before writing new records.
8. Create the runtime init/resume commit when `commit_policy` is `run` or `step`.
9. Resume engine execution.

## Milestones
### 1. Provider Usage And Core Event Plumbing
- Files: `core/providers/models.py`, `core/providers/fake.py`, `runtime/providers/_common.py`, `runtime/providers/codex.py`, `runtime/providers/claude.py`, `runtime/provider_backends.py`, `core/extensions.py`, `core/engine.py`.
- Add `TokenUsage` and `StepProviderUsage`, extend provider responses with optional `usage`, and carry usage through fake/runtime providers without failing when unavailable.
- Extend `StepFinish` with optional `provider_usage` only; keep git and static-graph data out of core events.
- Update pair and llm execution paths so `StepFinish` receives producer/verifier/llm usage in the exact shape requested.
- Validation: targeted provider model tests, fake provider tests, engine step-finish assertions for pair and llm steps.
- Regression guard: preserve current provider APIs for callers that ignore `usage`, and keep system steps unchanged.

### 2. Runtime Config, CLI, And Git Primitive Groundwork
- Files: `runtime/config.py`, `runtime/cli.py`, `extensions/git/repo.py`.
- Extend runtime config with nested git-tracking and tracing settings using the existing config-parsing style, including defaults and validation for `commit_policy` and `failure_mode`.
- Add CLI overrides `--no-git`, `--git-commit-policy`, and `--no-trace` on `run`, `resume`, and `answer` paths through resolved runtime config rather than ad hoc flags downstream.
- Add `GitRepo.status_porcelain()`, `is_dirty()`, `add_all()`, and `commit_all()` using `git add --all` and no path filtering.
- Validation: config parser defaults, invalid policy rejection, CLI override tests, git helper unit tests for noop and untracked-file commits.
- Regression guard: keep existing workflow-owned git policy/pathspec helpers intact for compatibility imports.

### 3. Runtime Observability Persistence And Sequencing
- Files: `runtime/git_tracking.py`, `runtime/tracing.py`, `runtime/workspace.py`, `core/workflow_capabilities.py` or `runtime/static_graph.py`.
- Implement `RuntimeGitTracker` with preflight repo discovery, clean-start eligibility handling, commit-all milestone writes, and append-only `git_tracking.jsonl`.
- Implement `RuntimeTraceWriter` with append-only `trace.jsonl`, raw-output persistence, SHA-256/byte metadata, provider usage serialization, and fatal-path handling that respects tracing failure mode.
- Add static step graph serialization from compiled workflows and persist `static_step_graph.json` for every run.
- Centralize `run.json` updates for git tracking, tracing, warnings, and append-only git step metadata; add shared sequence discovery across trace/git/raw for resume.
- Validation: direct tests for tracker behavior, trace schema, raw file naming/hash data, static graph shape, and resume collision prevention.
- Regression guard: keep runtime-owned evidence separate from workflow-declared trace sidecars and do not classify changed files for commits.

### 4. Runner And Engine Binding Integration
- Files: `runtime/runner.py`, `runtime/workspace.py`, `core/engine.py`, `runtime/observability.py`, `runtime/events.py` where needed.
- Add `runtime_extension_factories` support to the engine and bind runtime-owned observability before workflow-declared extensions while preserving tuple order within workflow extensions.
- Refactor runner/workspace preparation so workflow resolution happens first, git preflight happens second, and workspace materialization follows the mandatory ordered sequence for new runs and resumes.
- Add runtime observability binding that assigns/advances sequence numbers, calls git tracker `before_step/after_step/after_run/on_fatal`, and writes runtime tracing without mutating execution state.
- Ignore workflow-declared `extensions.git.GitTracking`, emit the required deprecation warning to `events.jsonl`, and record the warning in `run.json`; keep workflow-declared `Tracing` bound normally.
- Implement resume compatibility handling when prior run metadata and current git-tracking config differ, including the required warning when resuming a previously git-tracked run with tracking now disabled.
- Validation: integration tests for normal run artifact set, run/resume clean-start enforcement, extension ordering/failure behavior, and warning behavior when workflow `GitTracking` is declared.
- Regression guard: retain existing resume semantics, answer flow behavior, and extension failure checkpoint handling.

### 5. Regression Coverage, Docs, And Rollout Safety
- Files: `tests/runtime/test_runtime_git_tracking.py`, `tests/runtime/test_runtime_tracing.py`, existing runtime/provider tests, `tests/test_architecture_baseline_docs.py`, `docs/architecture.md`, `docs/authoring.md`.
- Add the request-mandated runtime git, runtime trace, provider usage, static graph, and end-to-end integration coverage.
- Update existing tests that run outside initialized repositories to explicitly disable git tracking instead of weakening the new runtime defaults.
- Document runtime-owned git tracking/tracing defaults, clean-repo prerequisite, workflow GitTracking deprecation behavior, runtime trace/raw/static graph outputs, and replay boundary expectations.
- Validation: full targeted runtime/doc test pass plus YAML/doc baseline assertions.
- Rollback: git tracking can be disabled immediately with `--no-git` or config if regressions are found after merge; tracing can be disabled with `--no-trace` without backing out provider usage typing.

## Interface Definitions
- `runtime/config.py`
  - `GitCommitPolicy = Literal["off", "run", "step"]`
  - `FailureMode = Literal["raise", "ignore"]`
  - `GitTrackingRuntimeConfig(enabled=True, commit_policy="step", failure_mode="raise")`
  - `TracingRuntimeConfig(enabled=True, path="trace.jsonl", failure_mode="raise", include_state_snapshots=True)`
- `runtime/cli.py`
  - `--no-git`
  - `--git-commit-policy {off,run,step}`
  - `--no-trace`
- `extensions/git/repo.py`
  - `status_porcelain() -> str`
  - `is_dirty() -> bool`
  - `add_all() -> None`
  - `commit_all(message: str) -> tuple[str, bool]`
- `runtime/git_tracking.py`
  - `RuntimeGitTracker.prepare_before_workspace_creation() -> dict[str, object]`
  - `RuntimeGitTracker.bind_run_dir(run_dir: Path) -> None`
  - `RuntimeGitTracker.commit_run_initialized() -> dict[str, object]`
  - `RuntimeGitTracker.before_step(...) -> dict[str, object]`
  - `RuntimeGitTracker.after_step(...) -> dict[str, object]`
  - `RuntimeGitTracker.after_run(...) -> dict[str, object]`
  - `RuntimeGitTracker.on_fatal(...) -> dict[str, object]`
- `runtime/tracing.py`
  - `RuntimeTraceWriter.step_started(...)`
  - `RuntimeTraceWriter.step_finished(...)`
  - `RuntimeTraceWriter.terminal(...)`
  - `RuntimeTraceWriter.fatal(...)`
- `runtime/observability.py`
  - `BoundRuntimeObservability.before_step(...)`
  - `BoundRuntimeObservability.after_step(...)`
  - `BoundRuntimeObservability.on_terminal(...)`
- `core/workflow_capabilities.py` or `runtime/static_graph.py`
  - `workflow_static_step_graph_payload(compiled: CompiledWorkflow) -> dict[str, Any]`

## Compatibility And Migration Notes
- Public compatibility is preserved for existing imports from `extensions/git/*` and `extensions/tracing.py`.
- Workflow packages that declare `GitTracking` continue to import and compile, but runtime ignores the declaration and surfaces a deprecation warning instead of binding duplicate commit behavior.
- Workflow packages that declare `Tracing` continue to emit their sidecar traces; runtime trace becomes the default authoritative evidence file.
- Persisted run data grows with new `git_tracking`, `tracing`, warnings, and static-graph metadata in `run.json`; no backfill is required for older runs.
- Resume may start git tracking mid-run when older runs lacked it, but it must not attempt to reconstruct missing historical commits.
- If an earlier run segment recorded git tracking and the resumed segment disables it, the runtime must persist an explicit warning in `run.json` and continue without git tracking rather than silently changing replay guarantees.

## Resume Compatibility Rules
- Previous segment had git tracking enabled, current resume disables it:
  - Continue the resume without git tracking.
  - Persist a warning in `run.json` explaining that the resumed segment no longer records git commits.
  - Do not alter or backfill previous git-tracking records.
- Previous segment had git tracking disabled, current resume enables it:
  - Start recording git metadata from the resume point only.
  - Do not attempt to backfill earlier commits or retroactively mark earlier steps as tracked.
- Both directions require explicit regression tests for warning persistence, append-only behavior, and preservation of pre-existing evidence.

## Regression Surfaces And Controls
- Workspace creation order: current `ensure_workspace/create_run/open_existing_run` helpers write files eagerly, so runner changes must isolate pure path resolution from materialization to preserve the clean-start invariant.
- Ordered initialization: `run.json`, `static_step_graph.json`, observability file creation, and init commits must occur in the required order so the initial commit captures runtime evidence without the runtime dirtifying the repo before eligibility is checked.
- Extension semantics: runtime extension factories must preserve existing workflow extension tuple order, binding validation, checkpoint-on-failure behavior, and terminal notifications.
- Fatal handling: runtime trace/git fatal writes are best-effort according to failure mode, but the original engine exception must still surface.
- Raw output persistence: sequence assignment must be shared across trace/git/raw so resume cannot collide with existing files even if JSONL has malformed lines.
- Resume config mismatch: prior and current git-tracking settings must be compared explicitly so a resumed run cannot silently lose git replay guarantees or attempt invalid backfill.
- Tests: any test running the filesystem runtime outside a git repo must now opt out explicitly with runtime config or CLI overrides.

## Risk Register
- Risk: runner preflight accidentally creates `.autoloop` artifacts before git cleanliness is checked.
  - Control: split path discovery from file creation and add tests that assert failure occurs before `run.json` or run directories exist.
- Risk: runtime git tracking duplicates or conflicts with workflow-declared git extension commits.
  - Control: filter workflow `GitTracking` before binding and emit one explicit warning event plus `run.json` warning entry.
- Risk: new trace writing changes extension failure behavior or mutates state snapshots.
  - Control: keep runtime observability out of core state, use cloned event/state snapshots already emitted by the engine, and preserve existing contract tests.
- Risk: provider usage extraction becomes provider-specific brittle logic.
  - Control: keep usage optional, map only known fields into `TokenUsage`, and retain raw provider usage payload for unsupported future fields.

## Validation And Rollback
- Validate with targeted runtime/provider/doc tests first, then the broader suite that exercises run/resume and extension behavior.
- Validation must explicitly assert the mandatory new-run and resume ordering, including failure-before-workspace-creation on dirty repos and correct init commit timing.
- Validation must explicitly cover both resume git-tracking config mismatch directions and warning persistence in `run.json`.
- Roll back operationally by disabling runtime git tracking or tracing via config/CLI while preserving the typed provider usage changes if only observability surfaces regress.
- Roll back code changes in reverse dependency order if needed: docs/tests, runtime observability binding, persistence modules, config/CLI/git helpers, provider usage plumbing.
