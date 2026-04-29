# Full Revised Autoloop v3 Redesign Plan

## Objective

Implement the revised public authoring model by lowering it into the existing compiled FSM and runtime first. Preserve current execution reliability, checkpointing, provider retries, child workflow behavior, and run artifacts while shrinking the public surface and moving policy decisions into hooks/functions instead of DSL rules.

## Current Baseline

- `autoloop.simple` already lowers a convenience surface into `core` through `core.validation.describe_workflow_class(...)`.
- The strict runtime is still centered on `SUCCESS`, global `transitions`, `RouteInfo`, `produces`, `PairStep`/`LLMStep`/`SystemStep`, and `static_step_graph.json`.
- Simple step-local `routes` exist, but they are partial: route metadata is split across `Route` and `RouteInfo`, prompt-read inference is narrow, control routes are always injected, entry inference is heuristic, and output naming remains `produces` internally/publicly in many places.
- Ordering still depends partly on module-level counters in `core.steps`, which is a concurrency and determinism risk for the redesign.
- Compatibility pressure is high: runtime tests, docs, CLI inspect output, workflow packages, and static graph payloads still assert legacy names and terminals.

## Non-Negotiable Invariants

- Keep the runtime as a compiled FSM with explicit normalized routes.
- Lower new authoring declarations into the current compiler/runtime before deeper refactors.
- Enforce only execution invariants called out in the request.
- Do not add a second large public topology or route-effect DSL.
- Do not silently break resume, replay, route legality, artifact validation, child workflow behavior, or the persisted run/audit surfaces.
- Treat intentional behavior breaks as explicit migration items, not incidental fallout.

## Canonical Public Surface To Reach

```python
Workflow

step
do_review_step
python_step
workflow_step

llm
classify

Prompt
Md
Json
Text
Raw

Route
Session
Continuity
StateVar
Param

FINISH
PAUSE
FAIL
SELF
```

Compatibility retained during migration:

- `SUCCESS = FINISH`
- `review_step = do_review_step`
- `system_step = python_step`
- `out` and `outputs` accepted as deprecated aliases for `writes`
- global `transitions` and `flow` remain fallback inputs until cleanup
- `RouteInfo`, `StrictWorkflow`, `chain`, public `reads`, and public `produces` remain compatibility paths until cleanup, but public docs/examples/templates leave those surfaces immediately

## Milestones

### Phase 1: Canonical Surface, `python_step`, Prompt Model, And Topology Lowering

Scope:

- Add public constants `FINISH` and `SELF` while preserving `SUCCESS` aliasing.
- Introduce `@python_step(...)` as the canonical public Python-step declaration, keep `system_step = python_step` as a deprecated alias, and normalize the requested return contract: `None -> "done"`, `str -> route tag`, `Event(...)` only when control payload is needed.
- Make step-local `routes={...}` the canonical public topology source for `step(...)`, `python_step(...)`, and `workflow_step(...)`.
- Add `writes=` as the public output surface and `required=` on simple artifact helpers, with `out`/`outputs` accepted as deprecated inputs.
- Add the canonical prompt surface: `Prompt.inline(...)`, `Prompt.file(...)`, and `Prompt.ref(...)`, with explicit docs/examples preferring `Prompt.file(...)` over suffix heuristics.
- Add compiler support for the phase-1 prompt reference contract: `{step.artifact}`, `{self.artifact}`, `{step.value}`, `{params.field}`, bare artifact names only when globally unambiguous, inferred `reads` from prompt references, and compile/preflight failures for unknown or ambiguous placeholders when prompt text is available.
- Collapse target normalization so strings, direct step refs, terminals, `SELF`, and `Route.to(...)` lower into one route path.
- Replace module-counter-driven topology ordering with class namespace order for authoring discovery and compiled entry/default-next resolution.
- Generate richer topology artifacts beside the existing static graph, but keep legacy static graph emission until consumers migrate.
- Move public docs/examples/templates to the canonical API in this phase so new authoring guidance stops reinforcing the legacy surface while compatibility remains available for existing code.

Primary modules:

