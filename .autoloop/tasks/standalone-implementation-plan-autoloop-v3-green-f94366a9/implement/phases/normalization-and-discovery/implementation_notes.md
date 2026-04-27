# Implementation Notes

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: implement
- Phase ID: normalization-and-discovery
- Phase Directory Key: normalization-and-discovery
- Phase Title: Normalization and discovery
- Scope: phase-local producer artifact

## Files changed
- `core/validation.py`
- `core/compiler.py`
- `core/workflow_capabilities.py`
- `runtime/loader.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- `tests/runtime/test_workflow_reference_resolution.py`
- `decisions.txt`

## Symbols touched
- `core.validation.is_workflow_class`
- `core.validation.describe_workflow_class`
- `core.validation._inject_reserved_routes`
- `core.validation._validate_handlers`
- `core.validation._validate_required_artifacts`
- `core.validation._validate_artifact_graph`
- `core.validation._validate_control_contracts`
- `core.validation._validate_workflow_step_reference`
- `core.compiler._compile_read_reference`
- `runtime.loader._locate_workflow_class`
- `core.workflow_capabilities.locate_workflow_class`

## Checklist mapping
- Plan milestone 2: shared workflow-class detection added and used by loader/capability inspection.
- Plan milestone 2: reserved routes now injected during normalization instead of ad hoc lowering.
- Plan milestone 2: `system_step(fn)` validation now accepts direct handlers without generated `on_<step>`.
- Plan milestone 2: reads/requires prototype semantics updated so `reads` stay optional and non-ordering.
- Deferred within this phase: provider rendering/request-shape work and engine execution-order changes remain untouched.

## Assumptions
- Unknown string reads should be treated as optional workspace paths for this phase, not hard validation failures.
- Existing runtime/reference tests that still import strict surfaces from `workflow` are out-of-phase regressions and were not migrated here.

## Preserved invariants
- `requires` still resolve only declared artifacts and still enforce producer-before-consumer ordering.
- Simple prompt placeholder inference still resolves artifact reads conservatively and never infers `requires`.
- `system_step(fn)` runtime return normalization remains compiled through the existing direct system-handler path.

## Intended behavior changes
- Simple declaration workflows are now discoverable by file path, module path, and catalog name before lowering.
- Reserved `question` / `blocked` / `failed` routes are always present for normalized steps unless explicitly overridden.
- Direct system handlers validate with the same 1-arg/2-arg contract used by compilation.
- Optional reads no longer create artifact-graph edges or fail solely because the producer is later or absent.

## Known non-changes
- No provider rendering changes.
- No engine finalization-order or `WorkflowStep` execution-path changes.
- No bundled workflow migration off strict `workflow` imports in runtime fixture tests.

## Expected side effects
- Capability/inspection transition payloads for normalized workflows now include reserved pause/fail routes.
- Compiled step `reads` can now contain raw workspace-path strings alongside qualified declared-artifact names.

## Validation performed
- `.venv/bin/python -m py_compile core/validation.py core/compiler.py core/workflow_capabilities.py runtime/loader.py tests/unit/test_validation.py tests/unit/test_simple_surface.py tests/runtime/test_workflow_reference_resolution.py`
- `.venv/bin/python -m pytest tests/unit/test_simple_surface.py::test_simple_single_step_workflow_compiles_with_inferred_entry_and_success_route tests/unit/test_simple_surface.py::test_simple_workflow_step_compiles_as_core_workflow_step_without_generated_handler tests/unit/test_simple_surface.py::test_simple_system_step_lowers_to_core_system_handler_without_on_step_method tests/unit/test_simple_surface.py::test_simple_system_step_normalizes_supported_handler_signatures_and_return_shapes tests/unit/test_validation.py::test_validation_accepts_direct_system_step_handler_without_on_step_method tests/unit/test_validation.py::test_validation_rejects_invalid_workflow_step_child_class_reference tests/unit/test_validation.py::test_compilation_exposes_step_control_contracts tests/unit/test_validation.py::test_validation_rejects_future_read_artifacts tests/unit/test_validation.py::test_validation_allows_application_routes_without_explicit_route_infos tests/runtime/test_workflow_reference_resolution.py::test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection`
- Full phase file test runs were not used as acceptance gates because unrelated pre-existing failures remain in `tests/runtime/test_workflow_reference_resolution.py` and unrelated baseline assertions in broader suites.

## Deduplication / centralization
- Workflow-class detection is centralized in `core.validation.is_workflow_class` and reused by both runtime loading and capability inspection.
