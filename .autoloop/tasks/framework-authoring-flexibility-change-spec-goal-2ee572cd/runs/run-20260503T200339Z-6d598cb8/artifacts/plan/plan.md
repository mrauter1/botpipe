# Framework Authoring-Flexibility Implementation Plan

## Intent Lock

- Use the request snapshot as the implementation contract.
- Apply the intentional behavior break exactly as requested: remove default provider-visible `blocked`/`failed` routes and remove default `failed` injection for Python and child-workflow steps.
- Do not preserve compatibility shims for legacy default provider routes; update tests, inspection payloads, and docs to the new contract.
- Preserve runtime-owned failure handling, checkpointing, artifact validation, explicit authored `blocked`/`failed` routes, and explicit blocked run-status mapping.

## Code Seams Confirmed

- Route injection and simple-surface prompt validation live in `autoloop/core/discovery.py`.
- Execution-legal route sets are compiled in `autoloop/core/compiler.py` and consumed widely through `CompiledStep.available_routes`.
- Provider-visible route construction is centralized in `autoloop/core/engine_collaborators.py::ProviderContractBuilder`; payload validation and retry feedback live in `autoloop/core/engine.py`, `autoloop/core/providers/rendering.py`, and `autoloop/core/providers/retries.py`.
- Worklist startup/restore logic is currently eager in `autoloop/core/engine.py`; scoped-step dispatch is in `autoloop/core/engine_collaborators.py::StepDispatcher`; runtime access is in `autoloop/core/context.py`, `autoloop/core/worklists.py`, and `autoloop/core/artifacts.py`.
- Work-item session continuity resolves in `autoloop/core/sessions.py`.
- Artifact ownership metadata already exists in `autoloop/core/inventory.py` and is validated in `autoloop/core/topology.py`.
- Inspection/static graph payloads are produced in `autoloop/runtime/static_graph.py`, `autoloop/core/workflow_capabilities.py`, and surfaced via `autoloop/runtime/cli.py`.
- Public authoring exports are controlled by `autoloop/core/__init__.py`, `autoloop/simple.py`, and `autoloop/__init__.py`.

## Implementation Strategy

### Phase 1: Route Policy Rebase

- Add a small runtime interaction policy object and plumb it through `Engine` plus runner/config.
- Rebase reserved-route injection to `question`-only runtime control, with provider visibility gated by interaction policy.
- Remove hard-coded `blocked`/`failed` payload semantics from event/outcome validation, provider retry feedback, and provider prompt rendering.
- Keep `question` as the only reserved runtime route with a built-in non-empty-question requirement.
- Preserve `CompiledStep.available_routes` as the full execution-legal route set; add separate metadata for authored routes, runtime control routes, and provider-visible routes so execution, provider contracts, and inspection stay consistent.

Primary files:

- `autoloop/core/providers/models.py` or adjacent runtime-policy module
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/discovery.py`
- `autoloop/core/compiler.py`
- `autoloop/core/providers/rendering.py`
- `autoloop/core/providers/retries.py`
- `autoloop/runtime/runner.py`
- `autoloop/runtime/config.py`

Phase acceptance:

- Interactive provider-facing steps expose default `question`; full-auto runs do not.
- No provider request exposes default `blocked` or default `failed`.
- Python and child-workflow steps stop receiving default `failed`.
- Explicit authored `blocked`/`failed` routes still compile and execute without hidden reason requirements.
- Runtime provider failures still flow through retry/failure context, not through provider-authored `failed`.

### Phase 2: Lazy Worklist Materialization And Work-Item Sessions

- Replace eager fresh-run initialization with empty `selections` and sparse restore from checkpoint snapshots only.
- Add `Context.ensure_selection(...)` and `StateRuntime.ensure_worklist_selection(...)`; make `selection`, `current`, `item`, `current_worklist`, `WorklistRuntimeView.selection/current`, artifact template resolution, and scoped-step entry use the lazy seam.
- Emit a dedicated runtime event when a selection is first materialized.
- Update work-item session continuity to ensure the referenced selection exists before resolving the current item and to fail only at runtime when no current item exists.
- Keep checkpoint snapshots sparse: snapshot only materialized selections and never force-load missing ones during save or restore.

Primary files:

- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/context.py`
- `autoloop/core/worklists.py`
- `autoloop/core/sessions.py`
- `autoloop/core/artifacts.py`

Phase acceptance:

