# Botlane v3 second-pass greenfield architecture plan

## Intent and non-negotiables

- Preserve the public Botlane API, SDK behavior, persisted `.botlane` identity, and user-facing route authoring.
- Preserve the public Botlane SDK helper methods `Botlane.prompt_step(...)`, `Botlane.produce_verify_step(...)`, `Botlane.python_step(...)`, and `Botlane.workflow_step(...)` alongside `Botlane.run(...)` and `Botlane.step(...)`.
- Remove internal compiled compatibility objects, `plan_adapters.py`, `compile_workflow_plan(...)`, `_COMPILED_WORKFLOW_CACHE`, dict-shaped branch runtime internals, duplicated placeholder parsers, and any authored-step backreferences in runtime plans.
- Treat `WorkflowPlan` as the only compiled workflow representation and `ExecutionFrame` as the only mutable runtime backing store.
- Keep the compiler/runtime cutover atomic. A mixed compiled-plan runtime is not a supported intermediate state.

## Current repo findings that shape the plan

- `botlane/core/compiler.py` still defines `CompiledWorkflow`, `CompiledStep`, `CompiledRoute`, `_COMPILED_WORKFLOW_CACHE`, and `compile_workflow_plan(...)`.
- `botlane/core/step_plans.py`, `workflow_plan.py`, `route_contracts.py`, `execution_frame.py`, `execution_services.py`, `branch_groups/results.py`, and `branch_groups/manifest.py` already contain partial second-pass types, but they still carry legacy fields such as `original_step`, `_compiled_step`, string-keyed artifact maps, optional `ReferenceGraph`, and `ProviderTurnKind="operation"`.
- `botlane/core/engine.py` and `engine_collaborators.py` still execute `CompiledStep`/`CompiledRoute` and use `plan_adapters` as a runtime bridge. `StepDispatcher` and `RouteFinalizer` already exist and should be retargeted instead of replaced.
- `botlane/core/context.py` still uses `WeakKeyDictionary`/`context_runtime(...)` sidecar mutation even though `ExecutionFrame.child_for_branch(...)` and `child_for_fan_in(...)` already exist.
- `botlane/core/branch_groups/runtime.py` still consumes compiled branch metadata and keeps branch results as dicts internally, even though `BranchResult` and `BranchManifest` modules exist.
- `botlane/sdk.py`, `botlane/runtime/{loader,runner,static_graph,tracing,provider_policy_resolver}.py`, `botlane/core/workflow_capabilities.py`, and `botlane/workflows/botlane_v1/parity.py` all type against compiled workflow objects today and must move in the same cutover.
- Existing tests already freeze root/core exports in `tests/unit/test_simple_surface.py` and adapter parity in `tests/unit/test_workflow_plan_adapters.py`; those tests need to be split and re-aimed instead of duplicated.
- The repo does not currently have `botlane/core/artifact_plan.py`, so the plan must explicitly introduce it as the canonical home for `ArtifactSpec` and artifact inventory metadata when `artifacts.py` is reduced to public-handle and template-delegate responsibilities.

## Chosen implementation directions

- Canonical one-step execution path: keep `SingleStepPlan`, remove all other one-step fallback paths, and stop routing SDK one-step execution through `compile_workflow_plan(...)`.
- Reuse the existing canonical-looking modules (`step_plans.py`, `workflow_plan.py`, `route_contracts.py`, `execution_frame.py`, `execution_services.py`, `branch_groups/results.py`, `branch_groups/manifest.py`) by correcting their shapes, but add `botlane/core/artifact_plan.py` because the spec requires artifact metadata to move out of `artifacts.py`.
- Keep operations on a separate canonical path unless fully migrated. Do not keep `"operation"` in `ProviderTurnKind` after provider-turn cutover unless the full operation-turn migration and tests are completed in the same slice.
- Treat `artifacts.py` as the public artifact-handle and template-delegate surface only after the cutover. Preserve `ArtifactHandle.artifact` behavior explicitly while moving canonical artifact metadata and inventory to `artifact_plan.py`.

## Ordered phases

### Phase 0: Public freeze

