# Implementation Notes

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: surface-foundations
- Phase Directory Key: surface-foundations
- Phase Title: Additive Surface Foundations
- Scope: phase-local producer artifact

## Files changed

- `autoloop/__init__.py`
- `autoloop/simple.py`
- `pyproject.toml`
- `core/prompts.py`
- `core/routes.py`
- `core/engine.py`
- `core/providers/fake.py`
- `core/providers/rendering.py`
- `runtime/prompts.py`
- `runtime/providers/_common.py`
- `docs/authoring.md`
- `tests/unit/test_simple_surface.py`

## Symbols touched

- `Prompt`, `ResolvedPrompt`, `PromptRegistry`
- `Route`, `RouteInfo`
- `Workflow`, `StrictWorkflow`, `ArtifactSpec`, `WorkflowStep`
- `Json`, `Md`, `Text`, `Raw`, `step`, `review_step`, `workflow_step`, `system_step`, `chain`
- `FilesystemPromptRegistry.resolve`
- `Engine._resolve_prompt`
- package discovery for `autoloop*` and `core*`

## Checklist mapping

- Milestone 1 / additive public surface: added repo-root `autoloop` package and documented `autoloop.simple`
- Milestone 1 / import-path compatibility: added minimal packaging glue plus an installed-layout probe for top-level `autoloop.simple`
- Milestone 1 / prompt foundations: added `Prompt.inline(...)`, `Prompt.file(...)`, and `ResolvedPrompt.source`
- Milestone 1 / route foundations: added `RouteInfo` and additive route metadata fields on `Route`
- Milestone 1 / simple artifact helpers: added lightweight simple artifact specs with step-local path inference helpers
- Deferred: compiler lowering, validation-path changes, provider contract migration, workflow-step execution, and workflow shim migration

## Assumptions

- The supported import compatibility story in this phase is repo-root source imports plus a top-level installed/exported package layout for `autoloop` and `core`
- Phase scope allows declaration/spec foundations without wiring compile/engine lowering yet

## Preserved invariants

- Root `workflow` shim remains strict and unchanged
- No runtime execution semantics changed for existing strict workflows
- Legacy `RouteContract` authoring and current provider/static-graph payloads remain untouched

## Intended behavior changes

- `autoloop.simple` is now importable and documented as the additive simple-authoring surface
- `autoloop.simple` now works from an isolated top-level package layout outside the repo root
- Prompt primitives can now carry inline/file origin metadata
- Route primitives can now carry optional summaries, required outputs, and handoff metadata

## Known non-changes

- `autoloop.simple` declarations do not compile or execute through the runtime yet
- No bundled workflow migration, route-contract removal, or strict-validation relaxation landed in this phase
- No provider rendering/schema vocabulary migration landed beyond prompt-origin compatibility

## Expected side effects

- Inline prompts can flow through existing prompt resolution APIs without fabricating prompt paths
- Future phases can lower simple artifact specs into normal `Artifact` objects with deterministic step-local templates

## Validation performed

- `./.venv/bin/pytest -q tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_runtime_providers.py tests/unit/test_provider_boundary_core.py`
- `./.venv/bin/pytest -q tests/unit/test_validation.py`
- `./.venv/bin/pytest -q tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_runtime_providers.py tests/unit/test_provider_boundary_core.py tests/unit/test_validation.py`
- `./.venv/bin/pytest -q tests/test_architecture_baseline_docs.py -k 'authoring_doc or package_foundation_docs_exist' tests/strictness/test_no_compat.py`

## Deduplication / centralization

- Reused the existing prompt registry/runtime resolution path for inline and file prompts instead of creating a second resolution mechanism
- Centralized the simple authoring surface in `autoloop/simple.py` rather than widening the strict `workflow` shim
