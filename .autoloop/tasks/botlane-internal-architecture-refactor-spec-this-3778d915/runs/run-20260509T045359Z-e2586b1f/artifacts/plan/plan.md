# Plan

## Objective

Refactor Botlane internals toward typed plan/runtime value objects while preserving the current public root API, simple authoring surface, SDK behavior, persistence identity, and existing runtime schemas. Treat the supplied spec as the implementation contract and prefer compatibility adapters over broad rewrites.

## Current Code Anchors

- `botlane/core/compiler.py` is the current source of truth for `CompiledWorkflow`, `CompiledStep`, `CompiledRoute`, route tables, artifact inventory wiring, and topology hashing.
- `botlane/core/context.py` owns the public `Context` surface, `ChildWorkflowResult`, `_DEFAULT_MESSAGE`, and the `_CONTEXT_RUNTIMES` weak sidecar that later phases must preserve during migration.
- `botlane/core/engine_collaborators.py` and `botlane/core/branch_groups/runtime.py` are the main compiled-shape consumers; both are still coupled to `CompiledStep`/`CompiledRoute` and current runtime dict payloads.
- `botlane/runtime/workspace.py` already owns the canonical task/workflow/run path vocabulary and persisted run metadata; `RunPaths` integration should reuse that ownership instead of inventing parallel path derivation.
- `botlane/runtime/loader.py` already owns workflow reference resolution through `WorkflowReference` / `ResolvedWorkflow`; `WorkflowLocator` should adapt that path rather than bypass it.
- Existing tests already freeze important public behavior: `botlane.__all__` in `tests/unit/test_simple_surface.py`, SDK facade behavior in `tests/unit/test_sdk_facade.py`, provider policy layering in `tests/runtime/test_sdk_policy.py` and `tests/runtime/test_provider_policy_steps.py`, branch manifest schema in `tests/contract/test_branch_group_runtime.py`, and compatibility removals in `tests/strictness/test_no_compat.py`.

## Non-Negotiable Invariants

- `botlane.__all__` must remain byte-for-byte stable. Do not export new internal plan/runtime types from `botlane.__init__`.
- `botlane.core.__all__` and `botlane.core.branch_groups.__all__` stay unchanged unless a targeted internal test requires an addition; new internal value objects remain module-local imports only.
- Public simple and SDK entrypoints remain source-compatible, including `Botlane.run(...)`, `Botlane.step(...)`, helper constructors, route sentinels, artifact helpers, `Context`, and pause/resume semantics.
- Existing persistence identity stays unchanged: `.botlane`, `.botlane/tasks`, `.botlane-sdk-task.json`, `botlane.sdk_task/v1`, `botlane.branch_results/v1`, and `generated_by="botlane.sdk"`.
- No `botlane/core` runtime imports from `botlane.runtime` outside `TYPE_CHECKING`.
- `CompiledWorkflow`, `CompiledStep`, and `CompiledRoute` remain compatibility facades throughout migration; new plan/value types cross that boundary only via `botlane/core/plan_adapters.py`.
- `WorkflowPlan` may remain an adapter-only layer while `Engine` continues consuming `CompiledWorkflow`; engine migration is explicitly deferred until parity coverage proves it safe.

## Milestones

### 1. Freeze Public Compatibility

- Audit existing test coverage against the spec and add only the missing freeze assertions:
  - `botlane.core.__all__` / `botlane.core.branch_groups.__all__` stability
  - public and semi-public dataclass positional compatibility
  - persistence identity invariants under `.botlane/tasks`
  - `provider_questions` defaulting and `StepResult.value is None`
  - unsupported branch-group / `client.step(...)` constraints that must not broaden silently
- Do not change runtime behavior in this milestone.

### 2. Boundary Primitives And Import Rules

- Add `botlane/core/identifiers.py`, `botlane/core/run_paths.py`, `botlane/core/provider_policy_resolution.py`, and a conversion-only `botlane/core/plan_adapters.py` shell.
- Update `botlane/runtime/provider_policy_resolver.py` to satisfy the core protocol without changing policy resolution semantics.
- Add the AST-aware `tests/strictness/test_core_runtime_boundary.py` only after confirming current `botlane/core` files have no runtime imports outside `TYPE_CHECKING`.
- Keep `Context` and `Engine` constructor signatures unchanged.

