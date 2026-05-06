# Test Strategy

- Task ID: final-standalone-codex-cli-spec-blocked-and-fail-4128a4ed
- Pair: test
- Phase ID: route-compilation-contract
- Phase Directory Key: route-compilation-contract
- Phase Title: Route Compilation Contract
- Scope: phase-local producer artifact

## Coverage map

- AC-1 default provider-backed compilation:
  - `tests/unit/test_validation.py::test_validation_routes_respect_control_route_configuration`
  - `tests/unit/test_simple_surface.py::test_simple_workflow_injects_canonical_default_routes_by_step_kind`
  - `tests/unit/test_simple_surface.py::test_simple_workflow_respects_control_routes_false_and_custom_semantic_routes`
  - `tests/runtime/test_runtime_static_graph.py::test_static_step_graph_includes_step_kind_prompts_routes_and_artifact_names`
- AC-2 explicit authored `blocked` / `failed` stay authored-only:
  - `tests/unit/test_validation.py::test_explicit_prompt_blocked_and_failed_routes_remain_authored_only`
  - `tests/unit/test_validation.py::test_explicit_produce_verify_blocked_and_failed_routes_remain_authored_only`
  - `tests/unit/test_stdlib_and_extensions.py` packaged-workflow compiled-surface snapshots keep explicit routes while asserting `runtime_control_routes == ["question"]` and `is_runtime_control == False` for explicit `blocked` / `failed`
- AC-3 provider visibility remains generic for explicit routes:
  - hidden explicit route assertions in the two new compile-level tests above
  - `tests/runtime/test_runtime_static_graph.py::test_topology_payload_preserves_hidden_global_route_visibility_flags`

## Preserved invariants checked

- `question` remains the only injected runtime-control route for enabled provider-backed steps.
- Full-auto hides default `question` but does not add `blocked` / `failed`.
- `control_routes=False` yields no runtime-control routes.
- Explicit visible and hidden `blocked` / `failed` follow normal route `provider_visible` behavior.

## Edge cases and failure paths

- Hidden explicit `failed` on `PromptStep` compiles as legal runtime route but not provider-visible.
- Hidden explicit `blocked` on `ProduceVerifyStep` compiles as legal runtime route but not provider-visible.
- Existing packaged-workflow snapshot coverage guards against accidentally reclassifying explicit authored routes as runtime-control again.

## Known gaps

- This phase did not add runtime retry/exhaustion tests for undeclared provider-selected `blocked` / `failed`; those remain for later runtime-focused work.
- No pytest execution was possible in the current shell environment because `pytest` is not installed; edits were limited to deterministic compile-level assertions.
