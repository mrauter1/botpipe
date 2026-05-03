# Remaining Delta Implementation Plan

## Objective
Align the runtime, compiler, and public authoring surface with the final hook/control model in the request: single-arity `hook(ctx)`, explicit runtime controls, no legacy hook/state-return compatibility, truthful checkpoint/failure semantics, worklist-helper-first scoped execution, and canonical vocabulary across runtime artifacts and docs.

## Current Baseline
- Already present and should be completed rather than rebuilt: `ctx.worklists` / `ctx.worklist(...)` / `ctx.current_worklist`, scoped `item_state` + `step_item_state`, `FailureContext` / typed execution errors, hook redirect tracing, collaborator shells in [`autoloop/core/engine_collaborators.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine_collaborators.py), and persisted schema ids in [`autoloop/core/schema_registry.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/schema_registry.py).
- Main remaining gaps: legacy discovery/compiler paths (`on_start`, `on_outcome`, `on_<step>`, `before_do`, `before_review`, class-attached compile cache), tuple-heavy engine/provider returns, ad hoc status vocabulary, resume hard-fail on topology mismatch, and incomplete trace/history semantics for direct runtime controls and hook short-circuits.

## Milestones

### 1. Public Contract Cleanup
- Scope: [`autoloop/simple.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py), [`autoloop/core/steps.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/steps.py), [`autoloop/core/discovery.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/discovery.py), [`autoloop/core/hook_validation.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/hook_validation.py), [`autoloop/core/compiler.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/compiler.py), [`autoloop/core/routes.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/routes.py).
- Remove public legacy surfaces and aliases: multi-arg hooks, state-return hooks, `AfterStepResult`, route effects, `on_route`, auto-installed `on_<step>` aliases, public class-level transition tables/flow, and public compatibility wording such as `system step`.
- Normalize pair-step/public naming to final vocabulary: `before_producer`, `after_producer`, `before_verifier`, `after_verifier`, `python_step`, `writes` / `producer_writes` / `verifier_writes`.
- Validation contract: only callable slot validity + exact `hook(ctx)` signature; no static inference of hook-returned routes; invalid routes/targets/payloads must fail at runtime with current mutated state/session preserved.
- Intentional breakage to call out in implementation/docs/tests: legacy public hook signatures and legacy class-method authoring are removed rather than shimmed.

### 2. Hook, Python-Step, and Finalization Normalization
- Scope: [`autoloop/core/engine.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine.py), [`autoloop/core/engine_collaborators.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine_collaborators.py), provider parsing/request assembly modules, and trace emitters.
- Make one normalized control path for all hooks and `python_step` handlers:
  - `None`
  - route-tag `str`
  - `Event`
  - `RequestInput`
  - `Goto`
  - `Fail`
- Add/finish result dataclasses and replace positional tuple plumbing:
  - `HookExecutionResult`
  - `StepExecutionResult`
  - `RouteFinalizationResult`
  - `PairProviderResult`
  - `ProviderExecResult`
- Allow any hook phase to return any valid control result without phase gates; `before`, `before_producer`, and `before_verifier` short-circuit provider execution when they return route/control values.
- Route-local `on_taken` stays, chains redirectively with the existing redirect cap, and stops chaining on direct controls.
- Artifact validation, route validation, and direct-control validation become phase-independent and candidate-route-independent.

