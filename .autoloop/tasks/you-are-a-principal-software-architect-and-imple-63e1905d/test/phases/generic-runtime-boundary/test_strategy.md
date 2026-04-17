# Test Strategy

- Task ID: you-are-a-principal-software-architect-and-imple-63e1905d
- Pair: test
- Phase ID: generic-runtime-boundary
- Phase Directory Key: generic-runtime-boundary
- Phase Title: Generic Runtime Boundary
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Generic workspace/runtime boundary is phase-agnostic:
  `test_workspace_creates_generic_layout_and_preserves_resume_root_compatibility`
  `test_runner_executes_toy_workflow_without_phase_scaffolding`
  `test_autoloop_v1_runs_with_generic_runtime_and_explicit_prompt_paths`
- Generic session persistence has no slot-name special cases and can be locally remapped:
  `test_filesystem_session_store_uses_generic_paths_and_loads_legacy_thread_id`
  `test_filesystem_session_store_sparse_writes_preserve_existing_metadata`
  `test_filesystem_session_store_supports_custom_path_resolver`
  `test_autoloop_v1_runs_with_generic_runtime_and_explicit_prompt_paths`
- Generic runner/CLI surface is workflow-agnostic:
  `test_resolve_runtime_config_merges_global_local_and_cli`
  `test_runner_rejects_non_positive_max_steps`
  `test_cli_main_threads_generic_runtime_options_into_runner_options`
  `test_cli_main_turns_config_errors_into_parser_exit`
  `test_cli_main_turns_workflow_execution_errors_into_clean_exit`
- Toy workflow proof for runtime agnosticism:
  `test_runner_executes_toy_workflow_without_phase_scaffolding`
  `test_cli_module_smoke_executes_toy_workflow_end_to_end`
- Preserved integration invariants around event status and workflow loading:
  `test_workspace_workflows_compile_through_the_strict_loader_surface`
  `test_loader_does_not_inject_canonical_symbols`
  `test_ralph_loop_executes_with_generic_runtime_and_persistent_main_session`
  `test_runner_emits_fatal_error_status_for_legacy_status_reader_compatibility`
  `test_legacy_latest_run_status_reads_generic_runtime_success_run`

## Edge cases

- Scoped session names that need encoded filesystem keys.
- Sparse session rewrites preserving legacy metadata fields.
- Prompt lookup through explicit workflow-owned paths instead of runtime search-root hacks.

## Failure paths

- `max_steps <= 0` is rejected at runner entry.
- Resume without checkpoint is rejected for both top-level and nested scoped session files.
- Loader still fails when workflow modules omit required canonical imports.

## Flake controls

- All behavior uses `ScriptedLLMProvider`, `tmp_path`, local smoke-provider modules, and explicit `PYTHONPATH` / `XDG_CONFIG_HOME`.
- No network, time-based ordering, or nondeterministic provider behavior is exercised.

## Known gaps

- Detailed Autoloop-v1 decisions/raw-log/clarification parity remains intentionally deferred to the later workflow-owned parity-harness phase.

## Validation

- `pytest autoloop_v3/tests -q`
