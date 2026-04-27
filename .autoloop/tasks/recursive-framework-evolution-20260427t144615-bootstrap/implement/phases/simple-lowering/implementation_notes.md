# Implementation Notes

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: simple-lowering
- Phase Directory Key: simple-lowering
- Phase Title: Simple Workflow Lowering
- Scope: phase-local producer artifact

## Files changed
- `autoloop/simple.py`
- `core/validation.py`
- `tests/unit/test_simple_surface.py`
- `.autoloop/tasks/recursive-framework-evolution-20260427t144615-bootstrap/decisions.txt`

## Symbols touched
- `autoloop.simple.ArtifactSpec`
- `autoloop.simple._NamedDeclaration`
- `autoloop.simple.ReviewStepDeclaration`
- `autoloop.simple.FlowSpec`
- `core.validation.describe_workflow_class`
- `core.validation._lower_simple_steps`
- `core.validation._lower_simple_workflow_graph`
- `core.validation._infer_simple_prompt_reads`

## Checklist mapping
- Revised order 6-8 / phase AC-1: completed additive lowering for simple `Workflow`, `step`, `review_step`, `system_step`, `chain`, `EmptyState`, single-step default routing, and entry inference.
- Revised order 10 / phase AC-2: completed conservative inline prompt placeholder read inference; no automatic `requires` or provider control-schema inference from artifacts/prompts.
- Revised order 11 / broader request `WorkflowStep`: deferred in this phase; helper remains public, but compilation now fails clearly until child-workflow runtime support lands.

## Assumptions
- Inline prompt placeholder inference is sufficient for this phase; file-backed prompt placeholder inference remains for later runtime-aware work.
- `retry=` on the simple helpers can safely lower to `ProviderRetryPolicy` when given an int or explicit policy object without widening runtime behavior.

## Preserved invariants
- Simple authoring still compiles through the existing `WorkflowDefinition` and `CompiledWorkflow` path.
- Artifact schemas remain artifact validation only; they do not set provider `expected_output_schema`.
- Undeclared workspace outputs remain untouched because the engine/provider write model was not changed.
- The strict `workflow` shim and metaclass validation behavior remain unchanged.

## Intended behavior changes
- Non-strict `autoloop.simple.Workflow` classes now lower helper-authored declarations into normal core step objects during workflow discovery.
- `flow = chain(...)`, per-step `routes=`, and explicit `transitions` now merge into one transition table for simple workflows.
- Review steps automatically gain their local rework self-loop, and a one-step simple workflow now gets an inferred terminal completion route.

## Known non-changes
- `workflow_step(...)` is still not executable in this phase.
- Step-level `before` / `after` hooks are carried as declaration metadata only; engine execution ordering is out of phase.
- Provider/model/effort overrides are not yet consumed by runtime provider selection.

## Expected side effects
- Simple workflows with unique inline artifact placeholders now gain inferred readable inputs in compiled metadata.
- Ambiguous bare placeholders intentionally remain unresolved and do not create dependencies.

## Validation performed
- `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py`
- `.venv/bin/python -m pytest -q tests/unit/test_validation.py`
- `.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py`
- `.venv/bin/python -m pytest -q tests/unit/test_provider_boundary_core.py`

## Deduplication / centralization
- Centralized simple-authoring lowering and inference in `core.validation` so the compiler and engine continue consuming only normal core step definitions.
