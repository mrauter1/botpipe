# Workflow Runtime v3 Plan

## Scope And Non-Negotiables

- Create the new implementation as a new package directory at `autoloop_v3/` inside the repo root (`/home/rauter/autoloop_v3/autoloop_v3/`).
- Keep the existing `autoloop/` codebase intact as a read-only behavioral oracle and parity target.
- Ship the full Workflow Definition Specification v1.1 core, isolated compatibility layer, filesystem runtime, runner/CLI harness, ADRs, docs, and comprehensive tests.
- Preserve required workspace behavior under `.autoloop/tasks/{task_id}/runs/{run_id}` with no regressions for the required scenarios.

## Workspace Findings That Drive The Plan

- `autoloop_v1.py` already expresses the target orchestration shape and depends on a `workflow` authoring package, `workflow.primitives`, step-produced artifact attribute access such as `plan.phase_plan`, `Verdict`, `ResolvedArtifacts`, `on_verdict`, scoped sessions, and phase-local artifacts.
- `Ralph_loop.py` adds real compatibility drift that must be handled outside the strict core: `SessionLifecycle.ON_START`, legacy `Verdict` naming, handler arity drift (`on_execute(state)` instead of `(state, ctx)`), and Pydantic `copy(update=...)` usage.
- `autoloop/src/autoloop/main.py` is the parity oracle for workspace/task/run layout, phase-plan scaffold and validation, implicit single-phase fallback, plan/phase session file layout, raw logs, events log, decisions/clarification ledger, loop-control retry behavior, phase-local scoping, resume bookkeeping, and provider-neutral session persistence.

## Target Implementation Shape

- `autoloop_v3/workflow/`
  - `primitives.py`: `Event`, `Outcome`, `Checkpoint`, terminal sentinels, compatibility `Verdict`.
  - `artifacts.py`: `Artifact`, `ArtifactHandle`, `ResolvedArtifacts`, compiled artifact registry, template resolution.
  - `steps.py`: `Step`, `PairStep`, `LLMStep`, `SystemStep`, `Session`, compatibility `SessionLifecycle`.
  - `prompts.py`: `Prompt`, prompt loader, optional `PromptRegistry`.
  - `context.py`: immutable context surface with session binding access and answer injection.
  - `validation.py`: definition-time validator and explicit error model.
  - `compat.py`: legacy workflow normalization, handler/signature adapters, alias support.
  - `compiler.py`: normalized workflow to compiled graph, artifact registry, session registry, handler table.
  - `engine.py`: deterministic executor, routing, pause/resume, best-effort checkpoint-on-failure hooks.
  - `providers/`: provider protocol plus outcome/parser adapters.
  - `stores/`: protocol definitions and in-memory test doubles.
- `autoloop_v3/runtime/`
  - `workspace.py`: `.autoloop` path policy, task/run scaffolding, phase selection persistence, phase dir key rules.
  - `stores/`: filesystem `CheckpointStore`, `SessionStore`, and artifact access.
  - `providers/`: provider adapters and loop-control compatibility interpreters needed by workspace workflows.
  - `events.py` or equivalent: append-only raw/event/decisions writers.
  - `runner.py` and `cli.py`: runnable harness for workflow modules/classes.
- `autoloop_v3/docs/`
  - `adr/`: one ADR per required material decision, each with exactly 3 candidates and the required evaluation fields.
  - `architecture.md`, `parity-matrix.md`, `compatibility.md`, `authoring.md`.
- If import ergonomics require it, add a repo-root `workflow/` shim package that only re-exports from `autoloop_v3.workflow` and contains no engine logic.

## Public Interfaces To Freeze Early

- Authoring surface exported by `workflow`:
  - `Workflow`, `Context`, `Session`, `SessionLifecycle`
  - `Artifact`, `Prompt`
  - `PairStep`, `LLMStep`, `SystemStep`
  - `SUCCESS`, `PAUSE`, `FAIL`, `GLOBAL`
- `workflow.primitives` must export:
  - `Event`, `Outcome`, `Verdict`, `Checkpoint`, `ResolvedArtifacts`
- Compiler/runtime surface:
  - load workflow class/module
  - normalize legacy workflow definitions before strict compilation
  - run with workspace root, task/run ids, provider binding, resume flag, optional answer injection, and optional phase targeting overrides
- Provider/store contracts:
  - provider interface must support raw producer turns, outcome-producing verifier/LLM turns, and provider-neutral session ids
  - checkpoint/session/artifact stores must be swappable with deterministic in-memory fakes and filesystem defaults

## Required ADR Backlog

