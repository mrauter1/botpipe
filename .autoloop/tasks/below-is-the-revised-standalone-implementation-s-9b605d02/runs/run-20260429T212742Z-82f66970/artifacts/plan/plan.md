# Autoloop v3 canonical cleanup plan

## Scope

- Remove legacy public authoring names and dual internal field names in favor of the canonical surface from the request spec.
- Preserve compatibility only for persisted run-data readers when old checkpoints/run metadata must still resume correctly.
- Update compiler/runtime/provider/topology/docs/tests so emitted contracts use one vocabulary only.
- Finish optimizer separation so application-specific helpers live under `autoloop_optimizer`, not duplicated in `stdlib`.

## Codebase findings

- `autoloop/__init__.py` and `autoloop/simple.py` still export and accept legacy names such as `SUCCESS`, `StrictWorkflow`, `RouteInfo`, `chain`, `review_step`, `do_review_step`, `system_step`, `out`, `outputs`, `review_*`, `Param`, and `StateVar`.
- `core/primitives.py`, `core/routes.py`, `core/steps.py`, `core/compiler.py`, and `core/validation.py` still model the engine around `SUCCESS`, `required_outputs`, `route_infos`, `produces`, `PairStep`, `LLMStep`, `SystemStep`, class-level `flow`/`transitions`, descriptor-backed state, and `"default"` session naming.
- `runtime/static_graph.py`, provider-boundary tests, capability inspection, and run metadata still emit mixed legacy/canonical payloads instead of a single canonical schema.
- `runtime/loader.py`, docs, tests, `stdlib`, and optimizer helpers still depend on `Parameters`, route-info helpers, and legacy topology/output naming, so migration must be staged across authoring, compile, runtime, and consumer layers together.

## Canonical interfaces to land

- Public exports from `autoloop`: `Workflow`, `step`, `produce_verify_step`, `python_step`, `workflow_step`, `llm`, `classify`, `Prompt`, `Md`, `Json`, `Text`, `Raw`, `Route`, `Session`, `Continuity`, `Worklist`, `Event`, `Outcome`, `FINISH`, `PAUSE`, `FAIL`, `SELF`.
- Workflow state and params: `State = BaseModelSubclass`, `Params = BaseModelSubclass`; reject public `Parameters`, `StateVar`, and `Param`.
- Step primitives:
  - `step(..., prompt=..., requires=..., reads=..., writes=..., routes=..., session=..., control_routes=...)`
  - `produce_verify_step(..., producer_prompt=..., verifier_prompt=..., producer_writes=..., verifier_writes=..., verifier_requires=..., verifier_reads=..., verifier_session=..., state=BaseModelSubclass, control_routes=...)`
  - `python_step(...)` with return normalization `None -> "done"`, `str -> route`, `Event -> explicit payload`
- Route contract: `Route.to(target, summary=None, required_writes=None, handoff=None, on_taken=None)` plus optional `Route.finish(...)`; no `RouteInfo`, no positional effect DSL, no `required_outputs`.
- Topology/session contract: step-local `routes={...}` only, declaration order default entry, `global_session` as the public default session slot, canonical terminals `FINISH`, `PAUSE`, `FAIL`, `SELF`.

## Milestones

### 1. Public surface and simple authoring cleanup

- Replace `autoloop/__init__.py` exports with the canonical set only.
- Rename simple-surface declarations from compatibility-heavy names to canonical names:
  - `review_step`/`do_review_step` -> `produce_verify_step`
  - `system_step` -> removed public alias, `python_step` remains
  - `writes` only; remove `out`, `outputs`, and public `produces`
  - `producer_prompt` / `verifier_prompt`, `producer_writes` / `verifier_writes`, `verifier_requires`, `verifier_reads`, `verifier_session`
- Replace descriptor-mapping step state with `state=BaseModelSubclass`.
- Remove public `StrictWorkflow`, `WorkflowStep` class export, `AfterHookResult`, `Checkpoint`, `ResolvedArtifacts`, and `ChildWorkflowResult`.
- Update simple-surface unit tests to assert presence/absence on the new public contract.

### 2. Compiler, validation, and topology normalization

- Replace legacy internal names in compiled data structures and validation logic:
  - terminals: drop `SUCCESS`, canonicalize to `FINISH`
  - kinds: `"step"`, `"produce_verify"`, `"python"`, `"workflow"`, `"operation"`
  - fields: `writes`, `required_writes`, `routes`, `producer_*`, `verifier_*`
- Move workflow topology derivation to step-local routes plus declaration order and explicit `entry`; eliminate public `flow`, `transitions`, and `chain`.
- Replace `RouteInfo`-based metadata with `Route` as the single route metadata carrier.
- Replace descriptor-backed `StateVar`/`Param` discovery with `State` / `Params` Pydantic model validation; emit a clear compile-time error for `Parameters`.
- Rename session defaults from `"default"` to `"global"` in canonical compiled/output metadata while planning a reader-side normalization path for persisted legacy payloads.

### 3. Engine, provider, checkpoint, and artifact payload cleanup