Scope
- Add `tests/unit/test_public_surface.py` and move the export-freeze assertions out of `tests/unit/test_simple_surface.py` into a dedicated surface test.
- Keep or add Phase 0 assertions for simple public authoring examples, route-sentinel authoring (`FINISH`, `AWAIT_INPUT`, `FAIL`, `SELF`, `Route(...)`), and the current branch-group export surface before any internals move.
- Add current-signature and current-behavior assertions for `Botlane.run(...)`, `Botlane.step(...)`, `Botlane.prompt_step(...)`, `Botlane.produce_verify_step(...)`, `Botlane.python_step(...)`, and `Botlane.workflow_step(...)`.
- Add `tests/strictness/test_botlane_identity.py` in Phase 0 and use it to freeze `.botlane`, `.botlane-sdk-task.json`, `botlane.sdk_task/v1`, `botlane.branch_results/v1`, and `botlane_optimizer` imports from `botlane`.
- Keep a Phase 0 assertion for the current `botlane.core.branch_groups.__all__`; stage the target post-cutover assertion but do not enable it yet.

Validation
- `pytest tests/unit/test_public_surface.py tests/unit/test_simple_surface.py tests/unit/test_sdk_facade.py tests/runtime/test_workspace_and_context.py tests/strictness/test_botlane_identity.py -q`

Rollback
- Revert only newly added freeze tests if they expose misunderstanding of the current public contract.

### Phase 1: Canonical type hardening

Scope
- Add `botlane/core/artifact_plan.py` as the canonical home for `ArtifactSpec`, ArtifactId-keyed artifact inventory maps, and related artifact-plan helpers.
- Finish the internal shapes of `ArtifactId`, `ArtifactSpec`, `WorkflowPlan`, `StepSource`, `StepHeader`, `ProviderTurnPlan`, `ExecutionServices`, `BranchResult`, `BranchManifest`, and `ReferenceGraph`.
- Update `workflow_plan.py` to use `artifacts: dict[ArtifactId, ArtifactSpec]`, `public_artifacts: dict[str, ArtifactId]`, and required metadata fields.
- Update `step_plans.py` so the target field layout is explicit before the runtime cutover, but defer removal of legacy fields until the atomic cutover.
- Define the post-cutover boundary: `artifacts.py` keeps public handle behavior and template delegates, while `artifact_plan.py` owns canonical metadata and inventory.
- Keep these types internal only; do not expose them through `botlane.__all__`, `botlane.core.__all__`, or `botlane.core.branch_groups.__all__`.

Validation
- `pytest tests/unit/test_artifact_ids.py tests/unit/test_route_contracts.py tests/unit/test_placeholder_refs.py tests/unit/test_step_plans.py tests/unit/test_sdk_facade.py -q`

Rollback
- Revert any shape change that forces public imports or runtime consumers to depend on unfinished plan types.

### Phase 2: Atomic compiler and runtime cutover

Scope
- Rewrite `botlane/core/compiler.py` so `compile_workflow(...) -> WorkflowPlan` and `_WORKFLOW_PLAN_CACHE` become canonical.
- Delete `CompiledWorkflow`, `CompiledStep`, `CompiledRoute`, `CompiledArtifact`, `CompiledBranchGroupSpec`, `CompiledBranchStepSpec`, `compile_workflow_plan(...)`, `plan_adapters.py`, `_COMPILED_WORKFLOW_CACHE`, `_compiled_step` backrefs, and `original_step` plan fields in the same slice.
- Retarget `botlane/core/engine.py`, `engine_collaborators.py`, `branch_groups/models.py`, `branch_groups/runtime.py`, `sdk.py`, `runtime/{loader,runner,static_graph,tracing,provider_policy_resolver}.py`, `core/workflow_capabilities.py`, and `workflows/botlane_v1/parity.py` to consume `WorkflowPlan`, `StepPlan`, `RouteContract`, and typed route actions directly.
- Keep `StepDispatcher` and `RouteFinalizer`, but make them operate on `StepPlan` variants and return `RouteDecision`/`RouteAction` without compatibility wrappers.
- Remove compiled branch exports from `botlane.core.branch_groups.__all__` and enable the prepared target assertion.