- Package/module layout
- Workflow compilation model
- Topology/routing representation
- Artifact registry and resolution
- Checkpoint persistence model
- Session binding model
- Provider protocol design
- Compatibility strategy for legacy/workspace drift
- Handler dispatch and signature adaptation
- Resume/answer injection mechanism
- Validation architecture
- Event/logging model
- CLI/runtime harness layout
- Testing strategy

## Ordered Milestones

### 1. Architecture Baseline And ADRs

- Build the feature-parity inventory and risk list from `autoloop_v1.py`, `Ralph_loop.py`, and legacy `autoloop.main`.
- Write the required ADR set before core implementation settles material design choices.
- Freeze the package layout, public interfaces, and compat boundary in docs.

### 2. Strict v1.1 Core

- Implement spec-compliant primitives, steps, artifacts, prompts, context, validation, compiler, engine, and in-memory stores/fakes.
- Keep the core free of workspace-specific conditionals; all drift handling stays outside the compiled strict model.
- Add unit and contract tests for routing, artifact resolution, lifecycle hooks, checkpointing, pause/resume, answer injection, and validation failures.

### 3. Compatibility Layer And Filesystem Runtime

- Implement legacy normalization/adapters for `Verdict`, `on_verdict`, handler arities, `SessionLifecycle`, step constructor drift, and any other workflow-local compatibility gaps discovered in the target workflows.
- Implement filesystem-backed stores, `.autoloop` workspace scaffolding, event/raw/decisions logging, phase selection persistence, scoped sessions, and prompt resolution.
- Add the runnable harness and any thin import/package shims needed to execute the target workflows without editing them.

### 4. Workflow Integration And Parity Proof

- Execute `autoloop_v1.py` and `Ralph_loop.py` end-to-end with deterministic fake providers.
- Add golden tests for task/run layout, phase activation, implicit/explicit phase handling, scoped artifacts/sessions, clarifications, pause/resume, and failure paths.
- Add parity comparisons against critical legacy `autoloop` behavior for raw logs, events, decisions ledger, session persistence, and workspace paths.

### 5. Hardening, Docs, And Final Validation

- Finish `architecture.md`, `parity-matrix.md`, `compatibility.md`, and `authoring.md`.
- Add filesystem integration tests and CLI smoke coverage.
- Close or explicitly document any remaining risk that could affect correctness, compatibility, or long-term maintainability.

## Compatibility And Parity Matrix

- `workflow` import ergonomics: preserve via a thin compatibility shim if necessary; real logic stays in `autoloop_v3/`.
- Workspace layout: preserve `.autoloop/tasks/{task_id}/plan`, `.autoloop/tasks/{task_id}/{pair}/phases/{phase-dir-key}`, and `.autoloop/tasks/{task_id}/runs/{run_id}` structure.
- Immutable request snapshot: write once per run and use as the primary request source for runtime prompts/resume.
- Phase plan behavior: support authored `phase_plan.yaml` plus implicit single-phase fallback when no explicit plan exists.
- Artifact scoping: task-global for plan artifacts, phase-local for implement/test, with dot-notation template resolution and missing-key-to-empty behavior.
- Sessions: provider-neutral session ids with scoped bindings; legacy Codex `thread_id` compatibility remains isolated in runtime/session serialization.
- Clarifications and pause/resume: explicit pending question/answer persisted through checkpoints and session bindings.
- Loop-control behavior: canonical and legacy parsing/retry stays in runtime/provider adapters, not in the clean engine core.
- Events and raw logs: append-only task-level and run-level logs plus event recorder parity for resumed runs and phase transitions.

## Regression Risks And Controls

- Import-surface mismatch
  - Control: create import smoke tests for `workflow`, `workflow.primitives`, `autoloop_v1.py`, and `Ralph_loop.py` before end-to-end execution.
- Legacy drift contaminating the core
  - Control: normalize once in `compat.py`, compile only normalized objects, and add dedicated compatibility tests.
- Resume semantics diverging from the legacy runtime
  - Control: define an explicit checkpoint schema, keep session/answer persistence deterministic, and compare resumed-path behavior with legacy artifacts/events for critical scenarios.
- Artifact/session path regressions
  - Control: golden path tests for `phase_dir_key`, task/run layout, produced-artifact lookup, scoped session files, and phase-local artifact directories.
- Logging/ledger regressions
  - Control: fixture-based tests for raw logs, events log, decisions headers, clarification writes, and append-only behavior.

## Rollback And Safety Constraints

- Do not migrate or rewrite the legacy `autoloop/` package in place.
- Keep any root-level compatibility shim minimal enough to delete or adjust without touching the new engine.
- If a compatibility behavior cannot be proven by tests, keep the old runtime as the oracle and treat the gap as blocking rather than silently narrowing support.