- Declared artifact-backed worklists compile without backing artifacts present.
- Unused worklists stay unloaded through compile, fresh start, resume, and checkpoint save.
- First scoped use, explicit `ctx.selection(...)`, explicit `ctx.worklist(...).selection/current/refresh`, and work-item continuity materialize exactly the referenced worklist.
- Missing or malformed sources fail at first use with targeted `WorkflowExecutionError` details.
- Scoped work-item continuity produces stable `<worklist>:<dir_key|id>` session keys and resumes them across checkpoints.

### Phase 3: Typed Worklist Effects And Repairable Validation Helper

- Add a narrow `autoloop/core/effects.py` surface with `WorklistEffect` and `Effects`.
- Extend `HookRunner.normalize_result(...)` and Python-step result normalization to accept `Effects`; execute refresh, status, advance, and exhausted routing through existing worklist runtime APIs/events.
- Keep route effects additive via helper constructors (`Route.advance(...)`, `Route.refresh(...)`, `Route.complete_current(...)`) or equivalent `on_taken` lowering; do not broaden `Route.to(...)` with a generic `effects=` kwarg.
- Add `ValidationResult` plus `validation_step` as a helper that lowers to existing Python-step machinery, writes deterministic feedback artifacts, and emits dedicated runtime events.

Primary files:

