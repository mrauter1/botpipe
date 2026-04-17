# Architecture

The final shape aims at the Book Architecture for this codebase: one strict core, one generic runtime, and one workflow-owned parity layer.

## Shape

The shipped architecture has three sharp boundaries:

- `autoloop_v3.workflow`: strict primitives, authoring types, validation, compilation, engine, provider/store protocols.
- `autoloop_v3.runtime`: workflow-agnostic filesystem runtime for `.autoloop/tasks/{task_id}/runs/{run_id}`, request snapshots, events, checkpoints, prompt resolution, and generic session persistence.
- `autoloop_v3.workflows`: workflow-owned helpers and harnesses. `autoloop_v1` parity lives here, not in the runtime core.

There is no compatibility layer and no generic workspace-hook system. The repo-root `workflow/` package is a strict re-export only. It does not normalize workflows, inject names, or map to a legacy base class.

## Canonical Surface

`workflow` exports:

- `Workflow`
- `Context`
- `Session`
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
- `Checkpoint`
- `ResolvedArtifacts`

## Execution Model

1. `runtime.loader` imports the workflow module without mutating globals.
2. `workflow.validation` validates the declared workflow definition at class-definition time.
3. `workflow.compiler` compiles the workflow into immutable steps, routes, artifacts, and middleware.
4. `workflow.engine` runs deterministically against explicit `Context`, resolved artifacts, provider calls, sessions, and checkpoints.
5. `workflow.observers` receives provider-turn, step-completed, and terminal facts through one minimal output-only seam.
6. `runtime.events` appends `events.jsonl`.
7. Workflow-owned harnesses may interpret the observer stream to add policy-specific side effects, such as Autoloop-v1 raw logs or decisions ledgers.

The architecture is closer to the Book Architecture precisely because the explanation is short and complete: the core emits generic execution facts, the runtime persists generic filesystem state, and the parity layer alone interprets legacy Autoloop-v1 meaning.

## Session Model

Sessions are not computed. They are created.

- Declare slots as `Session`.
- Open them explicitly with `ctx.open_session(slot, scope=...)`.
- Rebinding is visible at the workflow level.
- Step execution performs direct lookup only.

If a step requires a session that was never opened, execution fails with a runtime error naming the missing slot and step.

## Runtime Boundary

The generic runtime owns only:

- task/run workspace roots
- immutable request snapshots
- `events.jsonl`
- `checkpoint.json`
- generic session persistence
- prompt lookup
- CLI/config for workflow-agnostic controls

The generic runtime does not own:

- phases
- plan / implement / test orchestration
- Autoloop-specific artifact names
- Autoloop-specific session filename rules
- clarification ledgers
- raw phase logs
- workflow-specific git policy
- workspace plugin systems or phase hooks

## Configuration

The runtime keeps only generic configuration:

- provider selection and provider-specific settings
- runtime controls such as `max_steps` and `intent_mode`
- config-file discovery for `autoloop.*` plus legacy `superloop.*` filenames

Configuration is not used to encode workflow topology, phase plans, raw-log policy, or session-opening rules.

## Autoloop-v1 Parity

`autoloop_v1.py` remains a strict workflow. It owns its phase-plan parsing and explicit phase artifact templates directly.

Its legacy-equivalent operational behavior is split across two workflow-owned modules:

- `autoloop_v3.workflows.autoloop_v1_conventions`
  - exact `phase_dir_key(...)`
  - `sessions/plan.json`
  - `sessions/phases/{phase}.json`
- `autoloop_v3.workflows.autoloop_v1_parity`
  - thin `run_autoloop_v1(...)` composition root
  - task/run `raw_phase_log.md`
  - task `decisions.txt`
  - clarification note persistence in the active session file
  - question / blocked / failed event-status mapping
  - phase-started and phase-completed event synthesis from generic observer events

This keeps the engine and runtime generic while preserving Autoloop-v1 behavior where it actually belongs: next to the workflow that needs it.
