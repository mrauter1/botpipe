# Compatibility Boundary

## Goal

The core engine stays spec-clean. All legacy and workspace drift is isolated to loading and normalization so existing workflows can run without contaminating the strict runtime model.

## Boundary Placement

- `runtime.loader` handles import-time compatibility.
- `workflow.compat` handles authoring-surface compatibility.
- `runtime.providers` handles loop-control and provider-wire compatibility.
- `runtime.stores.filesystem` handles persisted session or checkpoint compatibility.

## Loader Compatibility

- Load workflow modules through a namespace that prebinds `Event`, `Outcome`, `Verdict`, `ResolvedArtifacts`, `SessionLifecycle`, and other workflow-surface names used in annotations.
- Use postponed evaluation or namespace injection so `Ralph_loop.py` can load even though it annotates with `Verdict` and `Event` without importing them.
- Treat source rewriting as a last-resort fallback. The default path is load-time compatibility with no mutation of user workflow files.

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
- `SessionLifecycle.ON_START` becomes a normalized session-opening policy.
- Step-produced artifacts remain addressable as attributes on the step object and on `ResolvedArtifacts`.
- Pydantic v1 `copy(update=...)` behavior is tolerated during compatibility execution, while strict v3 docs promote `model_copy(update=...)`.

## Persisted State Compatibility

- Session files remain JSON and preserve `session_id` plus legacy `thread_id` fields.
- Checkpoint persistence keeps the strict `Checkpoint` model while readers tolerate legacy session-file fields and missing metadata.
- Resume logic preserves pending question and answer semantics even when resuming runs created before the new engine exists.

## Runtime Behavior That Stays Outside The Core

- `.autoloop` workspace path rules
- request snapshot creation
- decisions header sequence allocation
- raw log formatting
- events JSONL recorder
- config discovery from `autoloop.yaml`, `autoloop.config`, and legacy names
- provider-specific loop-control parsing and retry policy

## Non-Goals

- No compatibility conditionals spread through `engine.py`, `compiler.py`, or `validation.py`.
- No in-place edits to `autoloop/`, `autoloop_v1.py`, or `Ralph_loop.py` unless a future blocker cannot be solved by the loader or compat boundary and is explicitly justified.
- No new workflow examples should be authored against legacy aliases unless a parity test requires them.