Validation
- Run the focused cutover suites only after the full slice lands:
- `pytest tests/unit/test_workflow_plan_compiler.py tests/contract/test_engine_workflow_plan_runtime.py tests/unit/test_route_contracts.py tests/contract/test_provider_turn_plan.py tests/contract/test_sdk_single_step_execution.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_provider_policy_steps.py -q`

Rollback
- Roll back the entire phase as one unit if any compiled-plan bridge remains or if compiler/runtime types diverge. Do not ship partial cutover commits.

### Phase 3: ExecutionFrame authority

Scope
- Remove `WeakKeyDictionary`, `context_runtime(...)`, and mirrored private-field mutation from `botlane/core/context.py`.
- Move context mutation and child-context creation onto `ExecutionFrame` plus narrow helpers used by `worklists.py`, `branch_groups/context.py`, `engine_collaborators.py`, and provider rendering.
- Preserve the public `Context` surface and the distinction between explicit `message=None` and the default request-message sentinel.

Validation
- `pytest tests/unit/test_execution_frame_context.py tests/unit/test_primitives_and_stores.py tests/unit/test_branch_group_context_sessions.py tests/runtime/test_workspace_and_context.py -q`

Rollback
- Revert frame-authority changes if any public `Context` property stops reflecting the same runtime state as before.

### Phase 4: Branch typed evidence cutover

Scope
- Make branch execution consume `BranchGroupPlan` and return `BranchResult` internally from all branch-runtime helpers.
- Make `build_branch_manifest(...)` return `BranchManifest`, and limit serialization to `BranchResult.to_manifest_dict()` and `BranchManifest.to_dict()`.
- Keep the manifest schema and JSON shape stable at the file boundary, and update `select_branch_group_outcome(...)` plus context rendering to use typed manifests.

Validation
- `pytest tests/contract/test_branch_result_runtime.py tests/contract/test_branch_result_serialization.py tests/contract/test_branch_group_runtime.py -q`

Rollback
- Revert only if the persisted branch evidence format changes or if fail-fast / cancellation behavior regresses.

### Phase 5: Placeholder and reference-graph cutover

Scope
- Centralize placeholder parsing, validation, and rendering in `botlane/core/placeholders.py`.
- Reduce `botlane/core/artifacts.py` to thin delegates and remove duplicated parser symbols and `_resolve_*` helpers.
- Preserve `ArtifactHandle.artifact` public behavior while `ArtifactSpec` and artifact inventory stay in `artifact_plan.py`.
- Make the compiler attach `ReferenceGraph` to `WorkflowPlan` and stop reparsing prompt strings at runtime for inferred artifact reads.
- Update discovery and branch/fan-in placeholder validation paths to use the same parser and full surface coverage.

Validation
- `pytest tests/unit/test_placeholder_refs.py tests/unit/test_validation.py tests/unit/test_simple_surface.py tests/contract/engine/test_prompt_context.py -q`

Rollback
- Revert if any current placeholder surface loses support or if runtime error wording drifts materially.

### Phase 6: Provider turn cutover

Scope
- Drive prompt and produce/verify execution exclusively through `ProviderTurnPlan -> RenderedProviderTurn -> ProviderTurnResult`.
- Remove provider-turn fallback adaptation from `engine_collaborators.py`.
- Keep operation execution separate but compiled-free unless a full typed operation-turn migration is completed with tests in the same phase.
- Ensure provider session persistence, retries, raw output persistence, and usage aggregation stay unchanged.

Validation
- `pytest tests/contract/test_provider_turn_plan.py tests/runtime/test_runtime_providers.py tests/runtime/test_provider_policy_core_protocol.py tests/runtime/test_provider_policy_steps.py -q`

Rollback
- Revert if any provider-backed step bypasses the rendered transport boundary or if operation runtime still depends on removed compiled types.

### Phase 7: SDK one-step cutover

Scope
- Keep `SingleStepPlan` as the only one-step execution architecture.
- Remove the synthetic workflow fallback and any dependency on `compile_workflow_plan(...)`.
- Preserve invocation-local policy layering, `provider_questions` defaulting, pause/resume behavior, retention handling, `StepResult(value=None, workflow_result=...)`, existing SDK error wrapping, and parity for `Botlane.prompt_step(...)`, `Botlane.produce_verify_step(...)`, `Botlane.python_step(...)`, and `Botlane.workflow_step(...)`.

