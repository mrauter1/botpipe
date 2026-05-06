# Plan

## Goal
Implement the standalone route-helper / GLOBAL-default / structured-provider-outcome spec by making compiled routes the only source of truth for route legality, provider visibility, route schemas, and execution metadata.

## Current implementation snapshot
- Route behavior is split today across authored transitions plus a separate runtime-control injection path in `autoloop/core/discovery.py`, `autoloop/core/lowering.py`, and `autoloop/core/compiler.py`.
- `Route` only carries target/summary/required_writes/handoff/on_taken plus boolean `provider_visible`; it has no payload-schema, route-fields-schema, preset-kind, or disabled/inheritance metadata.
- `Outcome` and rendered-provider parsing still use top-level `tag` / `payload` plus special-case `question` / `reason`, and engine validation still hard-codes `question` payload rules in `autoloop/core/engine.py`.
- Provider prompts, static graph, compile report, workflow capabilities, and topology hash all still expose authored-versus-`runtime_control_routes` concepts instead of compiled inherited route metadata.
- `simple.py`, `autoloop/__init__.py`, workflow docs, and existing tests still treat `ControlRoutes(question=...)` and the narrow control-route contract as the public model.

## Phased implementation plan

### Phase 1: Route metadata model and compilation unification
Target modules:
- `autoloop/core/routes.py`
- `autoloop/core/steps.py`
- `autoloop/core/discovery.py`
- `autoloop/core/lowering.py`
- `autoloop/core/compiler.py`
- `autoloop/core/topology.py`

Implementation intent:
- Extend `Route` with helper constructors and metadata required by the spec:
  - `Route.question()`, `Route.blocked()`, `Route.failed()`, `Route.hidden()`, `Route.disabled()`
  - payload-schema mode helpers `Route.inherit_payload_schema()` and `Route.no_payload_schema()`
  - normalized `provider_visibility` modes: `"hidden"`, `"interactive_only"`, `"always"`
  - route-fields schema, preset kind, and disabled marker
- Keep boolean `provider_visible` as a compatibility input only; normalize it immediately into the new visibility enum.
- Replace `_inject_control_routes()` and `runtime_control_routes_by_step` as the legality mechanism with one compiled route-resolution pass:
  - step-local routes override inherited routes by tag
  - workflow `GLOBAL` routes provide explicit defaults
  - framework default profile exists only for compatibility lowering
  - `Route.disabled()` suppresses inherited routes before available/provider-visible route sets are computed
- Lower legacy `ControlRoutes(question="auto" | "always" | "never")` into framework-default `Route.question()` inheritance only; do not add blocked/failed knobs and mark the surface deprecated in docs.
- Extend `CompiledRoute` to carry the canonical route contract:
  - target
  - summary
  - required writes
  - handoff
  - on_taken
  - provider visibility mode
  - payload-schema mode/schema/validator
  - route-fields schema/validator
  - preset kind
  - inheritance source
  - suppressed/disabled state when relevant to reports
- Preserve route finalization semantics and hook ordering; this phase only changes how the route table is compiled and described.

### Phase 2: Provider contract generation, parsing, and validation
Target modules:
- `autoloop/core/providers/models.py`
- `autoloop/core/providers/rendering.py`
- `autoloop/core/providers/parsing.py`
- `autoloop/core/providers/rendered.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/engine.py`

Implementation intent:
- Make provider-visible routes come only from compiled routes filtered by interaction policy:
  - interactive mode: `"interactive_only"` + `"always"`
  - full-auto mode: `"always"` only
  - hidden/disabled/absent routes are illegal
- Replace top-level control-response prompting with canonical `{"outcome": {...}}` rendering and per-route schema disclosure:
  - `outcome.tag`
  - `outcome.payload`
  - `outcome.route_fields`
- Generate provider JSON Schema from provider-visible compiled routes using the nested-`anyOf` branch form required by the spec, with strict object envelopes and per-route payload/route-fields schemas.
- Add simplified provider-schema fallback when route-discriminated schema size/complexity exceeds backend limits, while preserving full post-parse validation.
- Extend `Outcome` with `route_fields` and keep compatibility accessors/projections for `reason` and `question`.
- Parse both canonical and legacy provider outputs:
  - canonical envelope preferred
  - legacy top-level `tag` / `payload` / `question` / `reason` accepted during migration
  - canonical `route_fields` wins when both canonical and legacy fields are present
  - omitted `payload` / `route_fields` normalize to `{}` only in legacy/non-strict handling
