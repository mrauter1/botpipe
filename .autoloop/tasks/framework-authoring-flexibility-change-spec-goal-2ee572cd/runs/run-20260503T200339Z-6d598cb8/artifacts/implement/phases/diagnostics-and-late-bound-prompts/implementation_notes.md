# Implementation Notes

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: implement
- Phase ID: diagnostics-and-late-bound-prompts
- Phase Directory Key: diagnostics-and-late-bound-prompts
- Phase Title: Diagnostics And Late-Bound Prompts
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/inventory.py`
- `autoloop/core/discovery.py`
- `autoloop/core/artifacts.py`
- `autoloop/core/engine.py`
- `autoloop/core/operations.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched

- `collect_artifact_inventory`
- `_raise_dual_role_artifact_error`
- `_validate_simple_prompt_reference`
- `resolve_artifact_template`
- `render_runtime_template`
- `_resolve_placeholder`
- `Engine._resolve_prompt`
- `operations._resolve_prompt`

## Checklist mapping

- Phase 4 / artifact ownership: reject same-identity workflow-level plus step-produced artifacts with actionable guidance.
- Phase 4 / prompt validation: allow scoped `item.id`, `item.dir_key`, `item.payload.<path>`, and `worklist.<name>.current...` placeholder forms without compile-time backing-data checks.
- Phase 4 / prompt runtime: lazy runtime rendering now reports placeholder-specific current-item, payload-path, and worklist-load failures.

## Intended behavior changes

- Same artifact identity can no longer be both a workflow class artifact and a step write.
- Simple prompt static validation now admits the narrow late-bound `item.*` and `worklist.*` runtime namespaces requested by the phase.
- Runtime prompt text now resolves only `item.*` and `worklist.*` placeholders; artifact templates keep resolving supported runtime placeholders and now report stricter item/worklist failures.

## Preserved invariants

- Separate-identity duplicate and ambiguous artifact diagnostics remain unchanged.
- Prompt validation remains strict for unknown roots, params/state/input/workflow fields, step names, and regular artifact references.
- This phase does not introduce broad prompt interpolation; non-item/worklist prompt placeholders remain literal.

## Known non-changes

- No managed/shared artifact escape hatch was added.
- No static graph or inspection payload work was touched in this phase.

## Expected side effects

- File-based and inline operation prompts now get the same late-bound `item/worklist` rendering behavior as workflow prompts when a runtime context exists.

## Validation performed

- `python3 -m py_compile autoloop/core/inventory.py autoloop/core/discovery.py autoloop/core/artifacts.py autoloop/core/engine.py autoloop/core/operations.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py`
- `pytest` was not available in the shell.
- Project runtime deps were not available in the shell (`python3` import of `pydantic` failed), so no live workflow execution was possible here.

## Assumptions

- Narrow prompt runtime rendering for `item/worklist` only is acceptable because the request for this phase targets late-bound runtime facts rather than broad prompt interpolation.