- `autoloop/simple.py`
- `autoloop/__init__.py`
- `core/primitives.py`
- `core/routes.py`
- `core/steps.py`
- `core/validation.py`
- `core/compiler.py`
- `core/prompts.py`
- `runtime/static_graph.py`
- `runtime/cli.py`
- docs/tests/template surfaces that publish the public API

Key implementation notes:

- Prefer extending the existing simple-lowering path in `core.validation` instead of introducing a second compiler entrypoint.
- Keep `python_step` as a thin lowering over the current system-step machinery first; do not build a parallel step runtime just to rename the public surface.
- Introduce canonical compiled route/step metadata names without breaking current provider and engine callers in the same change.
- Keep prompt reference compilation additive first: phase 1 covers artifact/value/params-oriented namespaces and ambiguity checking, while phase 3 extends state/item/meta-backed namespaces once those public surfaces exist.
- Keep global `transitions` as a fallback input only; do not let it override explicit step-local routes silently.
- Keep `done` lowercase as the default step route tag and treat `FINISH` only as a terminal.

Regression controls:

- Add focused tests for `FINISH` aliasing, `SELF`, `python_step` declaration style, `system_step` aliasing, return normalization, step-local route targets, string forward refs, explicit entry, first-declared entry, custom semantic routes, and control-route opt-out/override.
- Add compiler tests for prompt declaration forms, prompt reference inference, bare-name ambiguity failures, unknown-placeholder failures, reserved phase-1 namespaces, and `reads` remaining an escape hatch rather than the primary path.
- Update static graph/inspect tests and docs/tests/templates so canonical topology artifacts and canonical authoring guidance are added without regressing existing runtime outputs during migration.

### Phase 2: `do_review_step` And Route-Scoped Output Contracts

Scope:

- Introduce `do_review_step(...)` as the canonical paired agentic step and retain `review_step` aliasing.
- Rename public prompt fields to `do` and `review`, with `producer`/`verifier` accepted temporarily.
- Separate `writes` and `review_writes`, `requires` and `review_requires`, and `session` and `review_session`.
- Support route-level `required_writes` across both do and review artifacts.
- Keep the runtime order explicit: do phase, review phase, route resolution, hook execution, selected-route validation, checkpoint, transition.

Primary modules:

- `autoloop/simple.py`
- `core/steps.py`
- `core/validation.py`
- `core/compiler.py`
- `core/engine.py`
- `core/providers/models.py`
- `core/providers/rendering.py`
- `core/providers/parsing.py`

Key implementation notes:

- Reuse current `PairStep` machinery first by extending compiled metadata, then split provider contracts and validation where required.
- Do not make all do-phase writes implicit hard preconditions for review.
- Preserve current retry behavior unless the request requires phase-specific refinement.

Regression controls:

- Add contract/runtime tests for separate do/review prompts, default review routes, custom review routes, review-specific required writes, missing review artifacts, and child-workflow parity.

### Phase 3: Hook Contract, State/Params Surface, Sessions, Prompt Namespaces, And Resume-Safe Topology Metadata

Scope:

- Add `StateVar` and `Param` descriptors for workflow and step state without replacing existing `State`/`Parameters` compatibility paths in the same slice.
- Expand context to organized public surfaces: `ctx.state`, `ctx.step_state`, `ctx.item_state`, `ctx.step_item_state`, `ctx.values`, `ctx.artifacts`, `ctx.params`, `ctx.run`, `ctx.workflow`, `ctx.session`, `ctx.meta`, `ctx.route`, `ctx.outcome`.
- Extend prompt-reference compilation from phase 1 into the requested stateful/runtime namespaces: `{state.field}`, `{step.state.field}`, `{item.state.field}`, `{step.item_state.field}`, `{run.id}`, `{workflow.folder}`, and reserved pseudo-fields such as `value`, `state`, `item_state`, and `meta`.
- Add explicit hook slots: `before`, `after`, `on_route`, route-level `on_taken`, plus do/review hook variants.
- Add workflow-level global session semantics, including `global_session = Session(...)`, provider-backed default session selection, `review_session`, and session helpers for global-session reset/set/open behavior, then checkpoint the resulting session state deterministically.
- Emit hook lifecycle events and persist stable topology hash/source hash/entry metadata into run artifacts; fail resume when topology mismatches.

