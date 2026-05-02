# Implementation Notes

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Public Surface Cleanup
- Scope: phase-local producer artifact

## Files changed
- `autoloop/simple.py`
- `autoloop/core/__init__.py`
- `autoloop/core/descriptors.py`
- `autoloop/core/steps.py`
- `autoloop/core/discovery.py`
- `autoloop/core/hook_validation.py`
- `autoloop/core/compiler.py`
- `autoloop/core/engine.py`
- `autoloop/runtime/static_graph.py`
- `tests/unit/test_simple_surface.py`

## Symbols touched
- `autoloop.simple.Workflow`
- `autoloop.simple.ArtifactSpec`
- `autoloop.simple._NamedDeclaration`
- `autoloop.simple.StepDeclaration`
- `autoloop.simple.ProduceVerifyStepDeclaration`
- `autoloop.simple.PythonStepDeclaration`
- `autoloop.simple._WorkflowStepDeclaration`
- `autoloop.core.Workflow`
- `autoloop.core.descriptors.effective_state_model`
- `autoloop.core.descriptors.effective_parameters_model`
- `autoloop.core.steps.Step`
- `autoloop.core.steps.PromptStep`
- `autoloop.core.steps.ProduceVerifyStep`
- `autoloop.core.steps.PythonStep`
- `autoloop.core.steps.ChildWorkflowStep`
- `autoloop.core.discovery.WorkflowMeta`
- `autoloop.core.discovery.describe_workflow_class`
- `autoloop.core.discovery._is_simple_step_declaration`
- `autoloop.core.discovery._is_simple_artifact_spec`
- `autoloop.core.discovery._lower_simple_writes`
- `autoloop.core.discovery._lower_simple_verifier_writes`
- `autoloop.core.hook_validation.validate_step_hooks`
- `autoloop.core.compiler.CompiledStep`
- `autoloop.core.engine._finalize_step_result`
- `autoloop.core.engine._run_route_hook`
- `autoloop.runtime.static_graph._runtime_control_hook_locations`

## Checklist mapping
- Milestone 1 / public `on_route` removal: removed `on_route` from core step constructors, removed compiled `on_route_hook`, removed engine execution of step-level route hooks, removed static/topology references.
- Milestone 1 / vocabulary cleanup: simple declarations and lowering now use only `writes` / `verifier_writes`; legacy alias fields are no longer stored on declarations.
- Milestone 1 / dunder-marker cleanup: simple workflow/declaration/artifact detection now uses base-class / `isinstance(...)` checks instead of dunder markers.
- Milestone 1 / handler alias cleanup: removed auto-installation of `on_<step>` aliases for simple `python_step`.
- Deferred: broader public removal of class-level `on_start` / `on_outcome` / prompt-step `on_<step>` handling was not changed in this phase.

## Assumptions
- Phase acceptance is satisfied by removing the route-hook surface end to end and fail-fasting removed constructor keywords without migrating unrelated legacy workflow packages in the same turn.

## Preserved invariants
- Strict/internal workflows still compile through the existing transition-based path.
- Route-local `Route.to(..., on_taken=...)` remains supported.
- Public simple workflows still reject class-level `transitions` / `flow`.
- Step-local route metadata and required-write payloads remain unchanged apart from the removed `on_route` surface.

## Intended behavior changes
- `PromptStep`, `ProduceVerifyStep`, `PythonStep`, and `ChildWorkflowStep` no longer accept `on_route=...`.
- Compiled steps no longer expose `on_route_hook`.
- Route finalization no longer runs a separate step-level route hook before `on_taken`.
- Simple declaration objects no longer store `outputs` / `review_outputs`.
- Simple `python_step` no longer mutates the workflow class by installing `on_<step>` aliases.

## Known non-changes
- `AfterStepResult`, multi-arity hook support, and broader hook normalization remain for later milestones.
- Route effects remain supported in this phase.
- Public class-level outcome handlers / lifecycle hooks are not removed in this pass.

## Expected side effects
- Legacy tests or call sites that construct core steps with `on_route=...` now fail immediately with `TypeError`.
- Topology/hash/static-graph consumers no longer see any compiled step-level route-hook field.

## Validation performed
- `python3 -m compileall autoloop/simple.py autoloop/core/__init__.py autoloop/core/descriptors.py autoloop/core/steps.py autoloop/core/discovery.py autoloop/core/hook_validation.py autoloop/core/compiler.py autoloop/core/engine.py autoloop/runtime/static_graph.py`
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/runtime/test_runtime_static_graph.py -q`
- `./.venv/bin/python` signature spot-check for `Step`, `PromptStep`, `ProduceVerifyStep`, `PythonStep`, and `ChildWorkflowStep` constructor surfaces.

## Deduplication / centralization
- Consolidated simple-authoring detection onto base-class inspection in both discovery and descriptor model selection.
- Kept route-hook cleanup centralized in the compiled metadata and route-finalization path rather than adding compatibility branches.
