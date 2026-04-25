# Pythonic Capability Upgrade Plan

## Goal
Implement the requested capability layer on top of the current class-based v3 runtime without drifting into a DSL, widening `workflow.toml`, or breaking the existing narrow provider control contract. The work must preserve current authoring patterns, package discovery, checkpoint/resume behavior, tracing, git tracking, and `ctx.invoke_workflow(...)` while adding artifact contracts, default sessions with explicit continuity, typed params, typed routes/effects, worklists, and typed child workflow IO.

## Current code seams
- `core/artifacts.py`, `core/validation.py`, and `core/compiler.py` currently treat artifacts as unqualified names with simple existence checks only; `Step.__getattr__` already exposes `step.artifact_name`.
- `core/engine.py` validates required inputs before step execution and validates `Outcome.payload`, but it does not validate produced files after route selection.
- `core/steps.py`, `core/context.py`, `core/stores/*`, and `runtime/stores/filesystem.py` still model provider continuity through `scope`; provider steps without a declared session currently run with no session at all.
- `workflow/__init__.py`, `workflow/primitives.py`, `core/__init__.py`, `extensions/__init__.py`, `core/workflow_capabilities.py`, and `runtime/cli.py` are part of the public or inspection-facing surface and must move in lockstep with the new primitives.
- Tests already cover validation, engine contracts, workspace/context behavior, capability inspection, strictness exports, optional extensions, and session-store payloads. Existing fixtures still exercise `ctx.open_session(..., scope=...)`, so the session migration must be explicit rather than silent.

## Compatibility guardrails
- Keep `expected_output_schema` scoped to `Outcome.payload`; artifact file validation is additive and happens after route resolution.
- Keep the runtime-injected provider contract narrow: `expected_output_schema`, `available_routes`, and `route_contracts`, with optional additive artifact contract metadata only.
- Preserve class-level `Artifact("{workflow_folder}/...")`, `produces={...}` handle exposure, deterministic compile caching, package discovery, CLI workflow references, and metadata-only `workflow.toml`.
- Do not add a flow-string parser, manifest-declared topology, hidden routing fallbacks, or generic effect/plugin infrastructure.
- Treat persisted session/checkpoint compatibility as a migration risk surface: new store keys and layouts are allowed, but upgraded runs must still checkpoint/resume correctly and the implementation should avoid avoidable reader breakage during transition.

## Interface targets

### Artifact contracts
- Extend `Artifact` with `kind`, `schema`, `required`, `owner_step`, and `qualified_name`, plus `text`, `md`, `json`, and `raw` factories.
- Split artifact identity into class-level and step-local records through compiled metadata rather than separate authoring types.
- Add compiled artifact metadata for `name`, `qualified_name`, `owner_step`, `template`, `kind`, `schema`, `required`, and `producer_steps`.
- Add `ArtifactHandle` helpers for `read_json`, `write_json`, `read_model`, `write_model`, `validate`, and existence/schema checks.

### Sessions and continuity
- Add `core/sessions.py` with `Continuity`, `SessionKey`, and `DEFAULT_SESSION_NAME`.
- Update `Session` to carry continuity instead of implicit scope semantics.
- Update session stores and runtime persistence around `SessionKey` + provider/session metadata, and remove workflow-facing `SessionPaths` exports.
- Preserve `ctx.open_session(...)` as the explicit override seam while moving runtime selection onto continuity policies and default-session auto-open behavior.

### Typed params, routes, worklists, and child IO
- Add `ctx.params` as the typed validated parameters model while preserving `ctx.workflow_params` as JSON-safe data.
- Add `Route` plus explicit effect dataclasses in dedicated modules; compile shorthand transitions onto the same normalized route table used by the engine and capability inspection.
- Add `WorkItem`, `Worklist`, `Selector`, and `Selection` as plain Python objects and use explicit engine effect dispatch instead of hidden looping.
- Extend `ChildWorkflowResult` and workflow conventions with optional typed `Input`, `Output`, and `build_output`.

## Ordered milestones

### 1. Artifact contract foundation
- Update artifact declarations, binding rules, compiled metadata, and validation resolution in `core/artifacts.py`, `core/steps.py`, `core/validation.py`, and `core/compiler.py`.
- Add step-local qualified-name resolution, schema gating, relative step-local path rules, and route-contract artifact-name resolution.
- Update capability/introspection surfaces that expose compiled artifact data.
- Validation: focused unit coverage for artifact factories, qualified names, ambiguity rejection, schema gating, and route-contract resolution.

