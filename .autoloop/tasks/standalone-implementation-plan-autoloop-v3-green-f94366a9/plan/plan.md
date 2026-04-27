# Standalone implementation plan: Autoloop v3 greenfield authoring cleanup

## Intent lock
- Use the request snapshot as the implementation contract.
- Treat this as a greenfield cleanup: remove legacy compatibility shims instead of preserving `RouteContract` behavior.
- Keep `autoloop.simple` as the only active public authoring surface.
- Do not add `autoloop eject`, source expansion, or workflow package rewriting commands.

## Repository reality
- `RouteContract` is still exported from [`core/__init__.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/__init__.py:1) and [`workflow/__init__.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflow/__init__.py:1), normalized in [`core/route_contracts.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/route_contracts.py:1), and threaded through validation, compiler, provider models, renderer, engine, loader-adjacent inspection, bundled workflows, and tests.
- Simple lowering in [`core/validation.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py:340) still converts `workflow_step(...)` into a `SystemStep` plus generated `on_<step>` handler, which conflicts with the requested real `WorkflowStep` engine path.
- Workflow discovery in [`runtime/loader.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/loader.py:662) and capability inspection in [`core/workflow_capabilities.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/workflow_capabilities.py:165) currently require concrete `Step` members and therefore miss simple declaration workflows before lowering.
- Active bundled workflow packages under `workflows/*` and many contract/runtime tests still assert `route_contracts` and `route_required_artifacts`, so kernel cleanup and package/test migration must land together.
- `legacy_docs/` is present and can be treated as archived, but active prompt READMEs and working-tree code/tests cannot retain the removed terminology.

## Target interfaces
- `autoloop.simple` and `autoloop.__init__` export exactly: `Workflow`, `StrictWorkflow`, `step`, `review_step`, `system_step`, `workflow_step`, `WorkflowStep`, `chain`, `Json`, `Md`, `Text`, `Raw`, `Prompt`, `Route`, `RouteInfo`, `AfterHookResult`.
- `core/routes.py` owns the final `RouteInfo` and `Route` dataclasses plus constructor helpers and metadata validation.
- `core/steps.py` owns `Step(route_infos=...)`, direct `SystemStep(handler=...)`, and a real `WorkflowStep`.
- `core/compiler.py`, `core/providers/*`, and `core/engine.py` carry only route metadata (`route_infos`, `route_required_outputs`, `route_handoff`) and readable/required/writable artifact references.
- `runtime/loader.py` and `core/workflow_capabilities.py` share a single workflow-class detection rule that recognizes simple declarations before lowering.
- `system_step(fn)` remains a direct callable surface with supported `(ctx)` and `(state, ctx)` signatures plus normalized returns for `None`, `BaseModel`, route strings, `Event`, `(state, route)`, and `(state, Event)`.
- Provider-facing control rendering must explicitly require the runtime JSON outcome shape `{tag, reason, payload}` plus route-specific `question`, `blocked`, and `failed` guidance and the requested runtime contract sections.

## Ordered milestones
1. Public surface and route metadata foundation
- Remove `RouteContract` from public exports, internal step signatures, and route normalization.
- Delete `core/route_contracts.py`.
- Finalize `RouteInfo` and `Route` validation, precedence, fallback summaries, and required-output resolution rules.
- Convert `autoloop.simple` declarations and `core/steps.py` constructors to the final greenfield API, including `SystemStep(handler=...)`, a real core `WorkflowStep`, and the explicit `system_step(fn)` signature/return normalization contract.
- Preserve `contracts.py` filenames only where they remain useful for schemas/spec helpers; they must not define or import `RouteContract`.

2. Definition normalization, lowering, and discovery
- Replace legacy simple lowering in `core/validation.py` with `route_infos` lowering, reserved-route insertion, `chain(...)` default-route expansion, entry inference, and final `reads`/`requires` semantics.
- Lower `system_step(fn)` directly to `SystemStep(handler=fn)` with no generated `on_<step>` handler and validate supported callable signatures and route/event/state return normalization.
- Add a central `is_workflow_class(candidate)` helper and use it in loader/capability discovery so simple workflows resolve by file path, module, and catalog name before strict lowering.
- Validate hook signatures, route override legality, required-output references, reachable required artifacts, and statically resolvable child workflows without reinstating strict-by-default requirements.

