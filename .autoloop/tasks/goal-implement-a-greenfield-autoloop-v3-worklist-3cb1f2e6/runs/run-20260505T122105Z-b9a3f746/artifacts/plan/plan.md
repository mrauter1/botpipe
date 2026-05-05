# Greenfield Progress Worklists Plan

## Scope
- Implement ordered selection in `autoloop/core/worklists.py` with canonical modes `all`, `single`, `up_to`, and `from_to`.
- Add stdlib-only canonical progress-board authoring helpers in `autoloop/stdlib/worklists.py` and export them from `autoloop/stdlib/__init__.py`.
- Add focused selector, stdlib source/policy, and runtime integration tests in the requested new test files.
- Leave `autoloop/__init__.py`, provider/checkpoint/session internals, and route helper surface unchanged unless a direct test exposes a necessary integration fix.

## Confirmed Constraints
- Treat this as greenfield for the new progress worklist helper: no board-shape aliases, no selector mode aliases, no automatic collection/field detection, no typo aliases, no migration shims.
- Core stays generic: `WorkItem.status` remains `str | None`; phase semantics and domain statuses stay out of core.
- Stdlib owns the canonical JSON progress board shape: top-level `items`, item fields `id`, `title`, `status`, plus arbitrary payload fields.
- Common authoring must reduce to `progress_artifact_worklist(name, model=..., fallback=...)`, with derived artifact path/name and selector parameter names.

## Implementation Shape

### 1. Core selector extension
- Expand `Selector` to include `start_param`, `end_param`, `mode_param`, `default_mode`, and validated `allowed_modes`.
- Add selector validation in `Selector.__post_init__`:
  - strip provided param names and reject empty strings,
  - reject empty `allowed_modes`,
  - reject duplicates,
  - accept only `all`, `single`, `up_to`, `from_to`,
  - require `default_mode` to be one of the allowed modes.
- Move selection semantics entirely into `Worklist` after source loading/validation via private helpers:
  - `_selector_param(ctx, name)` for stripped workflow param lookup with whitespace treated as absent,
  - `_selector_mode(ctx, selector, worklist_name)` for mode resolution and clear invalid-mode failures,
  - `_item_indexes(items)` plus `_require_item_id(...)` for ordered bound resolution and missing-id errors.
- Selection behavior to implement exactly:
  - `all`: all items; any selector-bound item/start/end param is an execution error.
  - `single`: explicit `item_param` selects one item; otherwise first item; no range params accepted.
  - `up_to`: use `end_param` when supplied, otherwise `item_param` as end bound, otherwise all items.
  - `from_to`: inclusive range from `start_param` to `end_param`; when `end_param` absent, `item_param` acts as end bound; open start/end select prefix/suffix/all as specified.
- `Selection.explicit` should be computed from whether a selector-bound parameter was actually supplied and used, not merely present in `workflow_params`.
- Keep existing source contracts intact; sources still only materialize ordered items.

### 2. Generic worklist compatibility points
- Preserve `Worklist.from_items`, `from_param`, and `from_artifact` behavior except where selector validation or selection semantics intentionally broaden the generic API.
- Add a read-only `Worklist.artifact` convenience property that returns the backing artifact when the source is artifact-backed and exposes one, otherwise `None`.
- Keep existing source descriptor / missing-policy surfaces stable so runtime/compiler/static-graph behavior does not drift unnecessarily.
- Only update engine/compiler/static-graph-facing selector detail formatting if test coverage proves the new selector fields need to be surfaced.

### 3. Stdlib progress worklist module
- Add `autoloop/stdlib/worklists.py` with:
  - `WorkStatus` enum,
  - `WorkStatusPolicy`,
  - `SKIPPABLE_WORK_STATUS_POLICY` constant if exported,
  - `ProgressItem`,
  - `ProgressBoard` (generic if low-friction, otherwise non-generic canonical base),
  - `ProgressJsonCollectionSource`,
  - `progress_selector(name)`,
  - `progress_artifact_worklist(...)`.
- `WorkStatusPolicy` responsibilities:
  - canonical default statuses exactly `planned`, `in_progress`, `blocked`, `completed`, `failed`,
  - optional `extra_statuses`,
  - alias normalization only for explicit aliases,
  - whitespace/space-to-underscore/lowercase normalization,
  - validation that default role statuses and terminal statuses are supported.
