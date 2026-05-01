# Remaining-Delta Implementation Plan

## Goal
Implement the remaining-delta spec against the current v3 baseline without keeping compatibility shims. The requested hard breaks are in scope: remove `PAUSE`, public `on_route`, `autoloop_v3`, workflow-facing git/tracing declarations, top-level internal namespaces, AST hook inference, and the other removed public names.

## Baseline Findings
- `PAUSE`, `pending_question`, and pause-oriented status handling are still wired through `core.primitives`, `core.engine`, `runtime.runner`, `runtime/stores/filesystem.py`, `runtime/static_graph.py`, and many tests.
- Public `on_route` is still part of simple declarations, core step objects, compiler metadata, validation, runtime finalization, tracing/history payloads, and generated topology artifacts.
- Route finalization, hook chaining, checkpoint persistence, and built-in step-state mutation are all concentrated in `core.engine`; failures currently propagate by mutating private exception attributes.
- Topology and related static artifacts are already written before the first step executes via `runtime.tracing.RuntimeTraceWriter._initialize`; extend that path instead of adding a second artifact writer.
- Prompt registry seeding is currently too narrow (`FilesystemPromptRegistry(workflow_parent)` in `runtime.runner`), so prompt-path expansion must be part of the runtime/package cleanup work.
- The repo still carries dual namespaces (`core/`, `runtime/`, `stdlib/`, `extensions/`, `autoloop_v3/`) and many imports that bypass the desired `autoloop.*` layout.

## Phase Plan

### Phase 1: Public Surface And Terminal Cleanup
- Replace `PAUSE` with `AWAIT_INPUT` across public/internal terminals, route helpers, run metadata, checkpoint payload names, status logic, docs, and examples.
- Add public `RequestInput`, `Goto`, and `Fail` types; export them from the canonical authoring surface and internal canonical modules.
- Remove public `on_route` parameters and delete the requested public names from exports, declarations, docs, and strictness coverage.
- Preserve provider-selected `"question"` as a route tag, but stop treating raw strings as step-target jumps anywhere in the public surface.

### Phase 2: Runtime-Control Semantics And Hidden Routes
- Extend `Route`/compiled-route data with `provider_visible`, and derive provider-facing route tables from the visibility-filtered view while keeping topology/global route data complete.
- Add hook-return normalization for `None`, route-tag strings, `Event`, `RequestInput`, `Goto`, and `Fail`; raw strings always mean route tags and must validate against the current step.
- Update step finalization so direct runtime controls bypass route-required-write validation and built-in route-field mutation, while route-based finalization remains the only place that mutates runtime-owned route fields.
- Keep redirect chaining for route tags and `Event` reroutes only, stop chaining on direct controls, and enforce `max_hook_redirects = 16` with preserved redirect history.

### Phase 3: Checkpoint/Resume, State Protection, And Structured Failures
- Replace pending-question storage with pending-input metadata that includes source step/hook, question, reason, best supposition, schema, created timestamp, and pending input id.
- Expose resumed validated input on `ctx.input_response`, clear pending input after consumption, and preserve current state/session on runtime-control, provider, hook, artifact, and finalization failures.
- Introduce `FailureContext` plus `StepExecutionError`, and migrate checkpoint/failure/retry propagation off private exception annotations in the engine and operation replay path.
- Wrap built-in step and step-item state in a read-only runtime view so `visits`, `last_route`, `last_reason`, `rework_count`, and `replan_count` stay readable but not assignable, while custom fields remain mutable.

### Phase 4: Metadata, Tracing, And Provider Attribution
- Add runtime-control trace/event payloads for `request_input`, `goto`, and `fail`, plus step-finalization records that distinguish candidate route, final route, direct runtime control, terminal, target step, source hook/phase, and redirect chain.
- Preserve route-redirect trace records with redirect index and hook metadata, and make provider attribution depend on the provider-selected route instead of hook-introduced reroutes.
- Update run metadata/history normalization so `AWAIT_INPUT` maps to status `awaiting_input`, while provider route tag `"question"` remains distinct from the terminal/status layer.
- Keep child-workflow telemetry aligned with the new terminal semantics so parent workflows can resume and inspect child runs without pause-specific assumptions.

### Phase 5: Validation, Rendering, And Topology
- Remove AST-based hook-route inference and keep hook validation focused on callable placement/signature plus runtime validation of returned route tags, events, and control objects.
- Filter provider-rendered route choices by `provider_visible=True`, but keep hidden routes in topology, route tables, compile reports, capability snapshots, and static graphs with explicit visibility markers.
- Extend static artifacts with explicit/effective required writes, route-local hooks, runtime-control hook locations, hidden-route markers, `AWAIT_INPUT`, and unified state/item-state surfaces.
- Preserve the existing run-start artifact generation path in tracing initialization so artifacts still exist even if the first step fails.

