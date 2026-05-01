# Implementation Notes

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: public-surface-terminal-cut
- Phase Directory Key: public-surface-terminal-cut
- Phase Title: Public Surface And Terminal Cut
- Scope: phase-local producer artifact

## Files changed
- `autoloop/__init__.py`
- `autoloop/simple.py`
- `core/__init__.py`
- `core/primitives.py`
- `core/routes.py`
- `core/validation.py`
- `core/compiler.py`
- `core/engine.py`
- `core/history.py`
- `runtime/static_graph.py`
- `runtime/runner.py`
- `runtime/workspace.py`
- `runtime/cli.py`
- `stdlib/__init__.py`
- `stdlib/control.py`
- `docs/authoring.md`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `tests/unit/test_simple_surface.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/strictness/test_no_compat.py`
- `tests/unit/test_stdlib_and_extensions.py`

## Symbols touched
- Public terminals: `AWAIT_INPUT`, `FINISH`, `FAIL`, `SELF`
- Public runtime controls: `RequestInput`, `Goto`, `Fail`
- Public route helper: `Route.await_input(...)`
- Removed public simple keywords: `on_route` on `step`, `produce_verify_step`, `python_step`, `workflow_step`
- Stdlib helper rename: `await_input_on_outcome_tags`
- Public/runtime status string: `awaiting_input`

## Checklist mapping
- Phase 1 / terminal cleanup: completed via terminal constant/export rename and static artifact terminal payload update.
- Phase 1 / runtime-control objects: completed for public dataclass surface and export wiring.
- Phase 1 / remove public `on_route`: completed for simple declarations/signatures and simple lowering.
- Phase 1 / remove old public names: partially covered here through `PAUSE` hard cut and strict/public-surface tests; broader removed-name enforcement remains in existing strictness coverage.

## Assumptions
- Internal core-step `on_route` hooks stay temporarily supported for later runtime-control work; only the public simple authoring surface is cut in this phase.
- Legacy persisted run metadata with status `paused` still needs to remain answerable during the rename.

## Preserved invariants
- Existing checkpoint payload shape stays unchanged in this phase (`pending_question` remains untouched).
- Route tag `"question"` remains the reserved provider/runtime route name.
- Engine semantics for pause-like suspension remain the same apart from terminal/status naming.

## Intended behavior changes
- `PAUSE` is no longer exported from `autoloop` or `core`; `AWAIT_INPUT` is canonical.
- `RequestInput`, `Goto`, and `Fail` are importable from the public authoring surface.
- Simple authoring declarations reject `on_route` as a keyword.
- Public topology hook payloads no longer emit an `on_route` hook field.
- Runtime status normalization now emits `awaiting_input` for the await-input terminal.

## Known non-changes
- Pending-input checkpoint/schema redesign is deferred to the runtime-control metadata phase.
- Internal core-step/runtime hook plumbing still uses `on_route`.
- Broader docs/tests/workflow examples outside the touched phase-local surfaces were not swept.

## Expected side effects
- Consumers that imported `PAUSE` or passed `on_route=` through the simple surface now fail fast.
- CLI/help text now refers to awaiting-input runs, while record selection still accepts legacy paused records through compatibility logic.

## Validation performed
- `python3 -m py_compile` passed for all touched production files.
- `python3 -m py_compile` passed for touched test files.
- `pytest` execution was not possible: the environment has no `pytest` module.
- Import-time smoke execution was not possible with the system interpreter: the environment has no `pydantic` module.

## Deduplication / centralization
- Kept terminal-name normalization local to existing terminal/status helpers instead of adding new compatibility shims.
- Centralized public await-input helper renames through `core.primitives`, `core.routes`, and `stdlib.control` rather than leaving aliases behind.