Primary modules:

- `core/context.py`
- `core/engine.py`
- `core/compiler.py`
- `core/validation.py`
- `core/stores/*`
- `runtime/workspace.py`
- `runtime/runner.py`

Intentional behavior break in this phase:

- Remove route redirection as a supported hook return behavior for the new hook surface. Existing after-hook route overrides are incompatible with the requested contract and should be retired deliberately, with tests and docs updated in the same phase.

Key implementation notes:

- Keep state/session mutation transactional and artifact writes atomic where current helpers already make that possible.
- Preserve existing worklist support; simplify the common path without deleting board machinery.
- Expand topology artifacts from the current `static_step_graph.json` baseline to `topology.json`, mermaid, route table, prompt refs, artifact/state/session contracts, and compile report.
- Keep prompt-reference validation split cleanly: phase 1 owns prompt declaration forms and basic artifact/value/params resolution, while phase 3 owns the new state/session/item/meta-backed namespaces that depend on this phase's context surface.

Regression controls:

- Add tests for hook execution order, hook failure checkpointing, state persistence, global-session defaulting, session reset/set persistence, topology-hash resume guard, extended prompt pseudo-fields, and state/item/runtime placeholder resolution.

### Phase 4: Feedforward `llm()` / `classify()` Operations

Scope:

- Add standalone `llm(...)` and `classify(...)` runtime operations plus `.step(...)` authoring helpers.
- Add a value-returning provider operation path distinct from route-oriented step execution.
- Add deterministic operation fingerprinting, retry, replay, and mismatch failure behavior.
- Support operation usage inside `python_step` and helper functions without implicit classifier routing.

Primary modules:

- `autoloop/__init__.py`
- `autoloop/simple.py`
- `core/providers/protocols.py`
- `core/providers/models.py`
- `core/providers/retries.py`
- `core/engine.py`
- runtime trace/checkpoint/replay artifacts

Key implementation notes:

- Keep the implementation narrow and reuse existing retry/parsing infrastructure where possible.
- Only introduce a small dedicated operation-recording module if existing runtime/provider modules become materially harder to reason about without it.
- Keep `classify.step(...)` as a value node; route selection stays explicit through a visible Python step or equivalent later helper.

Regression controls:

- Add tests for standalone calls, `.step(...)`, retry-on-parse/schema/choice failure, replay hit, fingerprint mismatch failure, and `python_step` integration.

### Phase 5: Bundled Workflow Migration, Stdlib Separation, And Compatibility Cleanup

Scope:

- Finish migrating bundled workflows, prompts, inspect expectations, and remaining compatibility-era docs/examples that were not part of the phase-1 canonical public-guidance switch.
- Move optimizer/application-specific stdlib material out of framework core into `autoloop_optimizer` or equivalent sibling package layout inside the repo.
- Demote the public route-effect DSL and legacy surface from docs; keep only the minimal compatibility bridges still needed by tests or transition tooling.
- Remove or fence deprecated public exports after migrated workflows/tests no longer depend on them.

Primary modules:

- `docs/*`
- `workflows/*`
- `stdlib/*`
- package exports and compatibility tests

Key implementation notes:

- Keep the docs/examples sequencing split explicit: phase 1 changes the canonical public guidance immediately, while phase 5 handles mechanical bundled-workflow migrations and final deprecation cleanup.
- Make this phase mostly mechanical and documentation-driven; do not hide unresolved runtime contract issues inside cleanup.
- Prefer deleting compatibility shims only after the affected tests and bundled workflows prove the canonical path end to end.

Regression controls:

- Full pass over docs tests, strictness tests, workflow integration/runtime suites, and package/CLI inspect surfaces.

## Cross-Cutting Interface Decisions