- `ProgressJsonCollectionSource` responsibilities:
  - hard-code `items` / `id` / `title` / `status`,
  - ensure/write fallback using `resolve_artifact_template` via `ArtifactHandle`,
  - validate `model` with Pydantic when provided,
  - normalize missing/aliased statuses through policy,
  - preserve order and non-status payload fields on save,
  - update statuses only for matching ids,
  - raise contextual execution errors with artifact path, collection name, and item id when relevant.
- `progress_artifact_worklist(name, ...)` should derive:
  - artifact path `{workflow_folder}/worklists/{name}.json`,
  - artifact name `{name}_board`,
  - selector params `{name}`, `from_{name}`, `to_{name}`, `{name}_mode`,
  - default `WorkStatusPolicy()`,
  - `Worklist(name=name, source=..., selector=..., item_state_model=item_state)`.

## Test Plan

### New focused tests
- `tests/unit/test_worklist_selectors.py`
  - cover all requested selection modes, default behaviors, explicitness, invalid ranges, unknown ids, invalid modes, and selector construction validation.
- `tests/unit/test_stdlib_progress_worklists.py`
  - cover status policy normalization/validation, canonical board models, source load/save/error behavior, fallback writing, duplicate ids, default artifact naming, and default selector naming.
- `tests/runtime/test_progress_worklists.py`
  - cover default all, `single`, `up_to`, `from_to`, invalid range failure, and optional `skipped` acceptance only under an opted-in policy.

### Adjacent regression checks
- Run the user-specified adjacent suites because they touch stdlib purity, context/worklist persistence, and artifact/template behavior:
  - `tests/unit/test_stdlib_and_extensions.py`
  - `tests/unit/test_primitives_and_stores.py`
  - `tests/runtime/test_workspace_and_context.py`
- Expect existing selector tests in `tests/contract/test_engine_contracts.py` and unit tests in `tests/unit/test_primitives_and_stores.py` to remain valid after the broader selector implementation.

## Regression Surfaces And Controls
- Selector semantics affect all generic worklists, so keep source loading unchanged and confine new behavior to post-load selection helpers.
- Persisted selection snapshots store selected item ids and mode; restoring older snapshots should keep working because item snapshots already carry ids/titles/statuses and the new modes remain plain strings.
- Artifact-backed worklists already participate in runtime/static-graph metadata. Avoid changing descriptor formats unless required, to prevent incidental snapshot churn.
- Stdlib module purity matters: keep the new module as authoring/helpers only, with no runtime or workflow-package imports beyond existing core/stdlib patterns.

## Risk Register
- Risk: selector validation becomes stricter for authored `Selector(...)` declarations.
  - Control: limit strictness to documented invalid inputs; keep existing `("all", "single")` use cases valid.
- Risk: `Selection.explicit` flips for current callers that rely on parameter presence rather than effective bounds.
  - Control: align logic exactly to the request and add unit coverage for implicit-first-item and unbounded range cases.
- Risk: fallback write/load/save paths could leak raw JSON/Pydantic errors.
  - Control: wrap artifact read/validation failures with artifact-path/context-rich `WorkflowExecutionError` messages.
- Risk: adding `.artifact` on `Worklist` could be implemented too invasively.
  - Control: prefer a simple property that introspects `source.artifact`; do not subclass unless necessary.

## Rollout And Rollback
- Rollout order:
  1. core selector behavior and compatibility property,
  2. stdlib progress worklist module and exports,
  3. focused unit/runtime tests,
  4. adjacent regression suites.
- Rollback if needed:
  - revert stdlib module/export addition independently from selector changes,
  - revert selector helper changes in `core/worklists.py` without touching runtime/store internals,
  - keep failures visible rather than adding compatibility shims.

## Milestones
1. Extend core `Selector` and `Worklist` selection semantics with ordered range support and explicit contextual errors.
2. Add canonical stdlib progress worklist helpers, strict default status policy, fallback materialization, and artifact convenience access.
3. Land focused selector/progress/runtime tests and run adjacent regression coverage to confirm no unintended drift.
