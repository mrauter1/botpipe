# Implementation Notes

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: implement
- Phase ID: lazy-worklist-runtime
- Phase Directory Key: lazy-worklist-runtime
- Phase Title: Lazy Worklist Runtime
- Scope: phase-local producer artifact

## Files changed

- Runtime core: `autoloop/core/worklists.py`, `autoloop/core/context.py`, `autoloop/core/artifacts.py`, `autoloop/core/engine.py`, `autoloop/core/engine_collaborators.py`
- Compile/static surfaces: `autoloop/core/compiler.py`, `autoloop/runtime/static_graph.py`
- Tests: `tests/unit/test_primitives_and_stores.py`, `tests/runtime/test_runtime_static_graph.py`, `tests/contract/test_engine_contracts.py`, `tests/unit/test_simple_surface.py`
- Adjacent regression cleanup: workflow package declarations under `workflows/**/workflow.py`

## Symbols touched

- `Worklist.from_artifact`, `Worklist.source_type`, `Worklist.missing_policy`, `Worklist.source_descriptor`, `Worklist.restore_selection`, `_ArtifactWorklistSource.ensure`
- `Context.__init__`, `Context._worklist_name`, `_ContextRuntime.set_selection`, `_ContextRuntime.set_selection_snapshots`, `_ContextRuntime.emit_worklist_selection_resolved`
- `Engine.run`, `Engine._restore_worklist_selections`, `Engine._ensure_worklist_selection`, `Engine._save_checkpoint`, `Engine._snapshot_worklist_selections`, `Engine._worklist_source_descriptor`
- `_resolve_item_placeholder`, `_resolve_work_item_path`
- `_workflow_compile_cache_key`, `_topology_hash_payload`, `_worklist_surfaces_payload`

## Checklist mapping

- AC-1: compile/runtime no longer load artifact-backed worklists until first use; unused non-scoped paths stay unmaterialized.
- AC-2: scoped entry, `ctx.selection(...)`, `ctx.current(...)`, prompt placeholders, and artifact-template placeholders all materialize via the same first-use resolver path.
- AC-3: resume restores `SelectionSnapshot` objects lazily; sources are not touched until access, and checkpoints preserve both restored snapshots and newly materialized selections.
- AC-4: work-item continuity still resolves through `ctx.current(...)`, which now materializes restored selections lazily before deriving the stable `<worklist>:<dir_key|id>` key.
- AC-5: static graph/topology worklist payloads now expose declared materialization state plus source descriptor/missing policy; runtime `worklist_selection_resolved` events expose the materialized state.
- AC-6: artifact-backed missing-source behavior is centralized on `Worklist.from_artifact(..., missing="error" | "scaffold")` and `_ArtifactWorklistSource.ensure`.

## Intended behavior changes

- Checkpoint restore is now strict-lazy: restored worklists stay as snapshots until a scoped step, placeholder, explicit selection access, or work-item continuity actually needs them.
- Artifact-backed worklists default to `missing="error"` and only scaffold backing data when `missing="scaffold"` is authored.
- Runtime placeholder rendering now resolves `{item.state.<field>}` from active `ctx.item_state`.

## Preserved invariants

- Static validation still only checks worklist declarations, selector metadata, item-state shape, and scoped-step references.
- Custom non-artifact `WorklistSource.ensure(...)` behavior is unchanged.
- Prompt placeholder compile-time legality stays separate from runtime artifact-template rendering.
- Existing duplicate-id, missing-payload-path, and missing-current-item runtime failures stay explicit.

## Known non-changes

- No broader `Effects` API redesign.
- No documentation sweep in `docs/` during this phase-local turn.
- No new eager inspection loader was introduced; runtime materialization is surfaced through static graph payloads and runtime events instead.

## Assumptions

- An empty scaffolded artifact payload `{collection: []}` is the correct first-use baseline for artifact-backed worklists that opt into scaffolding.
- Preserving checkpoint snapshots across later checkpoints is required even when a resumed path still has not re-materialized them.

## Expected side effects

- Compiled topology/static graph hashes change for workflows that declare worklists because source descriptor and missing policy now participate in the worklist surface.
- Public workflow packages that still passed `role="managed"` now import/compile again after the adjacent cleanup.

## Deduplication / centralization

- Selection restore and first-use selection creation now converge in `Engine._ensure_worklist_selection(...)` plus `Worklist._selection_from_loaded_items(...)`.
- Artifact-backed missing-source policy is enforced in one place: `_ArtifactWorklistSource.ensure(...)`.

## Validation performed

- `./.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py tests/runtime/test_runtime_static_graph.py tests/contract/test_engine_contracts.py -q`
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py -q`
- `./.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py tests/runtime/test_runtime_static_graph.py tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/runtime/test_workspace_and_context.py tests/unit/test_validation.py -q`
