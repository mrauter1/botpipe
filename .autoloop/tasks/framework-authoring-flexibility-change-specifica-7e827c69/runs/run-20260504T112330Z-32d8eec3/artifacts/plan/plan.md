# Framework Authoring Flexibility Change Plan

## Delivery stance

- Preserve the specification's milestone order: runtime semantics first, authoring ergonomics second.
- Reuse existing foundations already present in-tree: `RuntimeInteractionPolicy`, `ControlRoutes`, `Context.ensure_selection(...)`, runtime worklist resolver callbacks, `Effects`/`WorklistEffect`, `ValidationResult`/`validation_step`, artifact inventory ownership checks, prompt placeholder analysis, and inspection/static-graph payloads.
- Treat mismatches against the spec as behavioral alignment work, not as permission to replace stable APIs with parallel abstractions.
- Do not modify workflow packages as part of this change; only framework/runtime/compiler surfaces and their tests move.

## Current codebase alignment

- Route policy foundations already exist in `autoloop/core/providers/models.py`, `autoloop/core/compiler.py`, `autoloop/core/engine.py`, `autoloop/core/engine_collaborators.py`, and `autoloop/runtime/runner.py`.
- Lazy selection foundations already exist in `autoloop/core/context.py`, `autoloop/core/engine.py`, `autoloop/core/engine_collaborators.py`, `autoloop/core/worklists.py`, and checkpoint persistence.
- Ergonomic helper foundations already exist in `autoloop/core/effects.py`, `autoloop/core/routes.py`, `autoloop/core/validation_helpers.py`, and `autoloop/simple.py`.
- Inspection/static graph already distinguish authored routes, runtime-control routes, and provider visibility under interactive vs full-auto policy.
- The main remaining work is to close contract gaps, tighten error/reporting quality, and normalize tests around the new intentional break: no default provider-visible `blocked` or `failed`.

## Milestone A: Route Policy And Lazy Scoped Runtime

### Objective

Finalize provider-visible route semantics and lazy scoped runtime behavior so runtime-created data is validated only at first use, while provider/runtime failure ownership stays unchanged.

### Primary touchpoints

- `autoloop/core/providers/models.py`
- `autoloop/core/compiler.py`
- `autoloop/core/lowering.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/context.py`
- `autoloop/core/sessions.py`
- `autoloop/core/worklists.py`
- `autoloop/runtime/runner.py`
- `autoloop/runtime/static_graph.py`
- `autoloop/core/workflow_capabilities.py`

### Implementation slices

1. Provider route policy consolidation
- Keep `RuntimeInteractionPolicy` and `ControlRoutes` as the single policy path.
- Verify compiled and runtime-visible route lists never add default `blocked` or `failed`.
- Keep default `question` policy-gated through `allow_provider_questions`, with illegal provider `question` in full-auto continuing through the existing illegal-route retry/failure path.
- Keep `question` as the only hard-coded route payload rule; remove or reject any remaining hidden `blocked`/`failed` reason requirement paths.

2. Child workflow terminal mapping hardening
- Update `Engine._map_workflow_step_result(...)` so child `FAIL` and child await-without-question only map to `failed`/`blocked` when the parent step actually declares those routes.
- Emit a clear runtime error when a child terminal maps to an undeclared route, including step name, child terminal, mapped route, declared routes, and the fix.
- Preserve `done` default completion mapping and policy-aware `question` handling.

3. Lazy worklist materialization and scoped sequencing verification
- Keep fresh-run selections empty and resume restoration snapshot-driven only.
- Tighten `ensure_worklist_selection(...)` error shaping so failures identify worklist, source type/path when available, failure phase, and underlying error without loading unrelated worklists.
- Confirm all scope-sensitive entry points stay behind `ensure_selection(...)`: scoped step entry, `ctx.selection/current/item`, artifact template resolution, prompt rendering, and work-item session derivation.
- Keep checkpointing materialized selections only; maintain compatibility for missing/null `worklist_selections`.

4. Lazy work-item session continuity
- Preserve current `Continuity.work_item(...)` contract and `work_item` session-key domain.
- Ensure session resolution always materializes the referenced worklist before deriving the current item and uses `dir_key` before `id`.
- Improve the no-current-item failure message to match the requested contract and include the step name when available.

5. Inspection/static-graph parity
- Keep authored topology as the default graph view.
- Ensure static graph, topology, capability inspection, CLI payloads, and route tables consistently reflect authored routes, runtime-control routes, and interactive/full-auto provider visibility without implying default `blocked`/`failed`.
- Update any summaries or fixtures that still assume old reserved-route injection.

### Compatibility and intentional breaks

- Intentional break: default provider-visible `blocked` and `failed` go away everywhere; tests and generated inspection artifacts must be updated to the new contract.
- Compatibility to preserve: old checkpoints with absent or `null` `worklist_selections` must still resume as an empty lazy map.
- Compatibility to preserve: runtime/provider failure handling, retry behavior, artifact validation, and typed output validation remain runtime-owned and unchanged in principle.

### Validation

