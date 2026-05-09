# Test Strategy

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: strictness-cleanup
- Phase Directory Key: strictness-cleanup
- Phase Title: Strictness And Cleanup
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 removed-internal strictness scan
  - `tests/strictness/test_no_internal_compat_layers.py`
  - Covers forbidden internal symbols and file removal for `Compiled*`, `plan_adapters`, `compile_workflow_plan`, `_COMPILED_WORKFLOW_CACHE`, `_DirectRuntimeControl`, `RouteFinalizationResult`, `_compiled_step`, and `original_step`
- AC-1 stale identity scan
  - `tests/strictness/test_botlane_identity.py`
  - Covers `.botlane` identity constants, `botlane.sdk_task/v1`, `botlane.branch_results/v1`, `botlane_optimizer` import identity, and no stale `autoloop*` tokens across `botlane`, `botlane_optimizer`, and `tests`
- AC-2 runtime import boundary
  - `tests/strictness/test_core_runtime_boundary.py`
  - AST-checks that `botlane/core/**/*.py` does not import `botlane.runtime` outside `TYPE_CHECKING`
- Adapter-era assertion cleanup / typed plan boundary preservation
  - `tests/unit/test_validation.py`
  - Covers disabled step-local route suppression, typed route required-write lowering, workflow/step artifact inventory access through canonical plan helpers, and user-facing `RoutingError` / route-summary behavior
  - `tests/contract/engine/test_hooks.py`
  - Covers child-workflow step plans using typed `ChildWorkflowStepPlan.workflow` instead of authored-step backrefs
  - `tests/contract/engine/test_worklists.py`
  - Covers compile-time placeholder validation for missing item-state fields after placeholder centralization
  - `tests/unit/test_execution_frame_context_parity.py`
  - Covers renamed internal context sync helpers while keeping public `Context` mutators hidden
- JSON/public serialization safety for typed refs
  - `tests/unit/optimizer/test_portfolio_helpers.py`
  - Covers workflow capability snapshot JSON writing after typed artifact refs moved internal
  - `tests/unit/optimizer/test_selected_workflow_helpers.py`
  - Covers selected-workflow capability/decomposition/evaluation artifacts, plus explicit assertion that serialized `reads` / `requires` / `writes` / `log_artifacts` stay string-shaped
- Single-step preserved behavior
  - `tests/contract/test_single_step_plan_equivalence.py`
  - Keeps policy-layering and `SELF` lowering checks aligned with canonical one-step planning without stale `original_step` naming

## Preserved invariants checked

- Strictness tests scan maintained code only and do not reintroduce deleted internals or stale identity strings
- JSON-facing capability/selected-workflow artifacts remain string-serializable even though runtime/compiler plans use typed refs
- Disabled local routes suppress same-tag global fallback
- Public `Context` no longer exposes tested `_set_*` mutator names
- Final repo suite remains green after the phase-local test additions

## Edge cases and failure paths

- Disabled step-local route shadowing a global route with the same tag
- Explicit/global required-write serialization versus internal typed `ArtifactId`
- Missing worklist item-state field detected at compile time
- Selected-workflow payload writing for both package and single-file workflow references

## Determinism / flake controls

- All coverage is filesystem-local and synchronous; no network or time-sensitive assertions added
- Snapshot assertions read deterministic JSON payloads from temp directories
- Final validation uses the repo virtualenv directly: `.venv/bin/python -m pytest -q`

## Validation performed

- `.venv/bin/python -m pytest -q tests/unit/test_validation.py::test_route_helper_defaults_and_global_suppression_compile_from_route_metadata tests/unit/optimizer/test_selected_workflow_helpers.py::test_decomposition_helper_writes_selected_workflow_identity_authoring_surface_and_compiled_routes`
- `.venv/bin/python -m pytest -q`

## Known gaps

- The suite still emits one pre-existing `RuntimeWarning` in `tests/unit/test_provider_boundary_core.py`; phase scope treats it as non-blocking because the full suite passes
