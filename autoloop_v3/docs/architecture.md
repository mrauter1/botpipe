# Architecture

## Purpose

This document records the shipped architecture for `autoloop_v3`. It is grounded in the Workflow Definition Specification v1.1, the target workflows in `autoloop_v1.py` and `Ralph_loop.py`, and the legacy runtime behavior in `autoloop/src/autoloop/main.py`.

## Legacy Findings That Constrain The Design

- `autoloop_v1.py` depends on the `workflow` authoring surface, `Verdict`, `on_verdict`, workflow-level artifacts, produced-artifact attribute access such as `plan.phase_plan`, and phase-scoped sessions opened from a system handler.
- `Ralph_loop.py` adds load-time and handler-shape drift: missing `Verdict` and `Event` imports in annotations, `SessionLifecycle.ON_START`, `on_execute(state)` arity drift, and Pydantic v1-style `copy(update=...)`.
- The legacy runtime defines the parity surface outside the core engine: `.autoloop/tasks/{task_id}/runs/{run_id}` layout, immutable request snapshots, task and run raw logs, append-only decisions headers, events-driven resume bookkeeping, phase-plan selection, phase-local artifacts, phase-scoped sessions, and legacy `thread_id` session payloads.

## Shipped Module Layout

```text
autoloop_v3/
  workflow/
    __init__.py
    primitives.py
    prompts.py
    artifacts.py
    steps.py
    context.py
    errors.py
    validation.py
    compat.py
    compiler.py
    engine.py
    providers/
      __init__.py
      models.py
      protocols.py
      fake.py
    stores/
      __init__.py
      protocols.py
      memory.py
  runtime/
    __init__.py
    cli.py
    config.py
    events.py
    loader.py
    prompts.py
    runner.py
    workspace.py
    stores/
      __init__.py
      filesystem.py
  tests/
    test_architecture_baseline_docs.py
    unit/
    contract/
    runtime/
  docs/
    adr/
    architecture.md
    parity-matrix.md
    compatibility.md
    authoring.md
    risk-register.md
workflow/
  __init__.py
  primitives.py
```

The repo-root `workflow/` package is intentionally a thin compatibility shim. It re-exports the strict core surface and maps legacy workflow classes to `LegacyWorkflow`; it does not own execution or filesystem logic.

## Layer Boundaries

- `autoloop_v3.workflow` is the strict engine layer. It owns primitives, authoring types, definition-time validation, compilation, routing, and step execution semantics.
- `autoloop_v3.workflow.compat` is the only authoring compatibility boundary. It normalizes legacy workflows before strict compilation.
- `autoloop_v3.runtime` owns workspace-specific behavior: legacy-safe module loading, prompt-path resolution, filesystem stores, `.autoloop` layout, config discovery, event and ledger writing, and the generic CLI runner.
- Provider integrations stay outside the engine core. The generic runtime loads a provider factory from `module:function` via `runtime.runner.load_provider_factory`, and the returned object must satisfy the `LLMProvider` protocol.

## Execution Pipeline

1. `runtime.loader` loads a workflow module with compatibility globals injected for legacy annotations.
2. `workflow.compat` normalizes the loaded workflow class into the strict v1.1 authoring model.
3. `workflow.validation` validates the normalized workflow definition.
4. `workflow.compiler` compiles the definition into an immutable `CompiledWorkflow`.
5. `runtime.runner` prepares the workspace, request snapshot, filesystem stores, prompt registry, and event logger.
6. `workflow.engine` executes the compiled workflow deterministically against `Context`, `ResolvedArtifacts`, the provider, and the stores.
7. `runtime.events` appends run lifecycle events, clarification ledger entries, and raw-log records needed for parity and observability.

## Public Surface

`workflow` exports:

- `Workflow`
- `Context`
- `Session`
- `SessionLifecycle`
- `Artifact`
- `Prompt`
- `PairStep`
- `LLMStep`
- `SystemStep`
- `SUCCESS`
- `PAUSE`
- `FAIL`
- `GLOBAL`

`workflow.primitives` exports:

- `Event`
- `Outcome`
- `Verdict`
- `Checkpoint`
- `ResolvedArtifacts`

New workflows should target `Outcome`, `on_outcome`, and strict handler signatures. Legacy aliases remain supported only through the compatibility boundary.

## Core Invariants

- State is immutable. Handlers return a new state, and the engine revalidates returned state before continuing.
- Session bindings live in stores, not in workflow state.
- Routing is deterministic: step-local transition first, then `GLOBAL`, else a runtime error.
- Artifacts resolve through the compiled registry. Missing template keys resolve to `""`.
- Checkpoints are typed snapshots of stage, state, session bindings, and pending question or answer fields.
- Compatibility normalization happens once before compilation; the core executor does not branch on legacy workflow drift.

## Runtime Compatibility Boundary

- `runtime.loader` handles import-time issues such as missing annotation imports in `Ralph_loop.py`.
- `workflow.compat` handles `Verdict`, `on_verdict`, handler arity drift, `SessionLifecycle`, and produced-artifact attribute access.
- `runtime.stores.filesystem` handles session payload compatibility, including promotion of legacy `thread_id` fields to `session_id`.
- `runtime.events` owns append-only raw, event, and decisions logging for v3 runs.

## Generic Runner Limits

The shipped `autoloop_v3.runtime.cli` is intentionally a generic workflow runner, not a full clone of the legacy pair or phase orchestrator.

- It supports fresh execution and checkpoint-based resume for v3 runs.
- It rejects non-default pair, phase, git, and full-auto compatibility flags instead of silently ignoring them.
- It does not reconstruct legacy event-only or session-only runs into v3 checkpoints; those resumes stay on the legacy `autoloop` harness.
- Provider-specific loop-control parsing and retry policy stay in the injected provider factory or in the legacy runtime, not in `engine.py`.

## Validation And Proof

- `autoloop_v3/tests/unit/` covers primitives, stores, artifact resolution, and validation failures.
- `autoloop_v3/tests/contract/` covers engine semantics for pair, llm, system, lifecycle, routing, pause, resume, and failure paths.
- `autoloop_v3/tests/runtime/` proves workspace parity, compatibility shims, filesystem behavior, `autoloop_v1.py`, `Ralph_loop.py`, and CLI/runtime smoke execution.

## Related Documents

- [parity-matrix.md](parity-matrix.md)
- [compatibility.md](compatibility.md)
- [authoring.md](authoring.md)
- [risk-register.md](risk-register.md)
- `docs/adr/*`
