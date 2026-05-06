# Implementation Notes

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: implement
- Phase ID: tests-and-docs-migration
- Phase Directory Key: tests-and-docs-migration
- Phase Title: Migrate Tests And Docs
- Scope: phase-local producer artifact

## Files changed

- Runtime/reporting: `autoloop/core/compiler.py`, `autoloop/core/engine.py`, `autoloop/core/engine_collaborators.py`
- Tests: `tests/contract/test_engine_contracts.py`, `tests/test_architecture_baseline_docs.py`
- Public docs: `docs/authoring.md`, `docs/architecture.md`, `Workflow_Instructions.md`
- Prompt/docs wording sweep: `autoloop/workflows/*/prompts/*.md`, `autoloop/workflows/*/prompts/README.md`, `docs/workflows/*.md`

## Symbols touched

- `CompiledStep.route_table`
- `StepDispatcher._execute_pair_step_async()`
- `StepDispatcher._run_pair_step_async()`
- `Engine._required_output_artifacts()`
- `test_workflow_instructions_freeze_runtime_contract_vocabulary()`
- Prompt/doc route wording around helper routes, `GLOBAL`, `provider_visibility`, `outcome.route_fields`, and compatibility-only `ControlRoutes` / top-level `question` / `reason` notes

## Checklist mapping

- Phase 4 tests: updated contract/reporting assertions for provider-attempt events, pair-hook short-circuits, child-workflow `AWAIT_INPUT` fallback, and question-route required-write expectations.
- Phase 4 tests: extended docs regression coverage so `Workflow_Instructions.md` must keep the canonical helper-route wording and compatibility-only `ControlRoutes` / top-level `question` / `reason` note.
- Phase 4 docs: updated authoring, architecture, workflow instructions, workflow prompt READMEs, prompt bodies, and workflow package docs to prefer route helpers and canonical `outcome.route_fields`.
- No checklist items intentionally deferred in this phase.

## Assumptions

- The empty `compiled_routes` / `compiled_route_tags` reporting output was unintended drift from prior phases, not a deliberate compatibility shape.
- Pair-step `before_producer` hooks are expected to behave like other pre-provider hooks: no provider call when they short-circuit, and no candidate route recorded for hook-originated route events.

## Preserved invariants

- Compiled routes remain the only legality source.
- Existing filenames for static graph, topology, route table, and compile report are unchanged.
- Legacy top-level provider parsing compatibility remains intact.
- Runtime artifact validation still uses effective required writes, not only explicit route overrides.

## Intended behavior changes

- Inspection/reporting surfaces now expose per-step compiled route tables and provider-schema fallback metadata through `CompiledStep.route_table`.
- Pair-step `before_producer` hooks now execute before the producer call and may short-circuit cleanly with route events or direct controls.
- Docs and prompts now describe helper routes as ordinary compiled routes, prefer `provider_visibility="hidden"`, and teach `outcome.tag` / `outcome.payload` / `outcome.route_fields`.
- The shared workflow instruction contract and authoring docs now explicitly mark `ControlRoutes(question=...)` and top-level `question` / `reason` provider fields as compatibility-only during migration.

## Known non-changes

- Legacy `provider_visible=False` remains documented only as compatibility normalization, not preferred authoring.
- Legacy top-level `tag` / `payload` / `question` / `reason` provider parsing is still accepted during migration.

## Expected side effects

- Static graph/topology payloads and compile reports now include populated `compiled_routes` / `compiled_route_tags` instead of empty compatibility placeholders.
- Prompt and workflow-package docs no longer use the "question is the only default runtime control route" wording.

## Validation performed

- `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py tests/contract/test_engine_contracts.py tests/test_architecture_baseline_docs.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_validation.py tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_static_graph.py tests/contract/test_engine_contracts.py tests/test_architecture_baseline_docs.py`
- `./.venv/bin/python -m pytest -q tests/test_architecture_baseline_docs.py`

## Deduplication / centralization

- Used narrow bulk text replacements for repeated workflow prompt/doc phrases instead of hand-editing the same route wording dozens of times.
- Centralized the compatibility-only route guidance in `Workflow_Instructions.md` and locked it into the shared docs regression suite instead of relying on duplicated workflow-package wording alone.
