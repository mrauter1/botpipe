# Autoloop v3 Authoring Simplification Plan

## Objective
Implement an additive `autoloop.simple` authoring surface that lowers into the existing deterministic compiler and engine, making tier-1 workflows concise without weakening current runtime guarantees, checkpointing, provider retries, artifact validation, or graph semantics.

## Hard Invariants
- Do not introduce a second runtime engine, source-generation path, or `autoloop eject`.
- Keep the existing strict `workflow` shim working during the migration window.
- Preserve deterministic compilation/execution, filesystem artifacts as truth, reserved routes, and provider retry behavior.
- Treat simple authoring as a normalization layer into current `core/*` concepts rather than as a parallel framework.

## Current Repo Constraints
- `core.Workflow` is strict today because `WorkflowMeta` validates at class definition time; current `workflow` shim exports that strict surface and strictness tests pin it.
- `route_contracts` currently drive validation, provider request payloads, provider rendering, static graph output, CLI metadata, bundled workflows, and many tests.
- Prompt resolution is already lazy at runtime via `PromptRegistry` and `FilesystemPromptRegistry`; that should be extended, not replaced.
- Artifact enforcement is currently route-contract-first, then artifact `required=True`; simple authoring must preserve that execution rule while renaming/publicly reframing the concept.
- `BoardMutation` still raises at runtime in `core.engine`; this is a known trap but not on the critical path for the authoring simplification.

## Implementation Strategy

### Milestone 1: Additive public surface and foundation types
- Add a new repo-root `autoloop/` package with `simple.py` so repo-root execution supports `from autoloop.simple import ...` without disturbing `workflow/__init__.py`.
- Keep `workflow` as the strict compatibility shim in the first pass; do not change its default behavior or exports until compatibility work is complete.
- Extend prompt types with explicit inline/file constructors and richer resolved metadata:
  - `Prompt.inline(text)`
  - `Prompt.file(path)`
  - `ResolvedPrompt(path: str | None, text: str, source: Literal["inline", "file", "registry"])`
- Add `RouteInfo` plus new `Route` metadata fields: `summary`, `required_outputs`, `handoff`.
- Add lightweight artifact helper constructors in the simple layer: `Json`, `Md`, `Text`, `Raw`.

### Milestone 2: Compiler, validation, and provider contract migration
- Introduce a prototype-validation path used by `autoloop.simple.Workflow`; retain strict metaclass validation for explicit strict workflows.
- Split step inputs into:
  - `reads`: readable but optional inputs
  - `requires`: hard input preconditions owned by the target step
- Extend compiled metadata to carry `reads`, `requires`, `route_infos`, `required_outputs`, `before`, `after`, and explicit control-schema state.
- Replace public/runtime-facing route-contract terminology with:
  - `route_infos`
  - `route_required_outputs`
  - readable/required/writable artifact groupings
- Keep temporary adapters so legacy `route_contracts` still normalize into the new compiled shape until bundled workflows/tests are migrated.
- Relax validation so application routes no longer require contracts/summaries, while still rejecting unknown route metadata and invalid required-output references.

### Milestone 3: Simple authoring lowering and graph inference
- Implement `autoloop.simple.Workflow` as a non-strict declaration surface that is lowered during `describe_workflow_class` / `get_workflow_definition` rather than validated at import time.
- Add `StrictWorkflow` as the explicit strict counterpart for class-definition-time validation.
- Introduce `EmptyState` synthesis when no nested `State` exists.
- Support simple helpers:
  - `step(...)`
  - `review_step(...)`
  - `system_step(...)`
  - `workflow_step(...)`
  - `chain(...)`
- Infer:
  - step names from assignment
  - entry from `flow`, single-step workflows, or a unique graph root
  - inline prompt usage for raw `str`
  - step-local artifact paths when a helper artifact omits `path`
  - prompt-placeholder reads when unambiguous
- Keep inference conservative: never infer requiredness from prompt placeholders and never auto-generate provider control schemas from artifact schemas.

### Milestone 4: Engine execution extensions
- Add step-level `before` / `after` hooks across provider, system, and child-workflow steps.
- Implement the requested ordering so `after` route overrides happen before final route-specific artifact enforcement and route effect application.
- Add `AfterHookResult` and normalize legal hook return shapes.
- Introduce `WorkflowStep` as a first-class compiled step kind with:
  - child workflow invocation through existing runtime machinery
  - child terminal-to-route mapping
  - optional result artifact emission
  - legal participation in verifier-gated rework loops
- Extend provider-turn payloads and rendering to expose readable inputs, required inputs, writable declared artifacts, route info, route-required outputs, optional control schema, retry feedback, and handoff text.

### Milestone 5: Compatibility migration, docs, and cleanup
- Migrate docs, examples, CLI/static-graph payload expectations, and bundled workflows from public `RouteContract` usage to route metadata / simple helpers.
- Keep legacy adapters internally until:
  - bundled workflows compile through the new normalization path
  - runtime/provider/static-graph tests are updated
  - strict/public docs no longer teach `RouteContract`
