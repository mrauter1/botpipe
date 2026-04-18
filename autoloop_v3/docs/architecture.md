# Architecture

`autoloop_v3` targets the final Book Architecture for this codebase:

- smallest correct kernel
- sharp boundaries
- explicit semantics
- deterministic behavior
- optional extensions for orthogonal concerns
- workflow-owned policy for workflow meaning

## Package Shape

```text
autoloop_v3/
  workflow/
  runtime/
  stdlib/
  extensions/
  workflows/
```

Each package has one job:

- `workflow`: strict kernel, canonical authoring surface, validation, compilation, engine, provider/store protocols, and the minimal extension seam.
- `runtime`: workflow-agnostic filesystem runtime for workspace creation, request snapshots, `events.jsonl`, checkpoints, prompt loading, config, CLI, and generic session persistence.
- `stdlib`: tiny pure authoring sugar that compiles down to kernel primitives.
- `extensions`: tiny optional cross-cutting modules such as tracing, session-path strategy, and git tracking.
- `workflows`: workflow-owned parity helpers and conventions only.

There is no compatibility layer, no hidden normalization boundary, and no generic workspace hook system.

## Placement Rule

Use one placement rule everywhere:

- If a behavior is an invariant almost every workflow needs, make it seamless by default.
- If it is an orthogonal operational concern whose behavior varies, make it policy-configured.
- If it changes workflow meaning, topology, or semantic state, keep it explicit in workflow code.

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

The strict root authoring surface does not include `Engine`, `compile_workflow`, compatibility aliases, or authoring shims.

## Execution Model

The final execution model is singular:

1. `runtime.loader` imports the workflow module without mutating globals.
2. `workflow.validation` enforces the strict shape at definition time.
3. `workflow.compiler` produces an immutable compiled workflow model.
4. `runtime.runner` creates the generic workspace and binds `Workflow.extensions` for the run.
5. `workflow.engine` executes deterministically against explicit sessions, resolved artifacts, provider calls, and typed checkpoints.
6. `runtime.events` appends generic `events.jsonl`.
7. Workflow-owned parity code or optional extensions may add side effects beside the core artifacts.

There is one kernel execution model only. Extensions may observe step boundaries and run side effects, but they may not mutate workflow state, routing, or kernel semantics.

## Extension Seam

The kernel exposes exactly one extension concept:

- `Workflow.extensions: tuple[WorkflowExtension, ...] = ()`

The minimal seam is built around:

- `RunBinding`
- `StepStart`
- `StepFinish`
- `TerminalFinish`
- `WorkflowExtension`
- `BoundWorkflowExtension`

This seam exists for optional orthogonal behavior only. It is the place for:

- `Tracing(...)`
- `SessionPaths(...)`
- `GitTracking(...)`

It is not an event bus, not a plugin platform, and not a second workflow language.

## Runtime Boundary

The generic runtime owns only:

- `.autoloop/tasks/{task_id}/runs/{run_id}`
- immutable `request.md`
- generic `events.jsonl`
- typed checkpoint persistence
- generic filesystem session persistence
- prompt resolution
- generic config and CLI

Generic config stays small and typed. Typical controls include `max_steps`, `intent_mode`, provider settings, and extension config.

The generic runtime must not own:

- phases
- plan / implement / test semantics
- Autoloop-v1 artifact names
- raw phase log format
- decisions ledger schema
- review / rework / replan semantics
- workflow-specific git policy

## Stdlib Boundary

`autoloop_v3.stdlib` remains tiny and pure. It may offer:

- `global_routes(...)`
- `merge_transitions(...)`
- `pause_on_outcome_tags(...)`
- `PromptBundle`
- `PromptPair`
- `pair_step(...)`
- `SequenceCursor`

It must not introduce base classes, mixins, decorators that rewrite topology, or config-driven workflow behavior.

## Workflow-Owned Parity

Autoloop-v1 parity is preserved without polluting the core:

- `autoloop_v1.py` stays explicit and readable.
- `autoloop_v3.workflows.autoloop_v1_conventions` owns exact naming such as `sessions/plan.json` and `sessions/phases/{phase}.json`.
- `autoloop_v3.workflows.autoloop_v1_parity` owns `run_autoloop_v1(...)`, `raw_phase_log.md`, `decisions.txt`, clarification persistence, and question / blocked / failed status mapping.

That split keeps the runtime generic while preserving exact legacy behavior where it belongs: with the workflow that needs it.
