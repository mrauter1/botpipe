# Architecture Baseline

## Purpose

This document freezes the implementation shape for the new `autoloop_v3` runtime before core code lands. It is grounded in the spec, `autoloop_v1.py`, `Ralph_loop.py`, `autoloop/src/autoloop/main.py`, and the current `autoloop` tests that define required workspace behavior.

## Legacy Findings That Constrain The Design

- `autoloop_v1.py` already models the target authoring surface: `Workflow`, `Context`, `Session`, `Artifact`, `PairStep`, `SystemStep`, `Verdict`, `ResolvedArtifacts`, `on_verdict`, workflow-level artifacts, produced-artifact attribute access such as `plan.phase_plan`, and phase-scoped session opening inside a system handler.
- `Ralph_loop.py` adds compatibility drift that must remain outside the strict core: `SessionLifecycle.ON_START`, missing `Verdict` and `Event` imports in annotations, LLM-only steps, `on_execute(state)` system-handler arity drift, and Pydantic v1-style `copy(update=...)`.
- `autoloop/src/autoloop/main.py` and the legacy tests define the runtime parity surface: `.autoloop/tasks/{task_id}/runs/{run_id}` layout, immutable request snapshots, task-level and run-level raw logs, append-only decisions ledger, events log driven resume, explicit phase plans, implicit single-phase fallback, phase-local artifacts, phase-scoped sessions, clarification persistence, config discovery, and provider-neutral session state with `thread_id` compatibility.

## Frozen Module Layout

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
      protocols.py
      models.py
    stores/
      __init__.py
      protocols.py
      memory.py
  runtime/
    __init__.py
    loader.py
    config.py
    workspace.py
    logging.py
    runner.py
    cli.py
    providers/
      __init__.py
      codex.py
      claude.py
      fake.py
    stores/
      __init__.py
      filesystem.py
  tests/
    unit/
    contract/
    integration/
    golden/
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

## Layer Boundaries

- `autoloop_v3.workflow` is the strict spec-compliant core. It owns primitives, authoring types, definition-time validation, compilation, routing, and step execution semantics.
- `autoloop_v3.runtime` owns workspace-specific concerns: module loading, filesystem stores, provider adapters, config resolution, CLI wiring, request snapshotting, decisions and raw log writers, and parity with the current `.autoloop` layout.
- `autoloop_v3.workflow.compat` is the only compatibility boundary. It normalizes legacy workflow definitions before strict compilation and is the only place allowed to understand `Verdict`, `on_verdict`, legacy handler arities, `SessionLifecycle`, Pydantic copy drift, and other workspace-specific authoring quirks.
- The repo-root `workflow/` package is a thin re-export shim for import ergonomics only. It must not contain engine logic, runtime logic, or compatibility policy.

## Execution Pipeline

1. `runtime.loader` loads a workflow module through a legacy-safe namespace that tolerates unresolved legacy annotation names.
2. `workflow.compat` normalizes the loaded workflow class into the strict v1.1 authoring model.
3. `workflow.validation` validates the normalized workflow definition at class-definition or load time.
4. `workflow.compiler` compiles the normalized definition into an immutable `CompiledWorkflow` containing steps, routes, artifact registry, handler adapters, and session slots.
5. `workflow.engine` executes compiled steps deterministically against `Context`, `ResolvedArtifacts`, provider calls, and store interfaces.
6. `runtime.runner` binds filesystem stores, provider adapters, workspace paths, request snapshots, resume inputs, and event or raw log sinks to the engine.

## Public Surface To Preserve

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

Compatibility aliases remain supported for loading existing workspace workflows, but new v3 authoring should target `Outcome` and strict handler signatures.

## Core Invariants

- State is immutable. Handlers return a new state, using `model_copy(update=...)` semantics in the strict API.
- Session bindings are external runtime data, not embedded in workflow state.
- Routing is deterministic: step-local transition first, then `GLOBAL`, else a runtime error.
- Artifacts resolve from a compiled registry, not from ad hoc string concatenation at step runtime.
- Missing artifact-template keys resolve to an empty string.
- Checkpoints are snapshots of engine state plus session bindings, with append-only events retained separately for parity and observability.
- Compatibility normalization happens exactly once before compilation.

## Concrete Compatibility Scope

- `Verdict` aliases `Outcome`.
- `on_verdict` aliases `on_outcome`.
- Pair and LLM step handlers accept strict and legacy arities.
- System step handlers accept strict `(state, ctx)` and legacy `(state)` arities via adapters.
- `SessionLifecycle.ON_START` maps to runtime session opening policy without leaking lifecycle enums into the core executor.
- Pydantic v1 `copy(update=...)` usage is tolerated through loader or adapter policy, but strict state updates in v3 code use `model_copy(update=...)`.
- Produced artifacts remain addressable as attributes on their owner step and on `ResolvedArtifacts`.
- Direct imports that fail because legacy modules reference undeclared names in annotations are handled by the loader, not by mutating the core.

## Implementation Sequence For The Next Phases

1. Build the strict authoring types, error model, definition-time validator, and compiler.
2. Implement in-memory provider and store protocols plus the deterministic executor.
3. Implement compatibility normalization and handler adapters.
4. Implement filesystem stores, workspace layout, event and raw log sinks, loader, config, and CLI harness.
5. Add parity and golden coverage against `autoloop_v1.py`, `Ralph_loop.py`, and critical legacy runtime scenarios.

## Related Documents

- [parity-matrix.md](parity-matrix.md)
- [compatibility.md](compatibility.md)
- [authoring.md](authoring.md)
- [risk-register.md](risk-register.md)
- `docs/adr/*`
