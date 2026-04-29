# Test Strategy

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: test
- Phase ID: hook-state-session-and-topology-metadata
- Phase Directory Key: hook-state-session-and-topology-metadata
- Phase Title: Hook state session and topology metadata
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- AC-1 hook order and observability:
  `tests/contract/test_engine_contracts.py::test_llm_step_hooks_run_in_order_and_route_hooks_follow_after_hooks`
  `tests/contract/test_engine_contracts.py::test_system_step_hook_events_are_observable`
  `tests/contract/test_engine_contracts.py::test_on_route_hook_runs_before_required_output_validation_and_can_heal_artifact`
  `tests/contract/test_engine_contracts.py::test_route_hooks_re_resolve_artifact_paths_between_on_route_and_on_taken`
- AC-2 state and param surfaces:
  `tests/unit/test_simple_surface.py::test_statevar_and_param_descriptors_extend_compiled_models_and_prompt_namespaces`
  `tests/unit/test_simple_surface.py::test_do_review_step_state_descriptors_compile_to_step_state_fields`
- AC-3 session persistence and overrides:
  `tests/contract/test_engine_contracts.py` review-session and global-session contract tests
  `tests/runtime/test_workspace_and_context.py` persisted run metadata and resume flows
- AC-4 extended prompt/runtime namespaces:
  `tests/unit/test_simple_surface.py` simple-surface placeholder and compile coverage
  `tests/unit/test_primitives_and_stores.py` artifact template resolution with `{workflow_folder}` and nested `{state.*}` placeholders
- AC-5 topology metadata and resume safety:
  `tests/runtime/test_workspace_and_context.py::test_run_metadata_records_topology_hashes_and_artifact_contract_paths`
  `tests/runtime/test_workspace_and_context.py::test_resume_fails_when_saved_topology_hash_differs`

## Preserved Invariants Checked

- Route hooks mutate state and artifacts without redirecting topology.
- State-derived artifact paths stay consistent across `on_route`, route `on_taken`, and final required-write validation.
- Resume safety uses saved topology metadata rather than silently accepting a changed compiled graph.
- Global-session and review-session persistence stay deterministic across run and resume boundaries.

## Edge Cases And Failure Paths

- Route-hook healing before required-write enforcement remains covered.
- Route-hook artifact rebinding is asserted inside `on_taken`, not only through final filesystem output.
- Resume explicitly fails on mismatched topology hash.

## Flake Risk / Stabilization

- Tests are deterministic and filesystem-local; no network, sleeps, timing assumptions, or nondeterministic ordering.

## Known Gaps

- Feedforward `llm()` / `classify()` operation replay is out of scope for this phase and intentionally uncovered here.