- Remove `RouteContract` from `autoloop.simple` immediately and from broader public exports only after compatibility fallout is closed.
- Treat compile-time rejection of unsupported public `BoardMutation` usage as optional low-risk cleanup after the main migration, not as a blocker.

## Interfaces To Add Or Change

### Public API
- New additive package:
  - `autoloop/__init__.py`
  - `autoloop/simple.py`
- `autoloop.simple` exports:
  - `Workflow`
  - `StrictWorkflow`
  - `step`
  - `review_step`
  - `workflow_step`
  - `system_step`
  - `chain`
  - `Json`
  - `Md`
  - `Text`
  - `Raw`
  - `Prompt`
  - `Route`
  - `RouteInfo`
  - `WorkflowStep`

### Core model changes
- `core.prompts`:
  - explicit inline/file constructors
  - resolved prompt source metadata
- `core.routes`:
  - `RouteInfo`
  - metadata-bearing `Route`
- `core.steps`:
  - add `reads`
  - rename explicit provider schema concept to control schema internally or keep alias with clarified semantics
  - add `before` / `after`
  - add `WorkflowStep`
- `core.validation`:
  - prototype vs strict validation path
  - simple-workflow lowering/discovery
  - relaxed route metadata requirements
  - prompt-placeholder read inference
- `core.compiler`:
  - compiled step/route metadata expansion
  - compatibility normalization from legacy route contracts
- `core.engine`:
  - hook execution ordering
  - workflow-step execution path
  - final-route enforcement after hook overrides
- `core.providers.models` / `rendering` / `fake`:
  - route-info and readable-input vocabulary
  - compatibility aliases during migration
- `runtime.static_graph` and CLI metadata payloads:
  - stop centering `route_contracts`
  - include new route metadata fields while remaining readable for compatibility tests during transition

## Compatibility Notes
- The strict `workflow` shim remains the authoritative current surface during the early phases; `autoloop.simple` is additive first.
- Current strictness tests pin `workflow.__all__` and root-shim behavior. Do not break those tests until the compatibility phase explicitly updates them.
- Bundled workflows under `workflows/*` currently import `Workflow`, `PairStep`, `SystemStep`, and `RouteContract` from `workflow`; they should continue compiling unchanged until their migration phase.
- Legacy `route_contracts` mapping support remains temporarily available internally so provider, static-graph, CLI, and bundled-workflow changes can land incrementally.
- Public docs should not jump to `autoloop.simple` until the runtime/compiler/provider path behind it is implemented end to end.

## Regression Controls
- Keep lowering centralized in validation/compilation so simple and strict workflows share the same compiled runtime path.
- Preserve existing required-output enforcement priority:
  1. selected route required outputs
  2. produced artifacts marked `required=True`
  3. no further obligations
- Preserve existing reserved-route semantics (`question`, `blocked`, `failed`) as runtime-understood routes.
- Do not change provider retry semantics except where hook-driven route overrides require final-route revalidation.
- Keep prompt-file resolution lazy and fail clearly only at compile/run time when a file is actually needed.

## Validation And Test Plan
- Add focused tests for:
  - simple workflow declaration, name inference, entry inference, `chain(...)`, and inline prompts
  - `Prompt.inline` / `Prompt.file` / `Path` prompt resolution
  - artifact helper defaults and schema-vs-control-schema separation
  - `reads` vs `requires`
  - route summary inference and unknown-route rejection
  - `review_step` default loop semantics
  - hook ordering and route overrides
  - `WorkflowStep` child execution and loop participation
  - prototype vs strict validation behavior
- Update existing tests that currently assert `route_contracts` payloads, static graph fields, or strict root authoring docs only when the compatibility phase reaches those surfaces.
- Re-run bundled workflow compilation/regression tests after each migration slice because those workflows currently depend heavily on route-contract normalization.

## Risk Register
- Public package naming risk: the repo does not currently expose an `autoloop` package. Mitigation: add `autoloop/` as an additive package under repo root and mirror existing fallback import patterns where needed.
- Compatibility risk: `route_contracts` is wired into many tests and bundled workflows. Mitigation: keep an internal adapter until migration is complete; do not remove the legacy surface early.
- Validation drift risk: simple-workflow inference could bypass strict invariants. Mitigation: simple declarations must lower into the same `WorkflowDefinition` / `CompiledWorkflow` path used today.
- Hook-order risk: `after` route overrides can invalidate pre-hook enforcement assumptions. Mitigation: move final route/artifact enforcement after hook normalization exactly once in engine flow.
- Child-workflow risk: `WorkflowStep` can create topology/loop regressions. Mitigation: compile it as a first-class step kind and validate it with the same route/topology checks rather than embedding it inside pair-step internals.
- BoardMutation trap risk: scope creep if fixed opportunistically. Mitigation: keep it as a follow-up unless compile-time fencing is trivial after the main migration lands.

## Rollback
- Each phase remains additive until the final compatibility cleanup; rollback is primarily disabling the new simple surface while leaving `workflow` and existing bundled workflows untouched.
- Any provider/static-graph payload renames should ship behind compatibility adapters first so rollback can preserve legacy serialized expectations without reverting engine behavior.
