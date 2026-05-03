# Test Strategy

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: diagnostics-and-late-bound-prompts
- Phase Directory Key: diagnostics-and-late-bound-prompts
- Phase Title: Diagnostics And Late-Bound Prompts
- Scope: phase-local producer artifact

## Coverage map

- AC-1 dual-role artifact diagnostics
  - `tests/unit/test_validation.py::test_validation_rejects_same_identity_artifact_declared_workflow_level_and_produced`
  - Verifies same-identity workflow-level plus produced artifacts fail at compile time and the message includes producer-step guidance.

- AC-2 simple prompt validation for late-bound runtime facts
  - `tests/unit/test_simple_surface.py::test_simple_workflow_accepts_scoped_runtime_item_prompt_placeholders`
  - `tests/unit/test_simple_surface.py::test_simple_workflow_rejects_runtime_item_prompt_placeholders_without_scope`
  - `tests/unit/test_simple_surface.py::test_simple_workflow_accepts_late_bound_worklist_prompt_placeholders`
  - `tests/unit/test_simple_surface.py::test_simple_workflow_rejects_unknown_worklist_prompt_placeholders`
  - Preserves strict compile-time rejection for invalid scope/worklist declarations while allowing the requested `item.*` / `worklist.*` late-bound forms.

- AC-3 runtime prompt placeholder behavior
  - `tests/contract/test_engine_contracts.py::test_prompt_runtime_lazily_renders_item_and_worklist_placeholders`
  - `tests/contract/test_engine_contracts.py::test_prompt_runtime_reports_missing_payload_path_with_placeholder_context`
  - `tests/contract/test_engine_contracts.py::test_prompt_runtime_reports_missing_current_item_with_placeholder_context`
  - `tests/contract/test_engine_contracts.py::test_prompt_runtime_reports_missing_worklist_source_with_placeholder_context`
  - Covers happy-path rendering plus payload-path, current-item, and source-loading failures through the engine/provider boundary.

- AC-3 runtime artifact placeholder behavior
  - `tests/unit/test_primitives_and_stores.py::test_artifact_template_resolution_supports_worklist_placeholders`
  - `tests/unit/test_primitives_and_stores.py::test_artifact_template_resolution_lazily_materializes_worklist_placeholders`
  - `tests/unit/test_primitives_and_stores.py::test_artifact_template_resolution_reports_missing_payload_path`
  - `tests/unit/test_primitives_and_stores.py::test_artifact_template_resolution_reports_missing_current_item`
  - `tests/unit/test_primitives_and_stores.py::test_artifact_template_resolution_reports_worklist_source_loading_failure`
  - Keeps artifact-template coverage at the direct helper seam per the earlier lazy-selection test split.

## Preserved invariants checked

- Separate-identity duplicate and ambiguous artifact diagnostics were not re-baselined by this phase.
- Non-scoped `item.*` prompt placeholders still fail validation.
- Unknown worklists still fail validation instead of becoming late-bound at runtime.

## Edge cases and failure paths

- Empty worklist selection for `worklist.<name>.current...`
- Missing payload path under `item.payload...`
- Missing artifact-backed worklist source during lazy first use

## Flake risk / stabilization

- Tests use inline prompts, in-memory stores, deterministic worklists, and scripted providers only.
- No timing, network, subprocess, or nondeterministic ordering dependencies were added.

## Known gaps

- Full execution of the targeted suites was not possible in this shell because `pytest` and runtime deps were unavailable; only `py_compile` syntax validation could be performed here.
