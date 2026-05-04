# Test Strategy

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: test
- Phase ID: public-surface-polish
- Phase Directory Key: public-surface-polish
- Phase Title: Public Surface Cleanup
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 `Effects` remains intentional public hook-control API:
  - `tests/unit/test_simple_surface.py`
    - `test_effect_bundle_accepts_runtime_controls_as_event_overrides`
  - `tests/contract/test_engine_contracts.py`
    - `test_after_hook_effect_event_takes_precedence_over_exhausted_route`
    - `test_after_hook_effect_runtime_controls_match_direct_controls`
- AC-2 `validation_step` remains `python_step` sugar with explicit feedback writes and optional failed routing:
  - `tests/unit/test_simple_surface.py`
    - `test_validation_step_lowers_to_python_step_with_feedback_write_and_optional_failed_route`
  - preserved runtime behavior already covered in `tests/contract/test_engine_contracts.py`
    - `test_validation_step_valid_routes_to_default_done_and_emits_runtime_event`
    - `test_validation_step_invalid_writes_feedback_and_routes_repair`
    - `test_validation_step_exception_uses_failed_route_when_configured`
- AC-3 docs/examples no longer teach default `blocked` / `failed`, full-auto-visible default `question`, or `Artifact.managed` authoring:
  - `tests/test_architecture_baseline_docs.py`
    - `test_docs_cover_route_policy_lazy_runtime_and_managed_artifact_role`
    - `test_scoped_prompt_readmes_keep_shared_contract_sections_and_new_route_vocabulary`
    - `test_workflow_package_docs_use_question_only_runtime_control_wording`
  - runtime package-specific doc assertions preserved in `tests/runtime/test_*`
    - prompt README shared-section / route wording checks for affected workflow packages

## Preserved invariants checked

- `Effects.then(...)` still aliases `Effects(event=...)`.
- Worklist mutations still persist before direct runtime controls are finalized.
- `validation_step(...)` still materializes as `PythonStepDeclaration` and keeps explicit `writes`.
- Workflow docs and prompt READMEs still keep their required section markers and payload references after the wording sweep.

## Edge cases / failure paths

- `Effects` event override beats exhausted worklist routing.
- `RequestInput`, `Goto`, and `Fail` returned through `Effects` match direct-control behavior at terminalization time.
- Workflow package docs cannot drift back to `Reserved routes:` or managed-artifact authoring wording.

## Flake / stability notes

- Coverage is deterministic: no timing, network, or nondeterministic ordering dependencies.
- Validation used a temporary local virtualenv only to supply `pytest` / `pydantic`; runtime assertions themselves stay filesystem-local and scripted-provider-local.

## Known gaps

- I did not broaden this turn into full runtime workflow execution suites beyond the doc/readme assertions and focused contract/unit paths already changed for this phase.
