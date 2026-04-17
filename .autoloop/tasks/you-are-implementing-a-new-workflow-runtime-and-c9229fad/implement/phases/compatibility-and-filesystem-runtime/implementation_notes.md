# Implementation Notes

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: implement
- Phase ID: compatibility-and-filesystem-runtime
- Phase Directory Key: compatibility-and-filesystem-runtime
- Phase Title: Compatibility And Filesystem Runtime
- Scope: phase-local producer artifact

## Files Changed

- `autoloop_v3/workflow/__init__.py`
- `autoloop_v3/workflow/compiler.py`
- `autoloop_v3/workflow/compat.py`
- `autoloop_v3/workflow/engine.py`
- `autoloop_v3/runtime/__init__.py`
- `autoloop_v3/runtime/cli.py`
- `autoloop_v3/runtime/config.py`
- `autoloop_v3/runtime/events.py`
- `autoloop_v3/runtime/loader.py`
- `autoloop_v3/runtime/prompts.py`
- `autoloop_v3/runtime/runner.py`
- `autoloop_v3/runtime/workspace.py`
- `autoloop_v3/runtime/stores/__init__.py`
- `autoloop_v3/runtime/stores/filesystem.py`
- `workflow/__init__.py`
- `workflow/primitives.py`
- `autoloop_v3/tests/runtime/test_compatibility_runtime.py`

## Symbols Touched

- Compatibility boundary: `LegacyWorkflow`, `legacy_annotation_globals()`, `normalize_workflow()`.
- Strict compile path: `compile_workflow()` now normalizes legacy workflow classes before validation and caching.
- Runtime loader/harness: `load_workflow_module()`, `load_workflow_class()`, `load_compiled_workflow()`, `RunnerOptions`, `run_workflow()`, `build_arg_parser()`, `_validate_runtime_options()`, `_validate_resume_state()`.
- Filesystem runtime: `TaskWorkspace`, `RunWorkspace`, `ensure_workspace()`, `create_run()`, `open_existing_run()`, `resolve_resume_state_root()`, `FilesystemSessionStore`, `FilesystemCheckpointStore`, `FilesystemPromptRegistry`, `EventLogger`, `append_clarification()`.
- Compatibility shim exports: repo-root `workflow.Workflow`, `workflow.primitives`.

## Checklist Mapping

- `plan.md` milestone 3: implemented isolated legacy normalization for missing `entry`, string topology references, `Verdict` alias support, permissive root imports, and annotation-safe workflow loading.
- `plan.md` milestone 3: implemented filesystem-backed workspace scaffolding, prompt resolution, checkpoint/session stores, raw/events/decisions logging, and resume-state root discovery with `.superloop` fallback.
- `plan.md` milestone 3: implemented a thin runner/CLI harness, explicit validation for unsupported autoloop-specific runtime flags, a targeted legacy-resume compatibility gate, and runtime tests proving `autoloop_v1.py` compiles and executes through the new runtime while `Ralph_loop.py` loads and compiles through the legacy-safe loader.
- Deferred by phase contract: final parity goldens, full Ralph end-to-end execution, and final documentation polish.

## Assumptions

- The repo-root `workflow` shim is compatibility-only; strict workflow authors should continue importing from `autoloop_v3.workflow`.
- Legacy session-file compatibility is required for `plan_session` and `phase_session`; other scoped sessions use a generic `phases/<phase_dir_key>--<ref_name>.json` fallback to avoid collisions.
- The runtime prompt search path must include both the active workspace root and the workflow file’s repository so `autoloop_v1.py` can resolve `templates/...` without source edits.

## Preserved Invariants

- Legacy drift stays isolated in `workflow.compat` and `runtime.loader`; the strict engine still executes only compiled normalized workflows.
- `.autoloop/tasks/{task_id}/runs/{run_id}` remains the primary runtime layout, with append-only run-level `events.jsonl` and raw logs.
- Session bindings remain provider-neutral in the engine; filesystem persistence only adds compatibility serialization for legacy `thread_id` and session-note fields.

## Intended Behavior Changes

- Workspace workflows can now load unchanged through the repo-root `workflow` shim, then normalize into the strict core before compilation.
- The filesystem runtime now creates task/run scaffolding, persists sessions/checkpoints, resolves prompts from disk, and emits raw/event/decisions artifacts.
- Handler-returned state is revalidated before further execution so legacy Pydantic `copy(update=...)` usage cannot leave nested dicts in live engine state.
- The generic v3 runner no longer accepts non-default autoloop-specific pair/phase/git/full-auto flags as silent no-ops; those combinations now fail fast with targeted validation errors.
- Resume without a v3 engine checkpoint but with legacy run artifacts now fails with a targeted migration message instead of the generic missing-checkpoint exception.

## Known Non-Changes

- No final parity matrix updates or documentation polish landed in this phase.
- No external Codex/Claude process adapter is implemented yet; the new runner executes with injected `LLMProvider` implementations and a provider-factory hook.
- No final Ralph Loop golden run was added; this phase proves loader/compiler acceptance for `Ralph_loop.py` and defers full parity execution.
- The generic v3 runner still does not execute old autoloop pair/phase orchestration semantics directly; it now validates and rejects those non-default loop-control options instead of pretending to honor them.

## Expected Side Effects

- Existing workspace workflows importing `workflow` now import successfully under tests, while direct strict imports remain unchanged.
- Fresh runs create both task-level request state and run-scoped immutable request snapshots so legacy workflows with `{task_folder}/request.md` still execute.
- Persisted session files from current `.autoloop` or legacy `.superloop` roots still load for compatibility, but resumes without a v3 checkpoint now stop at an explicit migration boundary rather than falling through to a generic runtime error.

## Validation Performed

- `pytest -q autoloop_v3/tests/runtime/test_compatibility_runtime.py`
- `pytest -q autoloop_v3/tests`
- `python - <<'PY' ... load_workflow_class('autoloop_v1.py') / load_workflow_class('Ralph_loop.py') ... PY`

## Deduplication And Centralization Decisions

- Centralized legacy workflow drift in `workflow.compat` and `runtime.loader` instead of scattering import-time special cases through validation or the engine.
- Centralized filesystem persistence policy in `runtime.workspace` and `runtime.stores.filesystem`; tests target those modules directly rather than duplicating path logic in the runner.
- Centralized append-only observability helpers in `runtime.events` so the runner and later parity work can share the same raw/event/decisions writers.