Validation
- `pytest tests/unit/test_sdk_facade.py tests/contract/test_sdk_single_step_execution.py tests/contract/test_single_step_plan_equivalence.py -q`

Rollback
- Revert if `Botlane.step(...)` semantics diverge from `Botlane.run(...)` or if local policy application mutates authored step objects.

### Phase 8: Strictness and cleanup

Scope
- Add `tests/strictness/test_no_internal_compat_layers.py`, finish `tests/strictness/test_core_runtime_boundary.py`, and expand the Phase 0 `tests/strictness/test_botlane_identity.py` into its final strictness form.
- Remove or replace adapter-era tests such as `tests/unit/test_workflow_plan_adapters.py` and any assertions that preserve compiled objects or compatibility wrappers.
- Run the repo-wide stale-identity scan for `autoloop`, `.autoloop`, stale schema IDs, and forbidden public `RouteContract` aliases.
- Finish with a full `pytest` run only after all earlier phases are green.

Validation
- `pytest -q`

Rollback
- Revert strictness checks only if they block valid internal references that the spec explicitly allows; otherwise fix the underlying code instead of weakening the scan.

## Target interfaces after the rewrite

- `compile_workflow(workflow_cls) -> WorkflowPlan`
- `WorkflowPlan.new_state() -> BaseModel`
- `StepHeader` contains metadata only and never authored steps, route tables, or compatibility fields.
- `StepDispatcher` branches on `PromptStepPlan | ProduceVerifyStepPlan | PythonStepPlan | ChildWorkflowStepPlan | BranchGroupStepPlan`.
- `RouteFinalizer.finalize(...) -> RouteDecision`
- `Engine` consumes `RouteAction` (`Continue | Finish | AwaitInput | FailAction`) rather than terminal strings or direct-control wrappers.
- `BranchGroupRuntime._run_branches(...) -> dict[int, BranchResult]`
- `build_branch_manifest(...) -> BranchManifest`
- `render_branch_group_context(...)` accepts `BranchManifest` or final serialized manifest dict only at the rendering boundary.
- `artifact_plan.py` owns canonical artifact metadata and inventory; `artifacts.py` keeps public artifact-handle behavior plus thin template delegates.
- `ArtifactHandle.artifact` public behavior remains unchanged.
- `Botlane.step(...)`, `Botlane.prompt_step(...)`, `Botlane.produce_verify_step(...)`, `Botlane.python_step(...)`, and `Botlane.workflow_step(...)` execute through the preserved single-step/runtime contracts without helper-specific fallback paths.

## Regression controls and risk register

- R1: Export drift.
  Control: freeze root/core/branch-group exports before internals move; keep all internal plan/runtime types off public `__all__`.
- R2: Mixed compiled-plan runtime during cutover.
  Control: make Phase 2 one atomic slice touching compiler, engine, SDK, runtime helpers, static graph, and parity consumers together.
- R3: Context mutation regressions.
  Control: preserve `Context` property behavior with dedicated frame-authority tests before removing `context_runtime(...)`.
- R4: Branch evidence or outcome regressions.
  Control: keep schema `botlane.branch_results/v1`, snapshot JSON shape, and fail-fast / cancellation behavior under dedicated contract tests.
- R5: Placeholder surface regressions.
  Control: validate prompt, workflow-step message, artifact template, branch, fan-in, worklist, params, state, and runtime-template surfaces from one parser.
- R6: Provider and SDK behavior drift.
  Control: hold provider session, retry, raw-output, usage, and `Botlane.step(...)` parity under targeted contract suites before the final full run.

## Exit criteria

- All required phase suites are green at the end of each completed phase.
- Phase 2 lands with no remaining compiled/adapter symbols in `botlane/core`.
- Final `pytest -q` passes with public exports unchanged, branch-group compiled exports removed, no stale Botlane identity regressions, and no core-to-runtime import violations outside `TYPE_CHECKING`.