3. Compiler, provider contract, and engine execution
- Remove `route_contracts` and `route_required_artifacts` from compiled dataclasses, provider requests, fake provider telemetry, capability payloads, and rendered provider prompts.
- Introduce the final readable artifact representation and keep artifact schema validation separate from provider `expected_output_schema`.
- Render the provider control contract explicitly: runtime contract sections for readable inputs, required inputs, writable artifacts, available routes, and the exact `{tag, reason, payload}` JSON response format, including `question` route question requirements and `blocked` / `failed` reason requirements.
- Reorder step execution/finalization in `core/engine.py` to match the requested before/after-hook, re-resolution, route validation, required-output enforcement, handoff scheduling, and checkpoint order.
- Execute `WorkflowStep` directly in the engine with child terminal mapping, message resolution priority, loop legality, and declared child-result output writing.
- Keep provider-attributable retry behavior tied to step kind and produced-artifact failures, not to hook route overrides.

4. Bundled workflow migration, docs, and proof
- Migrate active bundled workflows under `workflows/*` off `RouteContract` and onto `Route`/`RouteInfo`, keeping runtime behavior equivalent where still meaningful.
- Update active tests to the new public surface and contract shape; add the requested simple-authoring, route metadata, reserved-route, `WorkflowStep`, hook, artifact, provider-rendering, and `system_step(fn)` return-matrix coverage.
- Update active docs/examples in the working tree to the greenfield model and exclude only archived `legacy_docs/` material from the “no active matches” grep.
- Run targeted suites, full suite, and anti-regression greps for removed terms as the final acceptance gate.

## Compatibility and intentional breaks
- Intentional break: `RouteContract` becomes non-importable from `autoloop`, `workflow`, and `core`, and no compatibility shim should survive in active APIs.
- Intentional break: simple helpers no longer accept `provider`, `model`, or `effort`; runtime config and CLI remain the only provider/model selection surfaces.
- Intentional break: `Workflow` stops requiring explicit `State`, `entry`, transitions, prompt files, session declarations, or `on_<step>` handlers for simple `system_step(fn)` and `workflow_step(...)`.
- Required migration: active bundled workflows, prompt READMEs, capability snapshots, and tests must move to the new metadata model in the same implementation branch.

## Regression controls
- Keep artifact schema validation file-based only; only `control_schema` may become provider `expected_output_schema`.
- Enforce reserved routes mechanically during normalization for every provider/system/workflow step and allow explicit author overrides.
- Preserve deterministic compile order, resumability, checkpointing, session continuity, handoff scheduling, and retry-policy behavior while changing route metadata plumbing.
- Re-resolve artifacts after after-hook state mutation before required-output enforcement so hook-driven route changes cannot use stale handles.
- Treat missing `reads` as non-fatal and missing `requires` as pre-execution failures, and avoid making `reads` impose topology ordering beyond hard requirements.
- Keep `system_step(fn)` behavior deterministic by validating supported handler signatures and normalizing all supported return forms before final-route enforcement.
- Keep provider interoperability stable by making the rendered control-response contract explicit and testing that prompts show the required sections with no route-contract terminology.

## Risk register
- Broad migration risk: bundled workflows and contract tests are tightly coupled to legacy metadata names.
Mitigation: land kernel/provider changes together with package/test updates and finish with grep-based term removal checks.
- Discovery risk: loosening workflow detection may admit helper classes as workflows.
Mitigation: centralize `is_workflow_class(...)` and require subclassing plus at least one concrete `Step` member or simple declaration member.
- Engine-ordering risk: hook reordering can silently change retryability or route enforcement timing.
Mitigation: add explicit engine-contract tests for before/after ordering, route override observability, required-output recomputation, and provider-attributable retry behavior.
- WorkflowStep risk: moving from generated system handlers to a real step class can regress child result wiring and verifier-gated loops.
Mitigation: add direct unit and runtime tests for success/fail/question/blocked mapping, output artifact writing, chaining, and `needs_rework` loops back into a workflow step.

## Validation and rollout
- Phase acceptance is gated by updated unit/contract/runtime coverage for each migrated surface.
- Final proof must include explicit tests for the `system_step(fn)` callable/return matrix and for provider-rendering/control-response contract wording and structure.
- Final verification must include `pytest` for the full suite and repo-wide greps showing no active matches for `RouteContract`, `route_contracts`, `route_required_artifacts`, or `route contract`, excluding archived `legacy_docs/` only.
- Roll back by reverting the full cleanup branch if any phase leaves mixed `route_infos` and `route_contracts` behavior in active code; partial hybrid state is not acceptable.
