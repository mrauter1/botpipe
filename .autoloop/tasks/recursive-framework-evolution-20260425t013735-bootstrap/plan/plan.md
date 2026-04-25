# Recursive Framework Evolution Plan

## Scope And Baseline

- Authoritative source: the immutable request snapshot for `run-20260425T043735Z-6422224e`; no later clarification entries are present in the run log.
- Repository baseline:
  - `workflow` currently exports only the minimal strict authoring surface.
  - `core.artifacts.Artifact` supports only `template`, `name`, and `owner`; `ArtifactHandle` supports text reads/writes only.
  - `core.validation.collect_artifact_inventory(...)` and `core.compiler` assume a flat artifact namespace.
  - `core.route_contracts.RouteContract.required_artifacts` is normalized for provider/runtime inspection but is not runtime-enforced.
  - `Context` exposes only `workflow_params` dict access; `ChildWorkflowResult` exposes legacy metadata/output fields only.
  - Sessions are modeled as `ref_name + scope` with `active_scopes`; `ctx.open_session(ref, scope=...)` and positional `scope` are already valid and must remain valid.
  - `docs/architecture.md` still describes the framework as greenfield and under-specifies the compatibility guarantees now required by this request.

## Non-Negotiable Invariants

- Preserve existing workflow authoring style, package discovery, CLI flow, checkpoint/resume semantics, tracing, git tracking, extension isolation, and provider boundary semantics unless the request explicitly upgrades them.
- Keep `workflow.toml` metadata-only.
- Keep `ctx.open_session(session)` plus both `ctx.open_session(session, scope="x")` and `ctx.open_session(session, "x")` valid.
- Keep `produces={"name": artifact}` and `requires=[artifact]` valid.
- Keep `expected_output_schema` scoped to `Outcome.payload`; artifact schemas are separate file validation.
- Do not add a string flow DSL, manifest-defined topology, generic plugin bus, provider-specific workflow APIs, or hidden auto-routing/fallback on validation failure.

## Implementation Milestones

### 1. Artifact Declaration And Handle Upgrade

- Extend `core/artifacts.py` so `Artifact` carries `kind`, `schema`, `required`, `owner_step`, and `qualified_name`, plus `text/md/json/raw` factories.
- Extend `ArtifactHandle` with JSON/model helpers and add `ArtifactValidationResult` plus a shared validation helper.
- Keep existing plain `Artifact("{workflow_folder}/x.md")` declarations valid and default `required=False` to avoid forcing new failures into existing workflows.
- Reject unsupported schema placements at validation/compile time rather than deferring them to runtime.

### 2. Compiler Artifact Inventory And Reference Resolution

- Upgrade `core.validation` and `core.compiler` to build one normalized inventory covering workflow-level artifacts and step-local produced artifacts, including qualified names and producer ownership.
- Bind inline step-local artifacts during compilation so `step.artifact_name` stays available and relative step-local paths resolve under `{workflow_folder}/{step_name}/`.
- Add unqualified-vs-qualified artifact resolution rules for `requires` and `RouteContract.required_artifacts`, with explicit rejection of ambiguous names.
- Preserve deterministic compiled workflow caching by freezing/copying normalized artifact/session definitions into compiled structures.

### 3. Runtime Artifact Contract Enforcement

- Enforce route-selected artifact contracts in `core.engine`: validate route tag, validate `Outcome.payload`, run handlers, resolve selected route, then validate required artifacts before effects/commit.
- Required artifact source of truth:
  - route-specific `RouteContract.required_artifacts` when present
  - otherwise all produced artifacts with `Artifact.required=True`
  - optional produced artifacts validate only when present and schema-bearing
- Raise `ProviderExecutionError` for provider-owned step failures and `WorkflowExecutionError` for `SystemStep` failures; never auto-route to `needs_rework` or any other fallback.
- Ensure checkpoint payloads contain enough artifact-validation detail to diagnose failures without widening provider contracts.

### 4. Session Continuity And Store Migration

- Introduce `core/sessions.py` with `Continuity`, `SessionKey`, `SessionBinding`, and default-session semantics, while keeping the public authoring surface centered on `Session`.
- Update `Context`, `core.engine`, `core.stores.protocols`, `core.stores.memory`, and `runtime/stores/filesystem.py` to resolve sessions by slot plus continuity policy, with explicit `scope=`/`key=` overrides.
- Add the implicit `"default"` session for every compiled workflow and ensure provider-owned steps without an explicit session use it automatically.
- Preserve legacy `scope` behavior and load legacy persisted snapshots (`ref_name`/`scope`, `active_scopes`) during migration; new writes may move to `SessionKey`-based storage/snapshot shapes.
- Keep `extensions.SessionPaths` importable initially and treat it as a storage-path customization hook only.

### 5. Typed Workflow Parameters

- Extend `Context` to expose `ctx.params` alongside backward-compatible `ctx.workflow_params`.
- Update runtime parameter loading/persistence (`runtime/loader.py`, `runtime/runner.py`, `runtime/workspace.py`) so runs validate through the declared `Parameters` model, persist JSON-safe values, and reconstruct typed params on resume.
- Default to an immutable empty parameters model when a workflow does not declare one.
- Preserve the current rule that resumes use persisted params rather than replacing them with new overrides.

### 6. Typed Routes And Effects

- Add `core/routes.py` and `core/effects.py` for `Route`, `Refresh`, `ResetCompletion`, `SetStatus`, `Advance`, and `BoardMutation`.
- Normalize existing transition shorthand to compiled route objects without breaking current `step -> {"tag": SUCCESS}` style declarations.
- Validate effect references against declared worklists and execute effects only after artifact contracts have passed.
- Keep routing explicit; do not introduce hidden sequencing or implicit worklist loops.