- Contract/runtime suites: `tests/contract/test_engine_contracts.py`, `tests/runtime/test_workspace_and_context.py`, `tests/runtime/test_runtime_static_graph.py`, `tests/unit/test_provider_boundary_core.py`.
- Add/adjust cases for:
  - interactive vs full-auto provider visibility
  - no default `blocked`/`failed`
  - explicit `blocked`/`failed` with no hidden reason requirement
  - child workflow undeclared mapped-route failures
  - lazy worklist restore/materialization/session continuity
  - static-graph and inspection parity

## Milestone B: Authoring Ergonomics And Validation/Inspection Polish

### Objective

Finish the authoring-facing flexibility work by aligning existing helper APIs with the requested behavior, without introducing a broader effects DSL or a second validation framework.

### Primary touchpoints

- `autoloop/core/effects.py`
- `autoloop/core/routes.py`
- `autoloop/core/validation_helpers.py`
- `autoloop/simple.py`
- `autoloop/core/discovery.py`
- `autoloop/core/artifacts.py`
- `autoloop/core/inventory.py`
- `autoloop/core/workflow_capabilities.py`
- `autoloop/runtime/static_graph.py`

### Implementation slices

1. Worklist effect alignment
- Keep the existing `Effects`/`WorklistEffect` surface instead of replacing it with a new effect API.
- Fill any missing normalization, constructors, or checkpoint/runtime-order guarantees needed to satisfy the requested worklist operations.
- Keep effect execution narrow: refresh, set/reset current status, advance, and exhausted-route control only.

2. Repairable validation helper alignment
- Extend the existing `ValidationResult` and `validation_step(...)` implementation in place.
- Ensure the helper's route behavior, feedback artifact writing, runtime events, deterministic feedback rendering, and optional failed-route path match the requested contract.
- Reuse existing structured-artifact validation utilities rather than duplicating schema logic.

3. Prompt placeholder late binding
- Reconcile compile-time simple-prompt validation in `autoloop/core/discovery.py` with runtime placeholder resolution in `autoloop/core/artifacts.py`.
- Preserve early validation for namespace/worklist/state typos.
- Allow late-bound scoped `item.*` and `worklist.<name>.*` runtime facts without requiring compile-time source existence or payload-subpath validation.
- Ensure runtime missing-item or missing-payload failures name the placeholder, step, worklist, and missing field/path.

4. Artifact ownership diagnostics
- Preserve compile-time ambiguity failure in `autoloop/core/inventory.py`.
- Tighten tests and message coverage only if needed so the diagnostic consistently includes artifact name, qualified name, workflow-level declaration, producer step names, and recommended fixes.

5. Inspection/docs polish limited to changed contracts
- Update inspection payload assertions and generated summaries only where the new runtime/prompt/effect semantics change author-facing interpretation.
- Do not broaden this phase into general docs or workflow-package refactors.

### Compatibility and intentional breaks

- Public helper APIs already in use should be extended in place, not replaced.
- If helper sugar differs from the spec's suggested names, preserve the repository's existing public names unless a failing contract requires additive aliases.

### Validation

- Contract/runtime suites: `tests/contract/test_engine_contracts.py`, `tests/runtime/test_runtime_static_graph.py`.
- Unit/authoring suites: prompt-validation tests, validation helper tests, worklist effect tests, and artifact-inventory validation tests.
- Add/adjust cases for:
  - effect returns from hooks/python steps
  - exhausted-route behavior
  - deterministic feedback rendering and failed-route fallback
  - late-bound prompt placeholders with runtime failure clarity
  - ambiguous workflow-level vs produced artifact ownership

## Regression controls

- Keep one source of truth for provider visibility: compiled route metadata plus runtime interaction policy. Do not duplicate full-auto checks elsewhere.
- Keep one source of truth for worklist materialization: `Context.ensure_selection(...)` delegating to engine state runtime.
- Keep child workflow mapping explicit; do not silently synthesize undeclared domain routes.
- Keep prompt validation split cleanly: compile-time typo detection in discovery, runtime value/path resolution in artifact/prompt rendering.
- Prefer additive tests in existing contract suites over new bespoke harnesses.

## Risk register

- Provider contract drift across compiler, engine, inspection, and CLI outputs.
  Mitigation: update all route-visibility payload producers together and assert parity in static-graph/inspection tests.
- Resume/session regressions from lazy worklist/session resolution.
  Mitigation: preserve snapshot format, add resume tests for missing/null selections, and keep work-item key derivation deterministic.
- Prompt validation loosened too far and silently hiding author typos.
  Mitigation: only relax runtime item/worklist payload subpaths; keep namespace, worklist-name, state-field, and syntax checks strict.
- Existing analytics/reporting fixtures still mention `blocked`/`failed` as domain routes.
  Mitigation: only change tests and fixtures that depended on default injection; leave unrelated run-history vocabulary untouched.

## Rollout and rollback

- Land Milestone A before Milestone B; do not mix authoring-surface polish into the runtime-semantics patch if A is not yet green.
- Roll back by reverting the milestone patch series in reverse order if provider contracts, pause/resume behavior, or session continuity regress.
- After each milestone, run the targeted contract/runtime suites before broader regression sweeps.
