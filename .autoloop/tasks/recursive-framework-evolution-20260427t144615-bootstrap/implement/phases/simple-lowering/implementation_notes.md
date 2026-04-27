# Implementation Notes

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: simple-lowering
- Phase Directory Key: simple-lowering
- Phase Title: Simple Workflow Lowering
- Scope: phase-local producer artifact

## Files changed
- `autoloop/simple.py`
- `core/prompts.py`
- `core/validation.py`
- `runtime/prompts.py`
- `tests/unit/test_simple_surface.py`
- `.autoloop/tasks/recursive-framework-evolution-20260427t144615-bootstrap/decisions.txt`

## Symbols touched
- `autoloop.simple.ArtifactSpec`
- `autoloop.simple._NamedDeclaration`
- `autoloop.simple.ReviewStepDeclaration`
- `autoloop.simple.FlowSpec`
- `core.prompts.resolve_prompt_reference`
- `core.validation.describe_workflow_class`
- `core.validation._install_simple_workflow_step_handler`
- `core.validation._lower_simple_steps`
- `core.validation._lower_simple_workflow_graph`
- `core.validation._infer_simple_prompt_reads`

## Checklist mapping
- Revised order 6-8 / phase AC-1: completed additive lowering for simple `Workflow`, `step`, `review_step`, `system_step`, `workflow_step`, `chain`, `EmptyState`, single-step default routing, and entry inference.
- Revised order 10 / phase AC-2: completed conservative prompt placeholder read inference for both inline and file-backed simple prompts; no automatic `requires` or provider control-schema inference from artifacts/prompts.
- Revised order 11 / broader request `WorkflowStep`: implemented this phase by lowering `workflow_step(...)` to generated `SystemStep` handlers over `ctx.invoke_workflow(...)` instead of adding a new engine kind.

## Assumptions
- `retry=` on the simple helpers can safely lower to `ProviderRetryPolicy` when given an int or explicit policy object without widening runtime behavior.
- `workflow_step(message_from=...)` should resolve against known artifact references; literal child messages should continue using `message=...`.

## Preserved invariants
- Simple authoring still compiles through the existing `WorkflowDefinition` and `CompiledWorkflow` path.
- Artifact schemas remain artifact validation only; they do not set provider `expected_output_schema`.
- Undeclared workspace outputs remain untouched because the engine/provider write model was not changed.
- The strict `workflow` shim and metaclass validation behavior remain unchanged.

## Intended behavior changes
- Non-strict `autoloop.simple.Workflow` classes now lower helper-authored declarations into normal core step objects during workflow discovery.
- `flow = chain(...)`, per-step `routes=`, and explicit `transitions` now merge into one transition table for simple workflows.
- Review steps automatically gain their local rework self-loop, and a one-step simple workflow now gets an inferred terminal completion route.
- Simple file prompts now participate in placeholder-based `reads` inference using the same lookup rules as runtime prompt loading.
- Simple `workflow_step(...)` declarations now compile as generated child-workflow system steps and can emit reserved child-result routes with no extra author boilerplate.

## Known non-changes
- Step-level `before` / `after` hooks are carried as declaration metadata only; engine execution ordering is out of phase.
- Provider/model/effort overrides are not yet consumed by runtime provider selection.
- `workflow_step` still does not lower to a first-class compiled `kind="workflow"` node; that broader engine refactor remains for the later runtime phase.

## Expected side effects
- Simple workflows with unique inline or file-backed artifact placeholders now gain inferred readable inputs in compiled metadata.
- Ambiguous bare placeholders intentionally remain unresolved and do not create dependencies.
- Lowered simple workflow steps now write child-result summary artifacts when outputs are declared.

## Validation performed
- `PYTHONPATH=.. .venv/bin/python -m pytest -q tests/unit/test_simple_surface.py`
- `PYTHONPATH=.. .venv/bin/python -m pytest -q tests/unit/test_validation.py`
- `PYTHONPATH=.. .venv/bin/python -m pytest -q tests/strictness/test_no_compat.py`
- `PYTHONPATH=.. .venv/bin/python -m pytest -q tests/unit/test_provider_boundary_core.py`
- `PYTHONPATH=.. .venv/bin/python -m pytest -q tests/runtime/test_workspace_and_context.py -k "invoke_workflow or prompt_resolution"`

## Deduplication / centralization
- Centralized simple-authoring lowering and inference in `core.validation` so the compiler and engine continue consuming only normal core step definitions.
- Centralized file prompt lookup in `core.prompts.resolve_prompt_reference(...)` so validation-time inference and runtime prompt loading do not drift.