### 7. Worklists And Scoped Execution

- Add `core/worklists.py` with `WorkItem`, `Selector`, `Selection`, `Worklist`, and artifact-backed worklist sources.
- Extend provider-owned steps with `scope=Worklist` and extend `Context` with `selection(...)`, `current(...)`, and `item`.
- Add item-aware artifact template placeholders and selection snapshots so scoped execution, session continuity, and checkpoint/resume remain deterministic.
- Make worklist progression explicit through `Advance(...)`; engine must not silently iterate the full collection.

### 8. Typed Child Workflow IO

- Extend workflow conventions to allow `Input`, `Output`, and `build_output(...)`.
- Extend `Context.invoke_workflow(...)` and `runtime.runner` to accept typed child input and return additive typed output on `ChildWorkflowResult`.
- Preserve current child-result metadata and path fields while adding `output`, `artifacts`, and `metadata` in a backward-compatible way.
- Record typed-output validation failures explicitly instead of silently dropping them.

### 9. Public Shim, Docs, And Regression Suite

- Update `core/__init__.py`, `workflow/__init__.py`, and `workflow/primitives.py` so the root shim exports only the authoring-facing primitives requested by the contract and keeps runtime internals out of the public surface.
- Update `docs/authoring.md` and `docs/architecture.md` to document default sessions, continuity, scoped overrides, artifact schemas/requiredness, typed params, routes/effects, worklists, and child IO, while explicitly preserving `workflow.toml` metadata-only behavior and `ctx.open_session(..., scope=...)`.
- Add/adjust unit, contract, runtime, and strictness tests for artifact inventory/enforcement, session continuity/default session behavior, typed params, route/effect normalization, worklists, child output, and updated docs/export constraints.
- Finish with full `pytest -q` regression coverage after focused phase-by-phase tests.

## Interface Delta Summary

- Root `workflow` exports become:
  - Core: `Workflow`, `Context`, `Session`, `Continuity`, `Artifact`, `Prompt`
  - Steps: `PairStep`, `LLMStep`, `SystemStep`
  - Routing: `Route`, `RouteContract`, `SUCCESS`, `PAUSE`, `FAIL`, `GLOBAL`
  - Effects: `SetStatus`, `Advance`, `Refresh`, `ResetCompletion`, `BoardMutation`
  - Work items: `WorkItem`, `Worklist`, `Selector`
- `workflow.primitives` becomes the home for low-level runtime values, including additive exports for `ChildWorkflowResult` once the typed child-result contract lands.
- New internal modules expected: `core/sessions.py`, `core/routes.py`, `core/effects.py`, `core/worklists.py`.
- Existing persistence/data contracts that change shape must be additive or backward-readable:
  - session snapshots/checkpoints
  - filesystem session paths
  - run metadata (`default_session`, `session_policy_version`, `worklists`)
  - child workflow result payloads/records

## Compatibility And Migration Notes

- Existing workflows without explicit `required=True` must continue to run.
- Existing route-contract metadata remains provider-visible and becomes runtime-enforced; provider prompt/runtime injection must stay limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- Existing persisted runs/checkpoints are a migration risk because session persistence currently stores `scope` and `active_scopes`; loaders should remain tolerant while writers migrate to the new key model.
- `SessionPaths` should not be promoted in docs/examples; it remains an advanced infrastructure seam only.
- Docs must explicitly replace the current “greenfield / backward compatibility is not a goal” framing where it conflicts with this upgrade contract.

## Regression Controls

- Phase-level validation:
  - run focused unit/compiler tests immediately after artifact and compiler changes
  - run contract/runtime tests after engine and session-store changes
  - run workspace/runner tests after params and child-workflow changes
  - run strictness/doc tests after public shim and docs updates
- Key invariants to assert throughout implementation:
  - route tags remain derived from transitions plus reserved routes
  - `expected_output_schema` validation remains payload-only
  - session provider boundary remains `session_id` plus `provider_metadata`
  - artifact failures do not introduce silent fallback routing
  - scoped session overrides affect later steps after `on_start`
  - deterministic compilation/cache behavior remains intact

## Risk Register

- Session persistence migration risk:
  - Impact: checkpoint restore or resumed runs could break if new snapshots are not backward-readable.
  - Control: support legacy `scope`/`active_scopes` inputs during restore; add focused resume/store tests before removing any old assumptions.
- Artifact namespace ambiguity risk:
  - Impact: flat existing inventories and new step-local qualified names can conflict in `requires` and route contracts.
  - Control: centralize artifact-name resolution in validation/compiler code and fail fast on ambiguity.
- Engine ordering risk:
  - Impact: validating artifacts before handlers or effects would break workflows that normalize/write artifacts in handlers.
  - Control: preserve the requested execution order and add explicit tests for handler-written artifacts.
- Child workflow compatibility risk:
  - Impact: adding typed IO could break downstream helpers expecting current fields.
  - Control: add new fields additively and preserve existing metadata/output/path fields until callers are migrated.
- Documentation drift risk:
  - Impact: new code may ship with docs and strictness assertions still describing the older narrower model.
  - Control: update docs/strictness in the final phase and treat doc/test failures as release blockers.

## Rollback Strategy

- Keep each phase internally coherent and mergeable so regressions can be isolated to one module cluster.
- If a late phase destabilizes runtime behavior, revert that phase’s public additions while preserving already-landed invariant-preserving groundwork.
- Do not delete compatibility loaders/readers for legacy session/checkpoint payloads until the full regression suite passes with the new model.
