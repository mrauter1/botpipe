# Test Strategy

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: test
- Phase ID: validation-rendering-and-topology
- Phase Directory Key: validation-rendering-and-topology
- Phase Title: Validation Rendering And Topology
- Scope: phase-local producer artifact

## Behaviors covered
- AC-1: hook validation no longer infers route/event redirects from source code.
  Files:
  `tests/unit/test_validation.py`
  Cases:
  `test_validation_does_not_infer_after_hook_routes_from_source`
  `test_validation_does_not_infer_after_producer_redirects_from_source`
- AC-2 provider rendering: hidden routes are excluded from rendered provider step contracts and operation-choice prompts.
  Files:
  `tests/unit/test_provider_boundary_core.py`
  Cases:
  `test_render_provider_turn_excludes_hidden_routes_from_prompt_contract`
  `test_render_provider_operation_prompt_excludes_hidden_choices`
- AC-2 static artifacts: topology/static graph/route table/compile report include hidden routes, explicit vs effective required writes, runtime-control hook locations, state surfaces, and `AWAIT_INPUT`.
  Files:
  `tests/runtime/test_runtime_static_graph.py`
  Cases:
  `test_topology_payload_marks_hidden_routes_and_mermaid_route_table_keep_them`
  `test_topology_artifacts_include_state_surfaces_runtime_control_hook_locations_and_compile_report_details`
  `test_route_table_and_compile_report_include_hidden_global_routes`
  `test_topology_payload_omits_unbound_effective_set_for_inherited_global_routes`
  `test_topology_payload_keeps_explicit_global_route_required_writes_concrete`

## Preserved invariants checked
- Hidden routes remain runtime-legal and provider-excluded at the engine contract boundary.
  File:
  `tests/contract/test_engine_contracts.py`
  Case:
  `test_hidden_routes_are_runtime_legal_but_excluded_from_provider_choices`
- Producer direct-control flow still short-circuits verifier correctly after the render-path change.
  File:
  `tests/contract/test_engine_contracts.py`
  Cases:
  `test_after_producer_goto_short_circuits_verifier`
  `test_after_producer_request_input_checkpoints_pending_input_before_verifier`

## Edge cases
- Hidden routes passed through `ProviderTurnContext.available_routes` are filtered at render time even for operation turns.
- Hidden global routes are emitted in topology artifacts and contribute to compile-report hidden-route counts.
- Static artifacts preserve inherited vs explicit required-write semantics while exposing the richer route table columns.

## Failure paths
- Runtime remains responsible for illegal hook returns; compile-time validation intentionally stops rejecting them via source inspection.
- Existing runtime contract tests remain the failure-path guard for unknown route strings and illegal direct-control usage.

## Flake / stabilization notes
- Coverage is deterministic and filesystem-local only.
- All tests run through the repo venv to avoid host-environment `pytest` mismatches.

## Validation run
- `./.venv/bin/pytest tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_static_graph.py -q`
- `./.venv/bin/pytest tests/unit/test_validation.py tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_static_graph.py tests/contract/test_engine_contracts.py -q -k 'does_not_infer_after_hook_routes_from_source or does_not_infer_after_producer_redirects_from_source or excludes_hidden_routes_from_prompt_contract or excludes_hidden_choices or include_hidden_global_routes or hidden_routes_are_runtime_legal_but_excluded_from_provider_choices'`

## Known gaps
- No full end-to-end golden workflow coverage is added here because that belongs to the later broader test/docs phase.