### 2. Runtime artifact enforcement
- Add post-step artifact validation utilities in `core/engine.py` and fail provider/system steps before route completion when required outputs are missing, empty, or schema-invalid.
- Preserve current pre-step `requires` behavior and `Outcome.payload` validation order while adding route-specific required artifact enforcement and optional present-artifact schema validation.
- Ensure failure checkpoints capture artifact validation context.
- Validation: contract/runtime tests for missing/invalid required outputs, optional output handling, checkpoint persistence, and unchanged `expected_output_schema` semantics.

### 3. Session continuity and store migration
- Introduce `Continuity`, implicit default sessions, session auto-open, and `SessionKey`-based storage.
- Refactor `core/context.py`, `core/stores/protocols.py`, `core/stores/memory.py`, `runtime/stores/filesystem.py`, provider session persistence helpers, and runtime metadata/session files around the new key model.
- Remove workflow-facing `SessionPaths` exports and rewrite affected tests/docs/fixtures.
- Validation: unit and runtime coverage for default-session behavior, auto-open, continuity key shapes, store round-trips, and checkpoint/resume with the new snapshot structure.

### 4. Typed params and child workflow contracts
- Add typed parameter reconstruction on run/resume and thread both typed and JSON-safe parameter views through `Context`.
- Extend child invocation to accept typed input and to produce typed output while preserving existing metadata/artifact fields.
- Update CLI/runtime serialization and workflow capability inspection only where the typed contract becomes visible.
- Validation: runtime tests for parameter validation/restoration, child IO success/failure recording, and unchanged invocation compatibility by name and class.

### 5. Routes, effects, and worklists
- Add explicit route/effect dataclasses, worklist primitives, scoped-step declarations, selection APIs, and artifact placeholders.
- Normalize existing dict transitions onto compiled routes without changing simple workflow authoring.
- Implement engine-side effect dispatch explicitly and keep worklist progression opt-in through `Advance(...)`.
- Validation: compiler/engine/runtime coverage for shorthand compatibility, effect validation, scoped item selection, continuity by work item, and exhaustion behavior.

### 6. Public surface, docs, and full regression
- Update `workflow` and `workflow.primitives` exports, `core/__init__.py`, strictness tests, docs, examples, and any capability inspection/CLI payload assertions that depend on compiled metadata.
- Remove `SessionPaths` from workflow-facing docs and extensions exports, and state the new continuity/runtime-store boundary clearly.
- Run the full regression suite after phase-local coverage passes.
- Validation: `pytest -q` plus strictness/doc assertions for exports, metadata-only `workflow.toml`, and absence of DSL/manifests as execution surfaces.

## Regression risk register
- Artifact-name ambiguity: current inventory is keyed by unqualified names, so step-local support must introduce qualified metadata without breaking existing unqualified single-owner workflows. Mitigation: keep explicit compiler resolution rules and add ambiguity rejection tests before engine work.
- Session migration: `scope` is wired through context, stores, fixtures, and provider helpers. Mitigation: land continuity/store changes as one phase with end-to-end tests and explicit metadata/path assertions.
- Capability inspection drift: compiled metadata changes feed `core/workflow_capabilities.py` and CLI JSON payloads. Mitigation: update those surfaces in the same milestone that changes compiled artifacts/routes.
- Checkpoint/resume drift: artifact-validation failures and new session snapshots change failure paths. Mitigation: checkpoint assertions must cover fatal validation, pause/resume, and session snapshot contents.
- Over-engineering risk: routes/effects/worklists can sprawl into a generic engine. Mitigation: keep additive dataclasses plus explicit compiler/engine dispatch only for the requested effects and selectors.

## Rollout and rollback
- Ship phase-local tests before moving to the next milestone; artifact/compiler changes must stabilize before runtime/store changes build on them.
- Keep changes localized to existing modules unless a new module clearly owns a new public concept (`sessions.py`, `routes.py`, `effects.py`, `worklists.py`).
- If a milestone destabilizes runtime behavior, rollback to the prior milestone boundary by reverting the new compiled/runtime surface for that concept rather than layering temporary compatibility shims.
