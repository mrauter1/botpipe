# Test Strategy

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: test
- Phase ID: maintainability-refactors
- Phase Directory Key: maintainability-refactors
- Phase Title: Maintainability Refactors
- Scope: phase-local producer artifact

## Behavior To Coverage Map
- Session backend composition:
  `tests/unit/test_primitives_and_stores.py::test_session_store_can_be_composed_from_backend`
  Confirms the canonical backend-composed `SessionStore` opens and returns bindings through the public store surface.
- Mapping-to-dict ingress normalization:
  `tests/unit/test_primitives_and_stores.py::test_context_copies_workflow_params_from_mapping_boundary`
  Confirms `Context` copies non-dict `Mapping` input once at ingress and returns outward copies so later caller mutation does not leak into runtime state.
- Worklist load caching per step execution:
  `tests/unit/test_primitives_and_stores.py::test_worklist_load_items_is_cached_per_context`
  Confirms artifact-backed loads are memoized per `Context`.
- Worklist cache refresh after mutable writes:
  `tests/unit/test_primitives_and_stores.py::test_worklist_set_current_status_refreshes_cached_items_for_mutable_sources`
  Confirms `set_current_status()` persists through the mutable source and refreshes the per-context cache without a second load.
- Typed child workflow output surface:
  `tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_supports_typed_child_input_and_output`
  Confirms typed child output, metadata, and artifact aliases remain stable after `ChildWorkflowResult[OutputT]`.
- Replay fingerprint provider-config mismatch:
  `tests/contract/test_engine_contracts.py::test_operation_replay_fingerprint_includes_provider_configuration`
  Confirms same-provider-type config drift emits mismatch warnings.
- Replay fingerprint for inline override providers:
  `tests/contract/test_engine_contracts.py::test_inline_operation_provider_override_participates_in_replay_fingerprint`
  Confirms inline `llm(..., provider=...)` under an active step runtime fingerprints the effective override provider instead of the ambient engine provider.

## Preserved Invariants Checked
- Replay mismatch default remains warn-and-reuse rather than fail.
- Child-run metadata and artifact aliases stay stable while typed output is available.
- Worklist caching remains context-local and deterministic.
- Session-store composition does not change the public open/get behavior.

## Edge Cases / Failure Paths
- Inline override-provider replay mismatch uses a cached value on rerun while still emitting a mismatch warning.
- Mutable worklist status updates do not force a second source load in the same context.
- Mapping ingress regression is exercised with `MappingProxyType` instead of a plain dict so boundary normalization is actually tested.

## Stabilization Notes
- New tests use in-process fake worklist sources and in-memory providers only; no timing, network, or nondeterministic ordering dependencies.
- Replay tests pin call counts and emitted runtime events instead of inspecting incidental internal state.

## Known Gaps
- This phase does not add structural assertions about collaborator/module ownership beyond the behavioral regressions already covered by contract/unit tests.
- Broader full-suite drift from earlier phases remains outside this phase-local test pass.
