# Test Strategy

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: test
- Phase ID: state-surfaces
- Phase Directory Key: state-surfaces
- Phase Title: Add Built-In Step State
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- Built-in runtime step state exists on every compiled step.
  Covered by:
  - `tests/unit/test_simple_surface.py::test_simple_workflow_compiles_with_pydantic_state_params_and_produce_verify_step`
  - `tests/runtime/test_runtime_static_graph.py::test_topology_artifacts_are_written_additively_with_canonical_finish_surface`

- `produce_verify_step` exposes `rework_count` / `replan_count`.
  Covered by:
  - `tests/unit/test_simple_surface.py::test_runtime_built_in_step_state_updates_and_checkpoints_for_simple_steps`
  - `tests/unit/test_simple_surface.py::test_runtime_step_state_restores_built_ins_and_custom_fields_on_resume`

- Public `StateVar` surface is reintroduced on `autoloop` / `autoloop.simple`.
  Covered by:
  - `tests/unit/test_simple_surface.py::test_autoloop_root_exports_only_the_canonical_public_surface`

- `StateVar` sugar compiles to Pydantic-backed step state.
  Covered by:
  - `tests/unit/test_simple_surface.py::test_produce_verify_step_accepts_statevar_mapping_sugar`
  - `tests/unit/test_simple_surface.py::test_simple_runtime_step_state_uses_pydantic_models_and_serializes_for_checkpoints`

- Ambiguous `StateVar(None)` is rejected.
  Covered by:
  - `tests/unit/test_simple_surface.py::test_produce_verify_step_rejects_ambiguous_statevar_none_defaults`

- Mutable literal defaults require `default_factory`.
  Covered by:
  - `tests/unit/test_simple_surface.py::test_produce_verify_step_rejects_mutable_statevar_defaults_without_factory`
  - `tests/unit/test_simple_surface.py::test_produce_verify_step_accepts_typed_statevar_default_factories`

- Reserved built-in names are rejected for custom state.
  Covered by:
  - `tests/unit/test_simple_surface.py::test_produce_verify_step_rejects_reserved_custom_state_field_names`

- Built-in and custom step state persist through checkpoint and resume.
  Covered by:
  - `tests/unit/test_simple_surface.py::test_simple_runtime_step_state_uses_pydantic_models_and_serializes_for_checkpoints`
  - `tests/unit/test_simple_surface.py::test_runtime_step_state_restores_built_ins_and_custom_fields_on_resume`

- Runtime surfaces remain intentionally out of scope for `item_state` / `step_item_state`.
  Covered by:
  - `tests/unit/test_simple_surface.py::test_simple_workflow_rejects_item_state_prompt_placeholders`
  - `tests/unit/test_simple_surface.py::test_simple_workflow_rejects_step_item_state_prompt_placeholders`
  - `tests/unit/test_simple_surface.py::test_simple_context_suppresses_unmodeled_item_state_surfaces`

## Preserved Invariants Checked

- Canonical simple signatures remain unchanged outside the existing `produce_verify_step(..., state=...)` surface.
- `core` still does not export `StateVar`.
- The intentional `autoloop_v3.core` hard-failure remains enforced by strictness coverage.

## Edge Cases And Failure Paths

- Invalid mapping entries that are not `StateVar(...)`.
- Reserved-name collisions for both `BaseModel` and `StateVar` declarations.
- Resume restores previously checkpointed built-in counters before the next visit increment.

## Flake Risk / Stabilization

- Tests use `ScriptedLLMProvider`, `InMemoryCheckpointStore`, and `InMemorySessionStore` only.
- Resume coverage uses a single deterministic in-memory checkpoint store and fixed provider turn queues; no timing or external I/O is involved.

## Known Gaps

- This phase does not add worklist `item_state`, step-item state, or telemetry/history tests because those behaviors are explicitly deferred.
