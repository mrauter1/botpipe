# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: branch-results-locators-and-policy-rules
- Phase Directory Key: branch-results-locators-and-policy-rules
- Phase Title: Branch Results And Locators
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/branch_groups/results.py`
- `botlane/core/branch_groups/runtime.py`
- `botlane/core/branch_groups/manifest.py`
- `botlane/runtime/workflow_locator.py`
- `tests/contract/test_branch_result_serialization.py`
- `tests/runtime/test_workflow_locator_variants.py`

## Symbols touched

- `BranchArtifactObservation`
- `BranchResult`
- `BranchResult.to_manifest_dict`
- `BranchGroupRuntime._branch_result_from_step_result`
- `BranchGroupRuntime._failed_branch_result`
- `BranchGroupRuntime._collect_branch_artifacts`
- `_cancelled_branch_result`
- `_unexpected_branch_failure_result`
- `_skipped_branch_result`
- `build_branch_manifest`
- `render_branch_group_context`
- `CatalogWorkflowLocator`
- `PythonFileWorkflowLocator`
- `PythonModuleWorkflowLocator`
- `WorkflowDirectoryLocator`
- `WorkflowLocator`
- `workflow_locator_reference`
- `resolve_workflow_locator`
- `workflow_locator_from_resolved`

## Checklist mapping

- AC-1 branch result serialization parity: implemented via `BranchResult` / `BranchArtifactObservation` and branch-runtime serialization through `to_manifest_dict()`.
- AC-1 workflow locator variants preserve loader behavior: implemented via `botlane/runtime/workflow_locator.py` delegation to `resolve_workflow_reference(...)`.
- AC-1 provider policy emitter parity where rule tables are introduced: deferred intentionally; no provider emitter code changed in this phase.

## Assumptions

- Existing branch manifest shape is authoritative, including omission of cancellation fields on non-cancelled entries.
- Imported-class locator variants remain out of scope for this phase because the approved internal union only covers catalog, file, module, and directory locators.

## Preserved invariants

- Branch manifest schema remains `botlane.branch_results/v1`.
- Branch event payloads and fan-in/outcome consumers still receive manifest-compatible dicts.
- Workflow resolution precedence and metadata stay owned by `botlane.runtime.loader`.
- No new internal names were exported through package `__init__` modules.

## Intended behavior changes

- None externally. This phase is internal-only.

## Known non-changes

- Branch-group scheduling, fan-in routing, and outcome policy semantics were not changed.
- Provider policy emitters were not table-driven in this pass.
- `botlane/runtime/__init__.py` exports were left unchanged; locator variants stay internal-module-only.

## Expected side effects

- Branch manifest helpers now accept typed branch-result objects in addition to serialized mappings during migration.
- Branch artifact observations are collected structurally first, then serialized at the manifest boundary.

## Validation performed

- `./.venv/bin/python -m pytest tests/contract/test_branch_result_serialization.py`
- `./.venv/bin/python -m pytest tests/runtime/test_workflow_locator_variants.py`
- `./.venv/bin/python -m pytest tests/contract/test_branch_group_runtime.py tests/unit/test_branch_group_context_sessions.py`
- `./.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py`

## Deduplication / centralization

- Centralized branch-result dict emission in `BranchResult.to_manifest_dict()` instead of keeping five independent dict constructors as the long-term source of truth.
- Centralized locator resolution through `workflow_locator_reference(...)` -> `resolve_workflow_reference(...)` rather than introducing a second loader path.
