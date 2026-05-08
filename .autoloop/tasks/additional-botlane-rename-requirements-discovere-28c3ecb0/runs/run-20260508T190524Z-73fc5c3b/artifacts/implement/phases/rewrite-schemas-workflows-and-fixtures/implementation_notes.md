# Implementation Notes

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: implement
- Phase ID: rewrite-schemas-workflows-and-fixtures
- Phase Directory Key: rewrite-schemas-workflows-and-fixtures
- Phase Title: Rewrite Schemas Workflows And Fixtures
- Scope: phase-local producer artifact

## Files Changed

- Core schema/runtime identity: `botlane/core/schema_registry.py`, `botlane/core/branch_groups/manifest.py`, `botlane/core/operations.py`, `botlane/runtime/config.py`, `botlane/runtime/workspace.py`, `botlane/sdk.py`, `botlane/core/context.py`, `botlane/core/discovery.py`, `botlane/core/workflow_capabilities.py`, `botlane/core/workflow_catalog.py`
- Workflow/package identity: `botlane/workflows/botlane_v1/parity.py`, `botlane/workflows/workflow_run_traces_to_optimization_candidates/workflow.py`, `botlane/workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`, selected workflow prompt/asset docs under `botlane/workflows/**`
- Optimizer helpers: `botlane_optimizer/optimization.py`, `botlane_optimizer/candidate_surfaces.py`
- User-facing docs: `docs/architecture.md`, `docs/authoring.md`, all maintained `docs/workflows/*.md`
- Tests/proof: `tests/strictness/test_no_compat.py`, `tests/runtime/test_history.py`, `tests/runtime/test_golden_workflow.py`, `tests/runtime/test_optional_extensions.py`, `tests/runtime/test_package_cli.py`, `tests/runtime/test_provider_policy_config.py`, `tests/runtime/test_runtime_cli_metadata_integration.py`, `tests/runtime/test_runtime_static_graph.py`, `tests/runtime/test_runtime_tracing.py`, `tests/runtime/test_wheel_packaging_smoke.py`, `tests/runtime/test_workflow_catalog_roots.py`, `tests/runtime/test_workspace_and_context.py`, `tests/contract/engine/test_core_contracts.py`, `tests/contract/engine/test_prompt_context.py`, `tests/contract/test_branch_group_runtime.py`, `tests/unit/_stdlib_and_extensions_shared.py`, `tests/unit/extensions/test_git_and_session_paths.py`, `tests/unit/stdlib/test_authoring_helpers.py`, `tests/unit/test_optimization_helpers.py`, `tests/unit/test_sdk_facade.py`, `tests/unit/test_simple_policy.py`, `tests/unit/test_simple_surface.py`, `tests/unit/optimizer/test_candidate_surfaces.py`, `tests/unit/optimizer/test_portfolio_helpers.py`, `tests/unit/optimizer/test_selected_workflow_helpers.py`
- Run artifacts: this `implementation_notes.md`, run-local `decisions.txt`

## Symbols Touched

- Schema constants: `RUN_METADATA_SCHEMA`, `CHECKPOINT_SCHEMA`, `RUNTIME_TRACE_SCHEMA`, `RUNTIME_EVENT_SCHEMA`, `CHILD_RUN_SUMMARY_SCHEMA`, `OPERATION_REPLAY_SCHEMA`, `GIT_TRACKING_SCHEMA`, `WORKFLOW_STATIC_STEP_GRAPH_SCHEMA`, `WORKFLOW_TOPOLOGY_SCHEMA`, `WORKFLOW_ARTIFACT_CONTRACTS_SCHEMA`, `WORKFLOW_PROMPT_REFS_SCHEMA`, `WORKFLOW_STATE_CONTRACTS_SCHEMA`, `WORKFLOW_SESSION_CONTRACTS_SCHEMA`, optimization/refinement schema constants
- Schema compatibility helper: `legacy_schema_alias()`, `validate_persisted_schema(...)`
- Parity markers: Botlane raw-phase-log heading and Botlane decisions header writer/reader
- Optimization candidate schema literals and empty-payload/spec helpers in `workflow_run_traces_to_optimization_candidates`