- Update engine routing, child workflow mapping, hook lifecycle, artifact validation, and operation replay to use canonical step kinds, `FINISH`, and `writes`/`required_writes`.
- Split operation execution and provider payloads from route-bearing harness turns so `llm`/`classify` are always value-returning operations.
- Remove dual-emission payloads from provider contexts, static graph, topology artifacts, trace/run metadata, and compile reports.
- Add internal one-way readers for persisted run artifacts that still contain legacy terminals or legacy default-session naming when required for resume safety.
- Ensure topology hash, checkpoint serialization, and resume validation all key off the canonical compiled topology.

### 4. Repo-wide consumer migration and package cleanup

- Migrate docs, examples-in-docs, workflow packages, runtime fixtures, strictness tests, and contract/runtime/unit suites to canonical names only.
- Update capability inspection, provider-boundary tests, and optimizer/application helpers to consume `writes`, `required_writes`, canonical step kinds, and `Params`.
- Remove or relocate optimizer-specific helpers still duplicated under `stdlib`; keep generic helpers only in `stdlib`.
- Remove package alias/fallback behavior that exists only to sustain the old `core`/`autoloop_v3.core` dual surface, unless a concrete CLI packaging constraint still requires it after canonicalization.

### 5. Verification, regression controls, and rollout gate

- Add strict import and grep tests that fail on public legacy names and legacy emitted payload keys outside explicit migration fixtures/readers.
- Run focused suites covering simple authoring, validation, engine contracts, provider boundaries, static graph/topology, checkpoint/resume, workflow loading, and stdlib/optimizer inspections.
- Validate that resumed old run payloads normalize correctly where migration support is intentionally retained.
- Confirm topology artifacts, run results, and provider contracts contain no legacy public keys before acceptance.

## Compatibility and migration rules

- Keep compatibility only where old persisted run folders, checkpoints, trace payloads, or session bindings must still be readable to resume safely.
- Do not keep compatibility aliases in the public authoring/import surface, compiled topology, provider payloads, docs, or tests.
- `Parameters` is intentionally broken in public authoring; replacement is `Params`, with a compile-time error telling authors to rename.
- `StateVar` and `Param` are intentionally removed from public authoring; replacement is explicit Pydantic `State`, `Params`, and step `state=Model`.
- Class-level `flow`, `transitions`, and `chain` are intentionally removed from public authoring. If temporary lowering scaffolding is kept during refactor, it must remain internal and disappear from public docs/tests.

## Regression controls

- Land public/simple-surface cleanup before deep engine refactors so there is one canonical contract to drive subsequent renames.
- Change compiler structures before runtime artifact writers so runtime outputs can be migrated from one normalized source of truth.
- Treat topology hash, checkpoint shape, provider turn payloads, and child-workflow terminal mapping as high-risk surfaces; validate each with targeted tests before proceeding to repo-wide migrations.
- Keep reader-side legacy normalization narrow: terminals/session-slot names only unless a concrete persisted payload demands more.

## Validation plan

- Unit: `tests/unit/test_simple_surface.py`, `tests/unit/test_validation.py`, `tests/unit/test_provider_boundary_core.py`, `tests/unit/test_stdlib_and_extensions.py`, strictness scan tests.
- Contract/runtime: `tests/contract/test_engine_contracts.py`, `tests/runtime/test_runtime_static_graph.py`, `tests/runtime/test_provider_backends.py`, `tests/runtime/test_workspace_and_context.py`, `tests/runtime/test_compatibility_runtime.py`, `tests/runtime/test_runtime_git_tracking.py`, workflow loader/package tests.
- Grep/import checks: removed names absent from `autoloop`, removed emitted payload keys absent from active tree and topology outputs except in explicit migration-reader fixtures.

## Risk register

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Compiler/runtime rename drift | Mixed field names will corrupt topology, provider payloads, or validation. | Rename compiled structures first, then switch all artifact writers/provider renderers from the compiled model. |
| Resume breakage for existing run folders | Removing `SUCCESS`/`default` outright can strand persisted runs. | Add narrow reader normalization for persisted terminals/session slots before deleting runtime assumptions. |
| Authoring breakage wider than requested | Workflows, docs, and tests currently rely on `flow`, `transitions`, `Parameters`, and alias exports. | Stage consumer migration after canonical primitives exist; fail clearly on banned names rather than silently reinterpreting them. |
| Operation path regression | `llm`/`classify` currently piggyback on step lowering via `SystemStep`. | Separate operation compilation/execution and add dedicated replay/provider tests before removing old branches. |
| Optimizer/stdlib duplication | Leaving overlapping helpers behind preserves technical debt and inconsistent contracts. | Migrate consumers to `autoloop_optimizer`, then delete or shim only truly generic stdlib helpers. |

## Rollback

- Revert at phase boundaries rather than partial cherry-picks inside a renamed contract layer.
- If checkpoint/resume migration proves unsafe, keep the reader normalization change isolated and roll back public-surface removals until persisted payload coverage is restored.
- If topology/provider payload changes break downstream inspections, temporarily hold the writer switch while keeping the compiled canonical model intact; do not reintroduce public alias exports as a rollback mechanism.
