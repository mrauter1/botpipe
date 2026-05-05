# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: contract-hardening
- Phase Directory Key: contract-hardening
- Phase Title: Contract Hardening
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/branch_groups/models.py`
- `autoloop/core/branch_groups/lowering.py`
- `autoloop/core/branch_groups/validation.py`
- `autoloop/core/branch_groups/__init__.py`
- `autoloop/core/discovery.py`
- `autoloop/core/compiler.py`
- `tests/unit/test_simple_surface.py`

## Symbols touched
- `BranchGroupDeclarationSpec`, `BranchStepDeclarationSpec`
- `CompiledBranchGroupSpec`, `CompiledBranchStepSpec`
- `build_branch_group_declaration_spec`
- `validate_branch_step_kind`, `validate_fan_in_step_kind`
- `validate_branch_placeholder_reference`, `validate_fan_in_placeholder_reference`
- `compile_workflow`, `_compile_branch_group_internal_steps`, `_definition_contains_branch_groups`

## Checklist mapping
- Plan milestone 1 / declaration-compiled split: completed via separate authored and compiled branch-group spec dataclasses.
- Plan milestone 1 / validation hardening: completed for exact placeholder roots, scoped branch rejection, operation branch rejection, child-workflow rejection, and existing explicit-fresh-session enforcement.
- Plan milestone 1 / composite route exposure: preserved by continuing to source composite routes from fan-in or mechanical outcomes only.
- Plan milestone 1 / compile-cache safety: completed by bypassing `_COMPILED_WORKFLOW_CACHE` for branch-group workflows.
- Plan milestone 1 / compile-time tests: completed with added coverage for spec split, scoped/operation branch rejection, exact placeholder-root matching, and cache bypass.

## Assumptions
- Operation-based fan-in declarations remain allowed in this phase because existing authoring/tests already treat them as supported; only branch operation steps were tightened.

## Preserved invariants
- Non-branch workflow compilation still uses the existing cache path.
- Top-level step session defaulting remains unchanged outside branch groups.
- Runtime branch-group execution, evidence paths, and provider transport behavior were not changed in this phase.

## Intended behavior changes
- Branch-group workflows now compile into separate authored vs compiled spec objects.
- Branch-group workflows no longer reuse the compiled workflow cache.
- Scoped branch steps and operation branch steps now fail compilation as unsupported v1 branch kinds.
- Placeholder root matching for `branch` and `fan_in` is exact instead of prefix-based.

## Known non-changes
- No asyncio runtime scheduling work.
- No provider async transport work.
- No branch evidence path migration.
- No branch-local session runtime changes.

## Expected side effects
- Repeated `compile_workflow(...)` calls for the same branch-group workflow return distinct compiled objects with stable topology when the source is unchanged.

## Validation performed
- `.venv/bin/python -m pytest tests/unit/test_simple_surface.py -k 'branch_group or compile_cache'`
- `.venv/bin/python -m pytest tests/runtime/test_runtime_static_graph.py -k 'branch_group'`
- `.venv/bin/python -m pytest tests/contract/test_branch_group_runtime.py`

## Deduplication / centralization
- Branch-group contract checks stayed centralized in `autoloop/core/branch_groups/validation.py`.
- Discovery owns authored/lowered branch-group specs; the compiler owns conversion into compiled branch-group specs.