### 3. Route Contracts And Route Decisions

- Add `botlane/core/route_contracts.py` with `RouteContract`, `RouteDecision`, `RouteAction`, and route-view helpers derived from `WorkflowPlan.routes`, not duplicated on step headers.
- Implement `CompiledRoute` round-trips in `plan_adapters.py`, including inventory-aware required-write conversion and explicit failure when non-empty required writes are adapted without inventory.
- Keep `CompiledRoute` as the runtime-facing object until route parity and runtime-control tests are green.

### 4. Step Plans And Workflow Plans

- Add `botlane/core/step_plans.py` and `botlane/core/workflow_plan.py`.
- Add `compile_workflow_plan(...)` in `compiler.py` with a lazy in-function import of `plan_adapters`.
- Preserve `compile_workflow(...) -> CompiledWorkflow`, current topology hashes, current provider payload naming, and branch-group compiled step support.
- Reuse `botlane/core/branch_groups/models.py` for an import-cycle-safe `BranchGroupPlan` only if colocating branch plan types in `step_plans.py` is not practical.

### 5. ExecutionFrame Behind Context

- Add `botlane/core/execution_frame.py` and synthesize an internal frame from the existing `Context` constructor arguments.
- Mirror old private fields and `_ContextRuntime` writes during migration so public `Context` reads remain stable.
- Preserve `_DEFAULT_MESSAGE` semantics, child workflow result fields, worklist selection snapshots, branch metadata, and fan-in metadata before removing any sidecar state.

### 6. ProviderTurnPlan And Route Finalization Adapters

- Add `ProviderTurnPlan` and `RouteDecision` adapters around the current provider request/render/result and route finalization flows.
- Migrate only prompt and produce/verify provider turns in the first pass.
- Keep operation execution, `RenderedProviderTurn`, `ProviderTurnResult`, and `RouteFinalizationResult` behavior unchanged until dedicated parity coverage passes.

### 7. Incremental Collaborator Migration

- Add a narrow `botlane/core/execution_services.py` shell and migrate collaborators off direct `Engine` private calls in the prescribed order.
- Keep migrations small and ownership-specific; avoid a broad service that simply mirrors the engine.
- Temporary private-call bridges are acceptable only when marked and scheduled for removal by a later phase.

### 8. PlaceholderRef And ReferenceGraph

- Add `botlane/core/placeholders.py` and `botlane/core/reference_graph.py`.
- Delegate current placeholder parsing, validation, inferred-read discovery, and rendering to the new types without changing supported grammar or error quality.
- Preserve current `ctx.*` allowlists and artifact-path restrictions.

### 9. Branch Results, Workflow Locator, And Policy Rules

- Add typed branch result serialization in `botlane/core/branch_groups/results.py` with manifest JSON parity.
- Add `botlane/runtime/workflow_locator.py` as an adapter over current loader/reference resolution, not as a second loader stack.
- Introduce provider policy rule tables only if they preserve current emitter payloads and strictness decisions exactly.

### 10. Optional SingleStepPlan And Cleanup

- Add `SingleStepPlan` only after explicit parity coverage exists against the current synthetic single-step workflow path.
- Keep the existing synthetic path as fallback until the full suite is green on the new path.
- Remove temporary duplication, adapter-only private calls, and dead compatibility branches only after full-suite validation.

## Interface Ownership

- `botlane/core/plan_adapters.py`
  - Sole owner of conversions between compiled objects and new internal plan/value objects.
  - The only new module allowed to import compiler dataclasses at runtime.
- `botlane/core/identifiers.py`
  - Owns `ArtifactId` and artifact identity helpers.
  - Must use inventory-driven resolution; no dot-splitting heuristics.