- `autoloop/core/effects.py` (new)
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/engine.py`
- `autoloop/core/routes.py`
- `autoloop/simple.py`
- `autoloop/core/__init__.py`
- `autoloop/__init__.py`

Phase acceptance:

- Hooks and Python steps can express refresh/status/advance/exhausted behavior without imperative glue boilerplate.
- Effects remain checkpoint-safe because they only mutate normal runtime state via current worklist APIs.
- `validation_step` routes valid results to success, invalid results to repair with feedback/handoff, and exceptions to explicit failed behavior or runtime error when no failed route exists.
- No new broad step DSL or new core step kind is introduced.

### Phase 4: Ownership Diagnostics And Late-Bound Prompt Context

- Add a compile-time diagnostic that rejects artifacts playing both workflow-level and produced roles on the same identity, while keeping current duplicate/ambiguous-name diagnostics for separate identities.
- Relax simple prompt placeholder validation only for declared late-bound item/worklist namespaces; keep typo protection for known roots, params/state/input fields, step names, and ambiguous artifact references.
- Make runtime prompt/artifact placeholder resolution lazily materialize referenced worklists and fail with placeholder-aware runtime errors when current items or payload paths are missing.
- Keep the relaxation narrow: unknown names must still fail at compile time.

Primary files:

- `autoloop/core/inventory.py`
- `autoloop/core/topology.py`
- `autoloop/core/discovery.py`
- `autoloop/core/prompt_validation.py`
- `autoloop/core/artifacts.py`
- provider prompt resolution call sites in `autoloop/core/engine.py`

Phase acceptance:

- Same-identity workflow-level plus produced artifact declarations fail with actionable guidance.
- Scoped prompts can reference `item.id`, `item.payload.<path>`, and `worklist.<name>.current...` without compile-time backing-data requirements.
- Non-scoped `item.*` references still fail unless explicitly supported by runtime worklist context.
- Runtime failures cite the placeholder and the missing current item/payload path/source problem.

### Phase 5: Inspection, Docs, And Regression Sweep

- Update inspection/static graph/capability payloads so they distinguish authored routes, runtime control routes, and provider-visible routes under interaction policy.
- Remove legacy assumptions about injected `blocked`/`failed` from static graph, route tables, compile reports, workflow capability payloads, and CLI inspection output.
- Update authoring docs to explain static-vs-runtime validation boundaries, lazy worklists, the new route policy, typed worklist effects, validation helper, and artifact ownership rules.
- Refresh regression suites across contract, runtime, unit, and docs tests.

Primary files:

- `autoloop/runtime/static_graph.py`
- `autoloop/core/workflow_capabilities.py`
- `autoloop/runtime/cli.py`
- `docs/authoring.md`
- `docs/architecture.md` and doc-backed tests if needed
- affected tests in `tests/contract`, `tests/runtime`, `tests/unit`, and doc baseline suites

Phase acceptance:

- Inspection surfaces show policy-aware provider-visible routes and no default `blocked`/`failed`.
- Static graph marks internal `question` as runtime control rather than an authored domain edge.
- Documentation matches the shipped runtime behavior and passes doc baseline tests.
- The minimum regression suite from the request snapshot passes with updated expectations.

## Interface Changes

### Public / Runtime

- `RuntimeInteractionPolicy(allow_provider_questions: bool = True)` added near provider/runtime models.
- `Engine(..., interaction_policy: RuntimeInteractionPolicy | None = None)` defaults to interactive mode.
- `RuntimeConfig.full_auto: bool = False` and runner plumbing added if the runtime does not already expose a workflow-level full-auto control.
- Existing provider transport auto flags remain separate from workflow interaction policy; do not conflate Codex CLI auto-approval flags with route visibility.

### Authoring

- Add `ControlRoutes(question="auto" | "always" | "never")` for step-level runtime-control intent.
- Preserve existing `control_routes=False` semantics by mapping it to “no injected question route”; do not preserve legacy `blocked`/`failed` injection.
- Add `Context.ensure_selection(...)`.
- Add `Effects`, `WorklistEffect`, `Route.advance(...)`, `Route.refresh(...)`, `Route.complete_current(...)`, `ValidationResult`, and `validation_step`.

### Internal / Compiled

- Keep `CompiledStep.available_routes` as the execution-legal route set.
- Add compiled or derivable metadata needed to answer three separate questions consistently:
  - what the author declared,
  - what runtime control edges exist,
  - what the provider may currently see under a given interaction policy.

## Compatibility Notes

- Intentional break: provider-facing steps lose default `blocked` and `failed`; Python and child-workflow steps lose default `failed`.
- Intentional break: provider retry copy and provider prompt instructions stop treating `blocked`/`failed` as reserved special payload shapes.
- Additive change: if no runtime-level `full_auto` workflow setting exists today, introducing one is necessary to satisfy the requested runner semantics; default it to `False` to preserve current interactive behavior.
- Additive change: new inspection/static graph fields may require updating snapshot tests and any downstream tooling that assumed `available_routes` alone described provider-visible routes.
- Preserve explicit authored `blocked` behavior so existing blocked-status run metadata remains valid when a workflow still authors that route.

## Regression Guardrails

- Do not widen prompt placeholder relaxation beyond the namespaces named in the request.
- Do not materialize all worklists during compile, run start, resume, checkpoint save, or unrelated error reporting.
- Route validation must continue to reject illegal routes and invalid structured payloads; only the hard-coded `blocked`/`failed` reason rule is removed.
- Effects must reuse existing worklist mutation/event paths instead of introducing a second state mutation mechanism.
- `validation_step` must lower to existing Python-step execution rather than adding a new step abstraction.
- Keep `Route.to(..., effects=...)` unsupported; existing tests currently reject that kwarg and the request does not require loosening it.

## Validation Plan

- Route policy: update canonical provider-contract, provider-boundary, simple-surface, and engine contract tests that currently expect `question`/`blocked`/`failed`.
- Lazy worklists: cover compile/start/resume/snapshot behavior in engine contract tests plus low-level context/worklist unit tests.
- Work-item continuity: add session-key tests around scoped and non-scoped resolution in engine contracts and session unit tests.
- Effects and validation helper: add unit/contract coverage for hook normalization, route helper lowering, checkpoint safety, feedback artifact writing, and exception paths.
- Ownership and prompt context: add validation tests for same-identity dual-role artifacts, ambiguous-name diagnostics, scoped vs non-scoped placeholders, and runtime placeholder failures.
- Inspection/docs: update static graph, workflow capability, CLI inspection, and doc baseline tests to the new route model.

## Risk Register

- Risk: route-view drift between compile metadata, provider contracts, and inspection payloads.
  Mitigation: derive provider-visible and runtime-control views from a single compiled source of truth; add snapshot coverage for both interactive and full-auto policies.
- Risk: lazy worklists break scoped item state, artifact template resolution, or checkpoint resume.
  Mitigation: centralize lazy selection in `Context.ensure_selection(...)`, make dispatcher materialize scoped worklists explicitly, and keep sparse snapshot tests for fresh and resumed runs.
- Risk: prompt-validation relaxation admits real typos.
  Mitigation: keep validation strict for unknown roots, worklist names, step names, and field namespaces; relax only the runtime-created item/worklist payload paths named in the request.
- Risk: helper additions create a second authoring model.
  Mitigation: keep effects narrow, keep `validation_step` as a lowering to Python step, and avoid adding a general DSL or generic route-effects kwarg.

## Rollback Posture

- Phase rollback should be cleanly sliceable by concern: route policy, lazy worklists/session continuity, helper additions, diagnostics/prompt relaxation, and inspection/docs.
- If a late phase regresses behavior, prefer reverting only the additive helper or payload-surface change while keeping already-stable route/worklist runtime fixes in place.