- Move provider-attributable validation onto compiled selected-route metadata:
  - malformed envelope -> `malformed_provider_output`
  - hidden/disabled/full-auto-hidden/unknown route -> `illegal_route`
  - payload mismatch or route-fields mismatch -> `invalid_payload`
  - question-style routes require non-empty `route_fields.questions`
- Keep direct/scripted `Outcome(...)` objects and rendered-provider JSON on the same legality and schema-validation path.

### Phase 3: Runtime projection, inspection metadata, and topology/report alignment
Target modules:
- `autoloop/core/primitives.py`
- `autoloop/core/engine.py`
- `autoloop/core/workflow_capabilities.py`
- `autoloop/runtime/static_graph.py`
- `autoloop/core/compiler.py` hash/report payloads
- `docs/architecture.md`
- workflow docs and prompt READMEs that describe provider/control routing

Implementation intent:
- Treat route metadata, not tag name alone, as the behavioral source for question-style routes.
- Convert provider outcomes to runtime events by projection from `Outcome.route_fields`:
  - `Event.tag` from `Outcome.tag`
  - `Event.reason` from `route_fields.reason`
  - `Event.question` projected from question-style `route_fields.questions`
- Expose `ctx.outcome.route_fields` everywhere hooks/runtime already expose `ctx.outcome.payload`, and thread it through cloning, trace payloads, finalization records, and extension-visible context snapshots.
- Preserve existing route finalizer, `after`, `on_taken`, redirect, handoff scheduling, required-write enforcement, and artifact guard behavior.
- Treat persisted inspection/report outputs as a compatibility surface:
  - keep existing filenames and runtime-owned artifact roles for `static_step_graph.json`, `topology.json`, `route_table.md`, `compile_report.md`, and workflow-capability snapshots
  - prefer additive field changes and derived compatibility fields over structural replacement when existing readers already consume those payloads
  - if any route-shape change cannot remain additive, land the consumer/test migration in the same slice and call the break out explicitly in the implementation change
- Update static graph, compile report, route table, workflow-capability inspection, and topology hash to reflect compiled route metadata exactly:
  - provider visibility mode
  - payload schema source/fingerprint
  - route-fields schema source/fingerprint
  - preset kind
  - inheritance source
  - suppressed/disabled state
  - required writes
  - handoff
  - hook identity
- Surface provider-schema fallback status anywhere the spec requires reporting it, at minimum in compile report output and inspection/static-graph payloads that summarize provider route contracts.
- Remove separate control-route terminology from reporting and docs; if temporary compatibility fields remain, they must be derived views only and not a second legality mechanism.
- Preserve child-workflow mapping and other non-provider route-finalization behavior unless required by the compiled-route legality changes.

### Phase 4: Regression suite migration and documentation closure
Target modules:
- `tests/unit/test_validation.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/contract/test_engine_contracts.py`
- `tests/unit/test_simple_surface.py`
- runtime workflow package tests that assert current route/control wording
- public docs that still teach top-level `question` / `reason` or separate control routes

Implementation intent:
- Add focused coverage for:
  - helper defaults for `question`, `blocked`, `failed`, `hidden`, and `disabled`
  - GLOBAL inheritance, step-local override, and step-local suppression
  - interactive-only exclusion from full-auto provider schemas
  - canonical provider schema generation and simplified-schema fallback
  - canonical parsing plus legacy parsing normalization
  - payload-schema versus step-level fallback resolution
  - route-fields validation failures
  - hook, handoff, and required-write behavior on helper routes
  - static graph / compile report / topology hash sensitivity to route schema and visibility changes
  - direct `Outcome(...)` parity with rendered-provider JSON and fake/scripted providers
- Update existing assertions that currently depend on:
  - `runtime_control_routes`
  - boolean-only provider visibility
  - top-level `question` / `reason` prompt contracts
  - question behavior inferred only from the tag name
- Update docs to teach:
  - everything is a route
  - route helpers define defaults
  - `GLOBAL` defines workflow-wide defaults
  - `payload` is business output
  - `route_fields` is selected-route metadata
  - legacy top-level `question` / `reason` is deprecated compatibility only

