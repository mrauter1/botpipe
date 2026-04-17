# Compatibility Boundary

## Goal

Keep the engine spec-clean while allowing the existing workspace workflows and persisted runtime data to execute without invasive source edits.

## Boundary Placement

- `runtime.loader` handles import-time compatibility.
- `workflow.compat` handles authoring-surface compatibility.
- `runtime.stores.filesystem` handles persisted session and checkpoint compatibility.
- `runtime.runner.load_provider_factory` delegates provider-wire behavior to injected provider modules instead of hardcoding provider-specific logic into the package.

## Loader Compatibility

- Workflow modules load through a namespace that prebinds `Event`, `Outcome`, `Verdict`, `ResolvedArtifacts`, `SessionLifecycle`, and related authoring symbols used in annotations.
- This allows `Ralph_loop.py` to load even though it annotates with `Verdict` and `Event` without importing them.
- The default strategy is namespace injection, not source rewriting.

## Authoring Compatibility

- `Verdict` remains a public alias of `Outcome`.
- `on_verdict` maps to the strict `on_outcome` middleware hook.
- Pair and LLM handlers accept:
  - `(state, outcome, artifacts)`
  - `(state, outcome)`
  - `(state, verdict, artifacts)`
  - `(state, verdict)`
- System handlers accept:
  - `(state, ctx)`
  - `(state)` for legacy workflows such as `Ralph_loop.py`
- `SessionLifecycle.ON_START` normalizes to runtime session-opening policy.
- Produced artifacts remain addressable as attributes on the step object and on `ResolvedArtifacts`.
- Legacy Pydantic `copy(update=...)` usage is tolerated during compatibility execution, while strict v3 authoring uses `model_copy(update=...)`.

## Persisted State Compatibility

- Session files stay JSON and preserve `session_id` plus legacy `thread_id` fields.
- Existing provider metadata, clarification notes, and timestamps are merged forward during sparse writes.
- Checkpoints use the strict `Checkpoint` schema while tolerating legacy session payload shapes on load.

## Runtime Compatibility Scope

The runtime preserves the compatibility surface that target workflows actually need:

- `.autoloop` workspace layout
- request snapshots
- task and run raw logs
- append-only decisions headers and clarification entries
- events JSONL lifecycle logs
- phase-local artifact directories
- phase-scoped sessions
- prompt-path resolution against the workspace and legacy template roots
- config discovery from `autoloop.yaml`, `autoloop.config`, and legacy config filenames

## Explicit Operational Limits

These limits are intentional and tested so the generic runner fails clearly instead of drifting silently:

- `autoloop_v3.runtime.cli` resumes only runs that already have `checkpoint.json`.
- Resuming legacy runs that only contain session files or events stays a legacy-runtime responsibility.
- Non-default pair, phase, git, and full-auto runtime flags are rejected by the generic runner.
- Provider-specific loop-control parsing and retry policy stay in the injected provider factory or the legacy runtime.

## Non-Goals

- No compatibility conditionals spread through `engine.py`, `compiler.py`, or `validation.py`.
- No in-place edits to `autoloop/`, `autoloop_v1.py`, or `Ralph_loop.py`.
- No hidden provider adapters inside `autoloop_v3.runtime`; provider wiring is explicit at the runner boundary.
- No new workflow examples should default to legacy aliases unless a parity test requires them.
