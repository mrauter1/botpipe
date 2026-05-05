# Implementation Notes

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: implement
- Phase ID: authoring-and-compile-model
- Phase Directory Key: authoring-and-compile-model
- Phase Title: Authoring And Compile Model
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/simple.py`
- `autoloop/__init__.py`
- `autoloop/core/steps.py`
- `autoloop/core/discovery.py`
- `autoloop/core/lowering.py`
- `autoloop/core/compiler.py`
- `autoloop/core/branch_groups/__init__.py`
- `autoloop/core/branch_groups/models.py`
- `autoloop/core/branch_groups/declarations.py`
- `autoloop/core/branch_groups/validation.py`
- `autoloop/core/branch_groups/lowering.py`
- `tests/unit/test_simple_surface.py`

## Symbols Touched
- Public surface: `parallel`, `fan_out`, `FanIn`, `ParallelDeclaration`, `FanOutDeclaration`
- Composite step model: `BranchGroupStep`, `BranchGroupSpec`, `BranchStepSpec`, `CompiledStep.branch_group`
- Discovery/lowering: `_collect_branch_group_nested_declaration_ids`, `_lower_one_simple_seed`, `_lower_simple_branch_group_step`
- Validation hooks: branch/fan-in placeholder validation, branch-only fresh-session validation, child-workflow fan-in rejection, fan-out input serializability checks

## Checklist Mapping
- Plan item `Add public parallel/fan_out/FanIn authoring surface`: completed
- Plan item `Lower branch groups into one composite compiled step with ordered internal branch specs`: completed
- Plan item `Validate names, helpers, placeholder legality, supported step kinds, fan-out input serializability, and branch-only fresh sessions`: completed
- Plan item `Integrate compiler/discovery/validation without runtime scheduling work`: completed
- Plan item `Runtime scheduling / checkpoint / manifest / outcome execution`: intentionally deferred to later phases

## Assumptions
- This phase owns compile-time structure and validation only; runtime scheduling, manifest writing, and fan-in execution remain out of scope.
- Branch-group consumed simple declarations are private to the composite step for discovery purposes and are not also emitted as top-level workflow steps.

## Preserved Invariants
- Non-branch workflows keep existing discovery, default-session lowering, routes, and compile behavior.
- Provider-backed steps outside branch groups still use the existing default-session behavior.
- `engine.py` and runtime dispatch were not broadened to execute branch groups in this phase.

## Intended Behavior Changes
- Workflows can now declare `parallel(...)` and `fan_out(...)` and compile them into one external `branch_group` step carrying internal ordered branch metadata.
- Provider-backed branch steps now fail compilation unless they explicitly declare `Session.fresh()`.
- `FanIn.results()` and `FanIn.context()` are reserved for fan-in-only reads and reject use elsewhere.

## Known Non-Changes
- No branch-group runtime execution, settlement, or manifest/context artifact writing yet.
- Runtime fan-in orchestration is not implemented yet; this phase only compiles the composite metadata and outer route table shape.
- No child-workflow branch steps or child-workflow fan-in support.

## Expected Side Effects
- Root public exports now include `parallel`, `fan_out`, and `FanIn`.
- Compiled branch-group steps expose `branch_group` metadata and route-tag shape for downstream runtime work.

## Validation Performed
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py -q`
- `./.venv/bin/python -m pytest tests/unit/test_validation.py -q`
- `./.venv/bin/python -m pytest tests/runtime/test_runtime_static_graph.py -q`
- `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -q -k "deterministic or control_routes"`
- `./.venv/bin/python -m py_compile autoloop/simple.py autoloop/__init__.py autoloop/core/steps.py autoloop/core/discovery.py autoloop/core/lowering.py autoloop/core/compiler.py autoloop/core/branch_groups/__init__.py autoloop/core/branch_groups/models.py autoloop/core/branch_groups/declarations.py autoloop/core/branch_groups/validation.py autoloop/core/branch_groups/lowering.py tests/unit/test_simple_surface.py`

## Deduplication / Centralization
- Reused the existing simple-step lowering path through `_lower_one_simple_seed` for both top-level steps and nested branch/fan-in steps.
- Kept branch-group-specific validation and metadata helpers under `autoloop/core/branch_groups/` instead of growing `compiler.py` or `engine.py`.