- Keep `core` as the runtime kernel; do not create a second runtime package for the redesign.
- Normalize new public names at the edge, then lower to compiled metadata the engine can already execute.
- Keep legacy field names readable in compatibility paths, but shift new compiled/reporting artifacts to canonical names as soon as feasible.
- Preserve existing route `effects` internally for advanced compatibility, but do not extend or document them as the public policy surface.
- Keep `workflow_step` and worklists intact; top-level parallel FSM execution remains out of scope.

## Compatibility And Migration Notes

- `SUCCESS` remains accepted while run results and topology artifacts migrate to `FINISH`; run result payloads should carry terminal and last route distinctly.
- `static_step_graph.json`, CLI inspect output, and compiled capability payloads currently expose `produces` and `route_required_outputs`; migrate them in additive form first, then retire old keys in cleanup.
- Existing strict-core workflows using `transitions`, `RouteInfo`, and `PairStep` must continue to compile until cleanup completes.
- Existing docs currently assert the old surface. Switch canonical public docs/examples/templates in phase 1 so new authoring stops drifting back to `StrictWorkflow`, `chain`, `system_step`, or global `transitions`, while bundled workflow packages can finish migrating in phase 5.
- `system_step` remains a deprecated alias, but the implementation target is the `python_step` decorator surface and the simplified return contract requested by the spec.
- Prompt-model migration is split intentionally: phase 1 lands canonical prompt declaration forms and artifact/value/params placeholder semantics, and phase 3 adds the state/item/meta/runtime namespaces that depend on the new context/state surfaces.

## Validation Strategy

- Unit: `tests/unit/test_validation.py`, `tests/unit/test_simple_surface.py`, provider retry/parsing tests, stdlib/extension tests that inspect compiled metadata.
- Contract: `tests/contract/test_engine_contracts.py` for route legality, hook behavior, required outputs/writes, sessions, child workflows, pause/fail semantics, and Python-step return behavior.
- Runtime: `tests/runtime/test_runtime_static_graph.py`, compatibility/runtime provider suites, workspace/resume suites, built-in workflow end-to-end tests, CLI inspect/package tests, and prompt reference/runtime contract coverage.
- Docs/strictness: `tests/test_architecture_baseline_docs.py` and `tests/strictness/test_no_compat.py`.
- Each phase should land with its own targeted regression tests before starting the next phase.

## Risk Register

- Terminal rename drift.
  Impact: inconsistent run artifacts, static graph payloads, provider expectations, and tests.
  Mitigation: add canonical `FINISH` while preserving `SUCCESS` alias until cleanup; update runtime/result serialization centrally.

- Ordering and entry determinism drift.
  Impact: silent topology changes, resume mismatch, cross-run nondeterminism.
  Mitigation: move to class namespace order in validation/compilation and persist topology hash before enabling resume enforcement.

- Route metadata split/merge errors.
  Impact: wrong required-write enforcement or wrong provider route contract.
  Mitigation: normalize all route metadata in one place and cover step-local, global fallback, and legacy `RouteInfo` compatibility cases.

- Prompt reference drift.
  Impact: ambiguous or unresolved placeholders can compile or render differently across authoring modes, causing hidden context loss or invalid reads.
  Mitigation: phase prompt support explicitly, validate prompt references at compile/preflight time when possible, and cover ambiguity/unknown cases in unit and runtime tests.

- Hook migration breakage.
  Impact: existing after-hook route override behavior could disappear unexpectedly.
  Mitigation: make the break explicit in phase 3, update affected tests/workflows in the same slice, and do not silently preserve redirect semantics under the new API.

- Docs/examples sequencing drift.
  Impact: new workflows keep copying the legacy surface even while the runtime migrates, increasing future cleanup cost and public/API confusion.
  Mitigation: switch public docs/examples/templates in phase 1 and confine later doc work to remaining bundled-workflow migration and compatibility cleanup.

- Session semantics drift.
  Impact: changing global-session defaults or review-session overrides can break replay/resume determinism or provider continuity unexpectedly.
  Mitigation: land global-session semantics with explicit checkpoint/resume coverage and additive compatibility behavior before removing any old assumptions.
