# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: implement
- Phase ID: normalization-and-discovery
- Phase Directory Key: normalization-and-discovery
- Phase Title: Normalization and discovery
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — `core.validation.is_workflow_class` now treats inherited simple declarations as discoverable workflow members, but `core.validation.describe_workflow_class` still only scans `workflow_cls.__dict__`. Concrete failure: `class Child(BaseSimpleWorkflow): pass` is now discoverable through loader/capability inspection, yet `compile_workflow(Child)` fails with `workflow entry must exist and be a step` because inherited simple declarations are never lowered. Minimal fix: centralize member enumeration for both `is_workflow_class` and `describe_workflow_class` so inherited simple/strict step members are discovered and lowered consistently.

- IMP-002 `blocking` — `core.compiler._compile_read_reference` falls back to the raw string for every `WorkflowValidationError`, which silently converts ambiguous declared-artifact reads into workspace-path reads. Concrete failure: a strict workflow with two produced `summary` artifacts and `SystemStep(reads=["summary"])` now compiles to `reads == ("summary",)` instead of raising the existing ambiguity error, so the authored artifact read is reinterpreted as a filesystem path. Minimal fix: add one shared optional-read resolver that only falls back on the specific “unknown artifact reference” case for string/path reads, while preserving ambiguity and other declared-artifact validation errors.

- IMP-003 `blocking` — The requested prototype validation for after-hook route overrides is still absent. `core.validation._validate_step_hooks` only checks arity, so a workflow like `step("Do A.", after=lambda ctx, outcome: "missing_route")` compiles even though the phase contract explicitly requires invalid after-hook route overrides to be caught during validation. Minimal fix: extend hook validation with a dedicated route-override check path in `core.validation` and add the missing regression test there instead of deferring it silently.

## Review Pass 2

No new findings. IMP-001, IMP-002, and IMP-003 are resolved by the current implementation and the targeted regression coverage:

- `tests/unit/test_simple_surface.py::test_inherited_simple_workflow_declarations_remain_discoverable_and_compilable`
- `tests/unit/test_validation.py::test_validation_rejects_ambiguous_declared_read_reference`
- `tests/unit/test_validation.py::test_validation_rejects_statically_invalid_after_hook_route_override`
- `tests/runtime/test_workflow_reference_resolution.py::test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection`
