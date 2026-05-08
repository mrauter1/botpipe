# Implementation Notes

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: implement
- Phase ID: rewrite-runtime-and-workspace-identity
- Phase Directory Key: rewrite-runtime-and-workspace-identity
- Phase Title: Rewrite Runtime And Workspace Identity
- Scope: phase-local producer artifact

## Files changed
- Runtime/core: `botlane/runtime/workspace.py`, `botlane/runtime/runner.py`, `botlane/runtime/loader.py`, `botlane/runtime/cli.py`, `botlane/runtime/config.py`, `botlane/runtime/git_tracking.py`, `botlane/runtime/providers/codex.py`, `botlane/core/workflow_catalog.py`, `botlane/core/context.py`, `botlane/core/workflow_capabilities.py`, `botlane/sdk.py`
- Focused tests: `tests/runtime/test_workspace_and_context.py`, `tests/runtime/test_workflow_catalog_roots.py`, `tests/runtime/test_workflow_reference_resolution.py`, `tests/runtime/test_runtime_cli_metadata_integration.py`, `tests/runtime/test_package_cli.py`, `tests/runtime/test_runtime_git_tracking.py`, `tests/runtime/test_provider_policy_config.py`, `tests/runtime/test_provider_backends.py`, `tests/runtime/test_sdk_policy.py`, `tests/unit/test_sdk_facade.py`

## Symbols touched
- Workspace/state: `STATE_DIRNAME`, `legacy_state_root()`, `readable_state_roots()`, `resolve_resume_state_root()`, `list_task_records()`, `list_run_records()`
- Catalog/loading: `workspace_workflows_root()`, `workflow_search_roots()`, `_WORKSPACE_MODULE_NAMESPACE`, `_cleanup_workflow_pycache()`
- CLI/runtime identity: `_WORKSPACE_HELP`, `build_arg_parser()`, `_handle_init_workflow()`, runtime git commit message helpers, Codex schema tempfile prefix, child workflow thread name prefix
- Config/SDK: `CONFIG_FILENAMES`, `legacy_user_config_dir()`, `discover_config_file()`, `resolve_runtime_config()`, SDK sentinel helpers, `_promotion_base_dir()`

## Checklist mapping
- Plan milestone 2 / P2-AC1: Botlane-only CLI help, scaffold path, runtime labels, git metadata strings, and Codex temp-file prefix.
- Plan milestone 2 / P2-AC2: New workspace writes use `.botlane`, workspace workflow discovery prefers `.botlane/workflows`, and isolated module namespaces use `_botlane_workspace_workflows`.
- Plan milestone 2 / P2-AC3: Legacy `.autoloop` runtime state, legacy config filenames/directories, legacy workspace workflow roots, and legacy SDK sentinels remain readable for transition behavior.

## Assumptions
- Legacy compatibility remains read-or-cleanup compatibility only; no `autoloop` import alias or CLI alias was reintroduced.

## Preserved invariants
- Checked-in repo `workflows/` remains the highest-precedence workspace discovery root.
- An explicit `state_dir` remains authoritative and disables automatic legacy fallback.
- Legacy compatibility paths are readers/fallbacks only; new writes stay Botlane-only.

## Intended behavior changes
- New runtime and SDK state writes move to `.botlane`.
- New workspace workflow scaffolds move to `.botlane/workflows/`.
- Runtime-generated module namespaces and internal catalog marker attrs move to Botlane-prefixed names.
- Canonical config discovery now prefers `botlane.yaml` / `botlane.config` and `~/.config/botlane`.

## Known non-changes
- Product schema IDs and broader docs/examples/fixture-string rewrites were not addressed in this phase.
- Historical automation-owned `.autoloop/tasks/**` artifacts remain untouched.

## Expected side effects
- Resume/list/summary flows can see both `.botlane` and `.autoloop` state during transition.
- When both Botlane and legacy config filenames exist in the same directory, Botlane config wins.
- SDK cleanup can remove legacy SDK task directories without requiring a manual sentinel rename first.

## Validation performed
- `python3 -m compileall botlane tests`
- Could not run `pytest`: `pytest` is not installed in this environment.
- Could not run runtime-level smoke scripts: the environment is also missing runtime dependencies such as `pydantic`.

## Deduplication / centralization decisions
- Centralized dual-root runtime reads through `readable_state_roots()` instead of scattering `.botlane` / `.autoloop` probes.
- Centralized config precedence in `discover_config_file()` instead of duplicating Botlane-vs-legacy filename checks at each call site.
- Centralized SDK sentinel compatibility in `_sdk_task_sentinel_path()` so cleanup and safe-delete share the same fallback behavior.