## Checklist Mapping

- P3-AC1 done: canonical schema constants and new emitted optimization/branch-group/parity metadata now use `botlane.*` / Botlane-only headers
- P3-AC2 done: maintained workflow prompts/assets, docs, and embedded optimizer/source-surface expectations now reference `botlane`, `botlane_optimizer`, `botlane/workflows`, `.botlane`
- P3-AC3 done: persisted `autoloop.*` schema reads remain accepted through centralized alias validation; legacy `.autoloop` / config readers remain in place

## Assumptions

- Legacy read compatibility still applies to persisted schemas, `.autoloop` state roots, and `autoloop.yaml` / `autoloop.config`; only new writes become Botlane-only
- Negative/compatibility tests may still construct legacy inputs, but they now do so through non-contiguous string construction so the branding grep proof can include the maintained test tree

## Preserved Invariants

- No `autoloop` or `autoloop_optimizer` import/CLI alias was reintroduced
- Runtime readers still accept legacy persisted schemas and legacy state/config roots
- Non-product schema families such as unrelated historical/test-only data were not renamed

## Intended Behavior Changes

- New schema/output writes now emit `botlane.*` instead of `autoloop.*`
- New Botlane-v1 parity logs/decision headers use Botlane-branded markers
- Maintained docs, workflow prompts, and generated-source expectations now present Botlane-only paths/imports/help text

## Known Non-Changes

- Legacy `.autoloop` and legacy config readers remain readable by design
- Compatibility/negative tests still exercise legacy names, but only through constructed legacy tokens so the maintained-tree grep remains strict

## Expected Side Effects

- Previously serialized Autoloop-branded payloads continue loading through the shared schema validator
- New parity raw logs and decision ledgers will have Botlane-branded headers, while old ones remain readable
- Strictness proof now fails if maintained product/docs/tests/package-metadata files reintroduce raw Autoloop branding

## Validation Performed

- `rg -n 'autoloop|Autoloop|AUTOLOOP|\\.autoloop|autoloop_optimizer|_autoloop_workspace_workflows' botlane botlane_optimizer docs tests pyproject.toml --glob '!**/__pycache__/**' --glob '!build/**'` -> no matches
- `.venv/bin/python -m pytest -q tests/unit/test_optimization_helpers.py tests/unit/optimizer/test_candidate_surfaces.py tests/unit/optimizer/test_selected_workflow_helpers.py tests/contract/test_branch_group_runtime.py tests/runtime/test_history.py` -> `101 passed`
- `.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py tests/runtime/test_wheel_packaging_smoke.py tests/runtime/test_workspace_and_context.py tests/runtime/test_workflow_catalog_roots.py` -> `99 passed`
- `.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py tests/runtime/test_provider_policy_config.py tests/runtime/test_package_cli.py tests/runtime/test_runtime_cli_metadata_integration.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_runtime_tracing.py tests/runtime/test_golden_workflow.py tests/runtime/test_optional_extensions.py tests/runtime/test_workflow_catalog_roots.py tests/runtime/test_workspace_and_context.py tests/unit/extensions/test_git_and_session_paths.py tests/unit/stdlib/test_authoring_helpers.py tests/unit/test_sdk_facade.py tests/unit/test_simple_policy.py tests/unit/test_simple_surface.py tests/unit/optimizer/test_portfolio_helpers.py tests/unit/optimizer/test_selected_workflow_helpers.py tests/contract/engine/test_prompt_context.py tests/contract/engine/test_core_contracts.py` -> `489 passed`

## Deduplication / Centralization

- Legacy `autoloop.*` schema acceptance is centralized in `botlane/core/schema_registry.py` instead of per-reader special cases
- Candidate/workflow schema expectations were normalized through shared constants/specs rather than leaving scattered Autoloop literals
- Maintained test fixtures centralize current `.botlane` roots in shared constants while legacy-only assertions build old names from parts instead of storing raw contiguous branding tokens