### Phase 6: Namespace Cut, Optimizer Boundary, And Prompt Registry
- Move runtime/core/stdlib/extensions under `autoloop/`, delete `autoloop_v3/`, remove top-level internal production imports, and migrate remaining code/tests/tooling to canonical `autoloop.*` imports.
- Expose stable inspection/query APIs from the canonical namespace by reusing the existing run/workspace/history/capability helpers instead of letting optimizer code reach into arbitrary internals.
- Update optimizer terminal/status logic for `AWAIT_INPUT`, hidden-route-aware topology, and the new route/control metadata surfaces.
- Expand prompt-registry construction to use workflow parent, compiled prompt paths, workflow capability prompt paths, and configured prompt roots with deterministic precedence.

### Phase 7: Maintainability Refactors
- Decompose the engine around the existing responsibilities (`StepDispatcher`, `RouteFinalizer`, `HookRunner`, `ArtifactGuard`, `StateRuntime`, `SessionRuntime`, `CheckpointManager`, `OperationRecorder`, `WorkflowInvoker`) without adding speculative layers.
- Split validation/compiler code into discovery/lowering/inventory/topology/hook/prompt/state modules by moving the current logic behind clearer ownership boundaries.
- Unify session-store behavior behind backend composition and keep persistence-specific behavior in the backend classes.
- Rename `_LLMOperationSurface`/`_ClassifyOperationSurface` to public `LLMOperation`/`ClassifyOperation`, add docstrings/repr/stubs, type `ChildWorkflowResult[OutputT]`, and update operation replay fingerprinting/mismatch behavior.

### Phase 8: Tests, Docs, And Golden Workflow
- Update runtime, contract, strictness, and unit coverage for renamed terminals, removed public names, hidden routes, runtime controls, pending-input resume, built-in state protection, replay mismatch behavior, prompt registry resolution, and topology artifacts.
- Add one end-to-end golden workflow that exercises the new authoring surface, worklist scopes, hidden-route redirects, runtime controls, checkpoint/resume, typed child output, and telemetry artifacts together.
- Rewrite canonical docs/examples to use `FINISH`, `AWAIT_INPUT`, `RequestInput`, `Goto`, `Fail`, `produce_verify_step`, `before`/`after`, and `Route.to(..., on_taken=...)` only.

## Interface Contracts
- Terminal constants: `FINISH`, `AWAIT_INPUT`, `FAIL`, `SELF`.
- Runtime controls:
  - `RequestInput(question, reason=None, best_supposition=None, input_schema=None)`
  - `Goto(target, reason=None, handoff=None)`
  - `Fail(reason)`
- Route API: `Route.to(target, ..., on_taken=None, provider_visible=True)`.
- Context additions:
  - `ctx.input_response`
  - `ctx.step_state` and `ctx.step_item_state` remain the single user-facing surfaces, but built-in runtime fields become read-only.
- Failure model:
  - `FailureContext(kind, step_name, candidate_route=None, final_route=None, runtime_control=None, provider_attributable=False, source_hook=None, source_phase=None, target_step=None, pending_input_id=None, details={})`
  - `StepExecutionError(checkpoint_state, failure_context, retry_kind)`

## Compatibility And Migration Notes
- This is a hard cut. Do not leave import aliases or fallback branches for `PAUSE`, `on_route`, `autoloop_v3`, or top-level `core`/`runtime`/`stdlib`/`extensions`.
- Persisted checkpoint/run/trace readers must either tolerate known older schema ids explicitly or fail with a clear migration error; resume must not silently reinterpret legacy `PAUSE` or `pending_question` payloads.
- Hidden routes must come from the same compiled route inventory as provider-visible routes so provider rendering and topology artifacts cannot drift.
- Provider-selected `"question"` remains legal when declared, but hook-returned `RequestInput(...)` is runtime-attributable and must not require provider-visible question-route scaffolding.

## Regression Controls
- Do not add a second topology/static-artifact writer; extend the existing tracing bootstrap path.
- Keep built-in route-state truthfulness: only successfully finalized route-based transitions may update `last_route`, `last_reason`, `rework_count`, or `replan_count`.
- Failures must checkpoint the mutated current workflow/session/custom state instead of auto-restoring snapshots.
- Runtime controls must validate before execution and bypass route-required-write checks by construction.
- Prompt registry precedence must be deterministic and covered by tests so widening search roots does not create ambiguous prompt resolution.

## Risk Register
- Namespace migration is the widest blast radius. Mitigation: move modules/imports mechanically, update strictness checks, then delete compatibility trees only after the canonical import sweep is green.
- `core.engine` is highly coupled today. Mitigation: land runtime-control semantics and structured-failure behavior before collaborator extraction so the refactor moves stabilized logic instead of changing it twice.
- Checkpoint schema changes can strand resumable runs. Mitigation: choose explicit legacy handling per reader surface and fail clearly where no safe translator exists.
- Hidden-route filtering can desynchronize provider contracts and topology if implemented twice. Mitigation: derive both from one compiled route model with a visibility filter only at provider-render time.
- Replay fingerprint changes can affect deterministic reruns. Mitigation: keep the replay store format explicit, add warning-vs-fail mismatch tests, and migrate only the fingerprint inputs requested by the spec.