### 3. Runtime Correctness, Trace/History, and Worklist Semantics
- Scope: engine finalization/state update paths, [`autoloop/core/history.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/history.py), [`autoloop/runtime/tracing.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/tracing.py), [`autoloop/runtime/static_graph.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/static_graph.py), worklist/context state sync.
- Preserve current mutated workflow/step/item/step-item/session state on all failures; remove remaining rollback-oriented logic from active paths and ensure failure checkpoints always serialize the latest in-memory state.
- Keep runtime-owned built-ins truthful:
  - increment `visits` on entry;
  - update `last_route`, `last_reason`, `rework_count`, `replan_count` only after successful route finalization;
  - never update route built-ins for direct controls.
- Guarantee scoped `ctx.step_item_state` even without custom author state by exposing built-in-only runtime fields, while keeping built-in fields read-only.
- Replace route-effect behavior with worklist helper + `on_taken` flows only; topology/static graph/contracts must contain no route effects.
- Centralize route/status/terminal classification in one helper module and use it everywhere trace/history/runner/inspection/workspace derive status, route metrics, or terminals. Any backward read of legacy `paused` data must be confined to explicit schema migration, not scattered aliases.
- Trace requirements:
  - hook short-circuits emit `provider_attempted: false` plus source hook/phase and target metadata;
  - producer-only short-circuits emit `producer_attempted: true`, `verifier_attempted: false`;
  - provider retry attribution only applies when a provider turn actually ran.

### 4. Compiler Cache, Resume, Schema, and Documentation Finalization
- Scope: compiler/runtime runner/resume loaders, persisted topology/contracts, docs/examples, strictness scans, and contract tests.
- Replace `workflow_cls.__compiled_workflow__` as the source of truth with an explicit compiler cache keyed by source/topology fingerprint; recompilation must occur when class source changes.
- Resume should load the saved run contract/topology, warn on mismatch by default, and continue unless a required executable element cannot be resolved; strict resume mode becomes the opt-in hard-fail path.
- Register any remaining persisted payload schemas and move old-schema compatibility into explicit migration-or-fail reader logic instead of ad hoc field aliases.
- Update public docs/examples to import from `autoloop`, document only final hook/control/worklist patterns, and remove legacy surfaces from author-facing material.

## Interface Targets
- Public hook signature: `def hook(ctx): ...`
- Public hook/python-step return contract: `None | str | Event | RequestInput | Goto | Fail`
- `HookResult`: normalized event-or-control only; never state replacement.
- `WorklistRuntimeView`: selection/status mutation helpers plus `advance()` / `advance_or(...)` without implicit routing.
- Failure payload: `FailureContext` attached through typed execution errors only; no `setattr` / `getattr` recovery conventions.

## Compatibility and Intentional Breaks
- Reject, do not shim:
  - multi-argument public hooks;
  - hook or `python_step` `BaseModel` returns;
  - `(BaseModel, Event|str)` returns;
  - `AfterStepResult`;
  - `on_route`;
  - route effects;
  - public simple/class-level handler aliases.
- Keep internal changes minimal: finish the current collaborator split instead of adding a second abstraction layer. New helpers are justified only where they remove duplicated normalization/tuple plumbing or centralize status logic.

## Regression Controls
- Primary regression surfaces: hook short-circuiting, pair-step verifier skipping, route built-in state truthfulness, checkpoint-on-failure semantics, worklist selection persistence, resume behavior, runtime/static graph payloads, and optimizer/history consumers of trace/status data.
- Mandatory test expansion/update areas:
  - [`tests/contract/test_engine_contracts.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py)
  - [`tests/unit/test_simple_surface.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_simple_surface.py)
  - [`tests/runtime/test_history.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_history.py)
  - [`tests/runtime/test_runtime_static_graph.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_runtime_static_graph.py)
  - [`tests/runtime/test_workspace_and_context.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workspace_and_context.py)
  - [`tests/strictness/test_no_compat.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py)

## Risk Register
- High: changing execution result plumbing can destabilize engine step dispatch and provider retry handling. Mitigation: land dataclass migration together with focused contract tests before broader cleanup.
- High: removing legacy discovery/compiler paths can silently break non-simple/internal workflows. Mitigation: restrict removal to public/compiler paths explicitly called out by the request, then update strictness scans and remaining internal call sites in the same slice.
- Medium: resume default behavior change touches runner UX and persisted topology loading. Mitigation: implement saved-contract-first loading with explicit warning emission and add strict-mode tests in the same phase.
- Medium: status centralization can skew history/inspection metrics. Mitigation: route all status derivation through one helper and update telemetry tests to cover direct controls, hidden routes, and no-provider attempts.

## Rollback
- Roll back by phase boundary only:
  - public contract cleanup;
  - execution normalization;
  - runtime trace/history/state semantics;
  - compiler/resume/schema/docs.
- Avoid partial rollback inside a phase once tuple/dataclass or status-classification migrations start, because mixed call shapes will create harder-to-diagnose regressions than a full phase revert.