## Interface definitions
- `Route`
  - New authoring helpers: `question`, `blocked`, `failed`, `hidden`, `disabled`
  - New schema helpers: `inherit_payload_schema`, `no_payload_schema`
  - New metadata: normalized `provider_visibility`, payload schema mode/schema, route-fields schema, preset kind, disabled flag
- `CompiledRoute`
  - Must become the canonical transport/runtime/reporting contract for route target, visibility, schemas, hook identity, required writes, handoff, inheritance source, and preset kind
- `Outcome`
  - Add `route_fields: dict[str, Any]`
  - Preserve readable `question` / `reason` compatibility projections
- `ProviderRoute` / `ProviderTurnContext`
  - Carry compiled route summaries, required writes, visibility mode, payload schema, route-fields schema, and any schema-fallback indicator needed by prompt rendering/reporting
- Reporting/topology payloads
  - Emit provider-visible interactive/full-auto route lists plus exact per-route compiled metadata
  - Do not preserve a second independent control-route authority path

## Compatibility and migration notes
- Keep accepting legacy provider outputs with top-level `tag`, `payload`, `question`, and `reason` during the first migration patch.
- Render and document only the canonical `outcome.tag` / `outcome.payload` / `outcome.route_fields` provider shape after this change.
- Keep `ControlRoutes(question=...)` as compatibility-only lowering into the framework default `Route.question()` profile; do not extend it with blocked/failed configuration.
- Keep existing step-level `expected_output_schema` semantics as the default payload-schema fallback when a route inherits payload validation.
- Preserve normal route-finalization ordering and route-local `on_taken` behavior; do not introduce a parallel control-route execution path.
- Persisted inspection/report artifacts are part of the compatibility surface:
  - keep current filenames and top-level runtime artifact identities
  - prefer additive payload changes for static graph, topology, route table, compile report summaries, and workflow capability snapshots
  - where an additive shape is impossible, treat the change as an intentional persisted-artifact contract update and migrate downstream readers/tests in the same phase instead of leaving staggered breakage
- Checkpoint/trace payload additions for `Outcome.route_fields` should remain backward-tolerant: old checkpoints and readers must continue to work when route-fields-specific data is absent, while new traces may add fields without removing the legacy projections in the first patch.

## Regression-risk notes
- The largest failure mode is hybrid legality: if injected runtime-control data and compiled route metadata both survive as active authorities, provider legality and runtime legality will drift.
- Provider schema generation, post-parse validation, retry feedback, and direct scripted outcomes must move together; partial migration would create false retries or allow illegal routes.
- Branch-group internal steps and `simple.py` lowering are separate compilation seams and must use the same route-resolution logic as top-level workflows.
- Static graph, compile report, workflow-capability inspection, and topology hash currently depend on authored/runtime-control distinctions; they must be updated in the same slice as the compiler metadata change to avoid stale inspection and cache keys.
- `Outcome`/`Event` projection changes touch checkpoint metadata, child-workflow propagation, and hook-visible context; these need explicit regression coverage so route-fields do not break paused/failed run bookkeeping.

## Validation and rollout
- Implement phases in order; do not land Phase 2 without Phase 1 metadata in place, and do not leave reporting/topology on the old split model after provider validation changes.
- Primary suites to run after implementation:
  - provider boundary tests
  - validation/compiler unit tests
  - engine contract tests covering provider routing and child workflow mapping
  - runtime static-graph/topology tests
  - runtime tracing and optimization-helper tests that read `static_step_graph.json` / topology artifacts
  - workflow-capability snapshot consumers such as `task_to_candidate_workflow_set`
  - simple-surface tests
  - workflow-package tests that currently assert question/blocked/failed route contracts
- Validate the persisted artifact contract explicitly:
  - confirm additive readers still parse static graph/topology/capability outputs when legacy fields remain present
  - if a non-additive route-shape change is required, update the reader/test surface in the same change and document the intended break in release notes / migration notes for the patch
- Verify compile-report and inspection outputs when simplified provider-schema fallback is used so the reporting requirement cannot regress silently.
- Roll back by reverting to the prior route-compilation path only if the new tests expose an unavoidable compatibility break. Do not keep a long-lived hybrid where compiled routes and runtime-control injection both determine legality.
