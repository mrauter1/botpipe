# Implementation Notes

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: implement
- Phase ID: authoring-and-builder-reducers
- Phase Directory Key: authoring-and-builder-reducers
- Phase Title: Authoring And Builder Reducers
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/placeholders.py`
- `botlane/core/inventory.py`
- `botlane/core/plan_adapters.py`
- `botlane/core/branch_groups/manifest.py`
- `tests/unit/test_placeholder_refs.py`
- `tests/unit/test_inventory.py`

## Symbols touched

- `_validate_simple_prompt_reference`
- `_validate_branch_or_fan_in_prompt_reference`
- `_validate_bare_simple_prompt_reference`
- `_validate_step_output_prompt_reference`
- `_SIMPLE_PROMPT_SPECIAL_ERRORS`
- `_SIMPLE_ROOT_VALIDATORS`
- `collect_artifact_inventory`
- `MutableArtifactRecord`
- `_ArtifactInventoryBuilder`
- `compiled_step_from_step_plan`
- `_compiled_step_common_kwargs`
- `_COMPILED_STEP_PLAN_BUILDERS`
- `render_branch_group_context`
- `_render_branch_group_header`
- `_render_completion_summary`
- `_render_route_summary`
- `_render_failure_summary`
- `_render_needs_input_summary`
- `_render_cancellation_summary`
- `_render_branch_detail`

## Checklist mapping

- Placeholder validator dispatcher/root helpers: completed in `botlane/core/placeholders.py`; `botlane/core/discovery.py` remained a thin wrapper and required no functional change.
- Artifact inventory builder extraction: completed in `botlane/core/inventory.py`.
- Plan-type builders/shared fallback helpers: completed in `botlane/core/plan_adapters.py`.
- Branch-group section renderers/list helper: completed in `botlane/core/branch_groups/manifest.py`.
- Direct inventory regression tests: completed in `tests/unit/test_inventory.py`.

## Assumptions

- Existing placeholder wording, artifact diagnostics, compiled-step parity metadata, and branch-group markdown content are behavior contracts and must remain unchanged.
- Out-of-phase engine/discovery lifecycle refactors remain deferred.

## Preserved invariants

- Simple prompt validation still routes through `botlane/core/placeholders.py` as the shared implementation used by discovery-time validation.
- `artifacts.<name>` and `step.<name>` simple-prompt aliases preserve the prior recursive bare-reference behavior.
- Artifact inventory still traverses workflow artifacts/logs before step-local writes/reads/requires/logs, preserving ownership and producer ordering.
- `CompiledStep` reconstruction still prefers original compiled parity fields where the prior implementation did.
- Branch-group context output stays byte-for-byte equivalent under the covered contract tests.

## Intended behavior changes

- None. This phase is an internal complexity reduction only.

## Known non-changes

- `botlane/core/discovery.py::describe_workflow_class` was not refactored in this phase.
- Runtime lifecycle behavior in `botlane/core/engine.py` was not touched.
- No direct edits were made under `build/lib/*`.

## Expected side effects

- Lower per-function branching complexity in placeholder validation, artifact inventory assembly, compiled-step rebuilding, and branch-group context rendering.
- Better locality for future tests around inventory conflicts and placeholder root handling.

## Validation performed

- `.venv/bin/python -m pytest tests/unit/test_placeholder_refs.py tests/unit/test_simple_surface.py tests/unit/test_inventory.py tests/unit/test_step_plans.py tests/unit/test_route_contracts.py tests/contract/test_branch_result_serialization.py`
- `.venv/bin/python -m compileall botlane/core/placeholders.py botlane/core/inventory.py botlane/core/plan_adapters.py botlane/core/branch_groups/manifest.py tests/unit/test_inventory.py`

## Deduplication / centralization decisions

- Kept placeholder root dispatch centralized in `botlane/core/placeholders.py` with module-local validator tables instead of duplicating logic in discovery.
- Kept inventory mutation and conflict checks inside a private builder so traversal order remains explicit in `collect_artifact_inventory` while the binding rules live in one place.
