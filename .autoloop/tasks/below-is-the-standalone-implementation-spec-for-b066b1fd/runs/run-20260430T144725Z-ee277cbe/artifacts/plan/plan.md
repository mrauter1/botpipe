# Autoloop Implementation Plan

## Objective
Implement the standalone spec without drifting from the current direction. Preserve the canonical simple authoring surface around `produce_verify_step`, move the codebase to one internal import path (`core...`), and add runtime-owned state, scoped state, hook rerouting, effective required writes, and read-only history/telemetry with regression coverage.

## Current Repo Findings
- The compatibility bridge is still live in root [`__init__.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/__init__.py) and [`autoloop_v3/core/__init__.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop_v3/core/__init__.py), backed by [`core/_compat.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/_compat.py).
- Production code still imports `autoloop_v3.core...` in `autoloop/simple.py`, `runtime/*`, and `extensions/*`; strictness currently assumes the bridge exists.
- The engine already checkpoints workflow state, `step_states`, `item_states`, `step_item_states`, worklist selections, pending handoffs, and failure context, but step visit/last-route bookkeeping still lives outside persisted state.
- Runtime hooks emit `hook_started` / `hook_finished` / `hook_failed`, but `_run_after_hook()` and `_normalize_after_hook_result()` still reject route redirects in [`core/engine.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py).
- Simple step state currently accepts only explicit `BaseModel` classes; prompt validation still rejects `item.state.*` and `step.item_state.*`; public exports do not yet reintroduce `StateVar`.
- Effective route required writes are only partially represented today: runtime enforces explicit empty overrides correctly, but provider contracts and topology/static graph outputs still render only `route.required_writes`.

## Milestones

### 1. Compatibility Bridge Removal
- Update production imports in `autoloop/`, `runtime/`, and `extensions/` to `core...` only.
- Remove the root bridge call, delete `autoloop_v3/core/__init__.py`, and delete `core/_compat.py` once no production import depends on it.
- Update strictness and import tests so `import autoloop_v3.core` fails intentionally and production files no longer reference `autoloop_v3.core` or `core._compat`.
- Keep `autoloop`, `core`, and `runtime` package behavior otherwise unchanged.

### 2. Hook Rerouting And Chaining
- Change after-hook normalization so hooks may return `None`, route-tag `str`, or `Event`, with validation against the current step’s declared routes.
- Replace the one-pass route-finalization flow with a redirect loop that re-runs step `on_route` and route `on_taken` hooks after each legal redirect, capped at `max_hook_redirects = 16`.
- Treat unknown hook routes as workflow/runtime errors, not provider-attributable errors.
- Extend trace/event emission with `hook_route_redirected` and record candidate route, final route, and redirect chain in step-finish data.

### 3. State Surfaces And `StateVar`
- Keep workflow `State` and `Params` Pydantic-based; continue rejecting `Parameters`.
- Add built-in runtime step models:
  - `StepRuntimeState(visits, last_route, last_reason)`
  - `ProduceVerifyRuntimeState(..., rework_count, replan_count)`
- Merge built-ins and custom step state onto one surface via `ctx.step_state`, with compile-time reserved-name validation.
- Reintroduce public `StateVar` only as inline step-state sugar that compiles to generated Pydantic models, including explicit handling for ambiguous `None` and mutable defaults.
- Persist built-in state in checkpoints and remove separate `step_visits` / `step_last_routes` bookkeeping from the engine.

### 4. Item State And Step-Item State
- Extend `Worklist` authoring and compilation so `Worklist.from_param(..., item_state=...)` declares shared per-item state.
- Extend scoped simple/core steps with step-level aggregate state plus per-item `item_state` for the current step/item pair.
- Expose `ctx.item_state` and `ctx.step_item_state` only when the backing models exist; otherwise fail clearly.
- Allow prompt placeholders for `{item.state.field}` and `{step_name.item_state.field}` with Pydantic-backed field validation and reserved-name checks.
- Keep storage keys stable and explicit: run id + worklist/item identity for item state, and run id + step + worklist/item identity for step-item state.

### 5. Effective Required Writes
- Preserve `required_writes=None` as “inherit artifact-level required writes” and `required_writes=[]` as “no required writes”.
- Compute effective required writes once in compiled/runtime helpers and use the same helper for provider contracts, topology/static graph artifacts, and final route validation.
- Extend topology outputs to include both explicit route required writes and effective route required writes so harnesses and docs reflect actual enforcement.

### 6. History And Telemetry
- Add a read-only history reader module on the canonical side (`core/history.py`) and expose it as `ctx.history`.
- Derive telemetry from `trace.jsonl`, `events.jsonl`, and checkpoint failure context without checkpointing large mutable telemetry blobs.
- Add stable step execution ids, scoped step identity fields, provider attempt events, hook redirect events, and structured artifact-validation events needed for exact telemetry.
- Support partial history when `trace.jsonl` is missing; cache file reads by path/size/mtime to avoid repeated full rereads in normal usage.

## Interface And Contract Changes

### Public API
- `autoloop.__all__` must include `StateVar` and continue to include only the canonical names from the spec.
- Removed names remain absent: `SUCCESS`, `review_step`, `do_review_step`, `system_step`, `StrictWorkflow`, `RouteInfo`, `chain`, `Param`, old `out` / `outputs`, and public `produces`.

### Canonical Imports
- Production source imports after phase 1 must use `core...` or `autoloop...` only.
- `autoloop_v3.core` becomes an intentional hard failure and strictness tests must enforce that break.

### Runtime State Models
- Every compiled step gets a runtime-owned built-in state model even when no custom state is declared.
- `produce_verify_step` increments `rework_count` and `replan_count` from final routed tags after hook resolution; defaults are `{"needs_rework", "minor_rework"}` and `{"needs_replan", "major_replan"}`.
- Reserved names are compile-time errors for both aggregate step state and step-item state.

### Hook Contract
- Hook redirects are route-tag redirects only. Returned tags must already exist on the current step’s route table.
- Redirected routes continue through the same route-finalization pipeline, including subsequent `on_route` / `on_taken` hooks.
- Hook rollback snapshots must cover workflow state, current step state, current item state, current step-item state, and sessions before route-finalization hooks run.

### Checkpoint Contract
- Existing checkpoint payload shape is extended, not replaced. Persisted sections remain: workflow state, params snapshot, step states, item states, step-item states, selections, sessions, pending handoffs, pending Q/A, and failure context.
- All model-backed state payloads use `model_dump(mode="json")` on save and `model_validate(...)` on restore.

### History Contract
- `ctx.history` is read-only and must not mutate run files.
- Step telemetry is keyed by `(step_name, scope, item_id)` rather than step name alone.
- `completed` means at least one `step_finished` event; semantic success is tracked separately via configurable accepted route tags.

## Regression Controls
- Keep phase ordering strict: remove compatibility shims before deleting files, then land hook behavior, then state surfaces, then scoped state, then required-write rendering, then telemetry.
- Reuse existing engine checkpoint plumbing and compiled-step metadata instead of introducing a parallel state subsystem.
- Centralize effective-required-write computation to avoid runtime/static-graph/provider drift.
- Reuse existing hook event sink and trace writer rather than inventing a second observability path.
- Preserve current non-scoped workflows and existing `state=BaseModel` simple steps as compatible paths.

## Validation Strategy
- Expand strictness coverage for forbidden imports and failed `autoloop_v3.core` imports.
- Update contract tests around after-hook redirect rejection to assert allowed rerouting, chained redirects, cycle detection, and final-route artifact validation.
- Add state tests for built-in counters, reserved-name failures, `StateVar` sugar, checkpoint restore, and hook-mutated custom state persistence.
- Add scoped-state tests covering item state, step-item state isolation, prompt placeholder resolution, and aggregate-vs-item state coexistence.
- Add runtime/static graph tests for explicit vs effective required writes and provider contract rendering.
- Add history tests for full trace input, events-only fallback, scoped telemetry keys, accepted-route overrides, attempt counting, and token aggregation.

## Compatibility And Intentional Breaks
- Intentional break: `autoloop_v3.core` imports stop working after phase 1 because the spec explicitly removes that bridge.
- Intentional break: hook redirects become legal and route resolution semantics change from “reject non-None redirect” to “validate and chain redirects”.
- Intentional break: simple prompt references to `item.state.*` and `step.item_state.*` become valid only when the corresponding state models are declared; undeclared usage must still fail clearly.
- Existing workflows using `Params` and `State` as Pydantic models remain supported without migration.

## Risk Register
- `R1 Import migration breadth`: many production and test files currently import `autoloop_v3.core`.
  Mitigation: change production imports first, then strictness/tests, then delete bridge files last in the same slice.
- `R2 State persistence drift`: built-in counters currently live outside checkpointed state.
  Mitigation: move visit/route counters into persisted step state before adding new history derivations; add resume tests for aggregate and scoped state.
- `R3 Hook redirect cycles and retry semantics`: redirect loops can create infinite churn or misclassify provider errors.
  Mitigation: enforce the 16-hop cap, emit redirect traces, and mark unknown hook routes as runtime errors.
- `R4 Prompt/state surface expansion`: enabling `item.state` and `step.item_state` can weaken validation if not model-backed.
  Mitigation: validate every placeholder against concrete Pydantic fields and reserved names at compile time.
- `R5 Telemetry cost and inconsistency`: derived history can become expensive or disagree with runtime traces.
  Mitigation: derive from one reader module, require stable execution ids/attempt events, and cache file reads by file metadata.

## Rollback Posture
- Phase 1 rollback is straightforward until bridge files are deleted; keep production import migration and bridge deletion in one reviewed change set.
- Later phases should be isolated behind test-backed commits so hook/state/history regressions can be reverted independently without restoring removed compatibility bridges.