- `botlane/core/run_paths.py`
  - Owns `RunPaths` / `RunIdentity` with existing field names `task_folder`, `workflow_folder`, `run_folder`, `package_folder`.
  - Must adapt to `runtime.workspace` and current `ChildWorkflowResult`, not replace them.
- `botlane/core/route_contracts.py`
  - Owns typed static route contracts and runtime route action/decision values.
  - Canonical route tables live on `WorkflowPlan`, not `StepHeader`.
- `botlane/core/step_plans.py`
  - Owns `StepIO`, `StepHeader`, `ProviderTurnPlan`, typed `StepPlan` variants, and optionally `SingleStepPlan`.
- `botlane/core/workflow_plan.py`
  - Owns immutable executable plan state copied from compiled workflow data.
- `botlane/core/execution_frame.py`
  - Owns mutable runtime state backing `Context` while preserving current constructor and property behavior.
- `botlane/runtime/workflow_locator.py`
  - Owns runtime-only locator variants that adapt current loader/reference behavior.

## Validation Strategy

- Run the first milestone exactly as specified before touching engine execution:
  - `python -m pytest tests/unit/test_artifact_ids.py`
  - `python -m pytest tests/unit/test_run_paths.py`
  - `python -m pytest tests/runtime/test_provider_policy_core_protocol.py`
  - `python -m pytest tests/strictness/test_core_runtime_boundary.py`
  - `python -m pytest tests/unit/test_simple_surface.py`
  - `python -m pytest tests/unit/test_sdk_facade.py`
  - `python -m pytest tests/strictness/test_no_compat.py`
- After each later phase, rerun the spec-named targeted buckets before broadening scope.
- Before completion, run `python -m pytest`.
- Add parity tests before switching ownership:
  - topology hash parity before `compile_workflow(...)` output changes
  - route table parity before route consumers move
  - provider turn adapter parity before prompt/pair execution paths change
  - branch manifest parity before branch-runtime serialization changes
  - synthetic-step parity before `Botlane.step(...)` changes

## Compatibility Notes

- Public and semi-public dataclasses may only receive appended defaulted fields; positional construction must remain valid.
- `ChildWorkflowResult` keeps current path fields even if `RunIdentity` or `RunPaths` are added internally.
- `Context` remains the public facade; no public `ContextView` is introduced.
- Provider request artifact names and route payloads stay string-compatible until compatibility tests are intentionally migrated.
- Unsupported branch-group capabilities stay unsupported unless a later phase adds full implementation plus tests.

## Risk Register

- Risk: duplicating canonical route state between `WorkflowPlan` and step headers causes drift across compiler, provider contracts, and runtime finalization.
  - Control: store canonical route contracts only on `WorkflowPlan`; derive route views with helper functions.
- Risk: naive artifact identity parsing breaks dotted artifact names and current inventory ambiguity rules.
  - Control: keep all identity conversion inventory-driven in `plan_adapters.py` and add negative tests for dot-splitting shortcuts.
- Risk: moving `Context` storage too early breaks pause/resume, child workflow results, worklists, or branch/fan-in helpers.
  - Control: introduce `ExecutionFrame` behind the current constructor first, mirror old fields, and defer sidecar removal until parity coverage is green.
- Risk: provider-turn migration accidentally forks transport/result types or changes operation behavior.
  - Control: adapt `ProviderTurnPlan` into existing `RenderedProviderTurn` / `ProviderTurnResult` machinery and explicitly defer operations.
- Risk: typed branch results or workflow locators change persisted JSON or workflow resolution precedence.
  - Control: serialize back to the exact current manifest shape and adapt current loader/reference models instead of replacing them.
- Risk: broad engine-service abstraction reintroduces a god object under a new name.
  - Control: keep `ExecutionServices` narrow, protocol-based, and collaborator-specific.

## Rollback Guidance

- Every phase must land with the previous public behavior still passing targeted regression tests.
- If a phase breaks parity, revert to the last passing adapter boundary instead of layering more compatibility shims on top.
- `CompiledWorkflow` / `CompiledStep` / `CompiledRoute`, current `Context`, and the synthetic `Botlane.step(...)` path remain the rollback anchors until their replacements are fully parity-tested.
