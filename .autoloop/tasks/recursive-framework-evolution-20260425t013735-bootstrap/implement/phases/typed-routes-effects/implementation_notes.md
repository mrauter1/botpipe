# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: typed-routes-effects
- Phase Directory Key: typed-routes-effects
- Phase Title: Typed Routes And Effects
- Scope: phase-local producer artifact

## Files Changed

- `core/routes.py`
- `core/effects.py`
- `core/compiler.py`
- `core/validation.py`
- `core/engine.py`
- `core/workflow_capabilities.py`
- `core/__init__.py`
- `workflow/__init__.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`

## Symbols Touched

- `Route`
- `Refresh`
- `ResetCompletion`
- `SetStatus`
- `Advance`
- `BoardMutation`
- `CompiledRoute`
- `CompiledWorkflow.route(...)`
- `_compile_routes(...)`
- `_compile_global_routes(...)`
- `_validate_topology(...)`
- `_validate_route_effects(...)`
- `Engine._apply_route_effects(...)`

## Checklist Mapping

- Plan milestone 6:
  compiled typed `Route` objects and route normalization from shorthand
- Plan milestone 6:
  added effect declarations and compile-time effect/worklist validation
- Phase AC-11:
  preserved shorthand transition execution and added route-object execution coverage
- Phase AC-12:
  reject invalid effect/worklist references at compile time

## Assumptions

- Worklist declarations/runtime support remain out of scope for this phase.
- Backward-compatible inspection payloads should keep emitting plain transition targets.

## Preserved Invariants

- Existing transition dict shorthand still works.
- Workflow control semantics remain limited to declared steps plus `SUCCESS`/`PAUSE`/`FAIL`.
- Route effects do not bypass artifact validation or route resolution.
- Capability inspection and CLI transition payloads remain string-target based.

## Intended Behavior Changes

- Compiled transition metadata is now explicit (`CompiledRoute.target` plus `CompiledRoute.effects`).
- Root `workflow` shim now exports typed route/effect authoring primitives for this phase.

## Known Non-Changes

- No worklist declaration/loading/runtime support was added here.
- No docs were updated in this phase.
- No hidden fallback routing or implicit looping was introduced.

## Expected Side Effects

- Internal consumers of `compiled.routes` / `compiled.global_routes` must read `.target` from `CompiledRoute`.
- Any attempted worklist-bound effect fails validation early until the worklist phase lands.

## Validation Performed

- `.venv/bin/python -m py_compile core/routes.py core/effects.py core/compiler.py core/validation.py core/engine.py core/workflow_capabilities.py workflow/__init__.py core/__init__.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py`
- `.venv/bin/python -m pytest -q tests/unit/test_validation.py`
- `.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_compatibility_runtime.py tests/runtime/test_package_cli.py`

## Deduplication / Centralization

- Route normalization is centralized in compiler/validation helpers instead of split across engine callers.
- Compatibility flattening for transition payloads is centralized in `core/workflow_capabilities.py`.
