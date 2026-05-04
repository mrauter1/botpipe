# Implementation Notes

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: implement
- Phase ID: route-and-artifact-contracts
- Phase Directory Key: route-and-artifact-contracts
- Phase Title: Route And Artifact Core
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/artifacts.py`
- `autoloop/core/compiler.py`
- `autoloop/core/inventory.py`
- `autoloop/core/lowering.py`
- `autoloop/core/providers/parsing.py`
- `autoloop/core/providers/rendering.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_runtime_providers.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/unit/test_validation.py`

## Symbols touched
- `Artifact`
- `collect_artifact_inventory`
- `_raise_workflow_level_artifact_conflict_error`
- `_raise_duplicate_qualified_artifact_name_error`
- `definition_default_route_summaries`
- `_compile_global_routes`
- `parse_outcome_json`
- `_render_control_response`

## Checklist mapping
- AC-1: removed managed-role artifact enforcement; workflow-level artifacts now keep canonical public names while step writers append `producer_steps`.
- AC-2: rendered provider parsing now defaults missing `reason` to `""`, requires top-level `question` only for `tag="question"`, and preserves `invalid_payload` retry semantics for rendered question-payload failures; added direct/rendered parity coverage.
- AC-3: preserved policy-gated `question` visibility; added rendered full-auto illegal-question regression coverage and kept no default `blocked`/`failed`.
- AC-4: authored `blocked`/`failed` stay legal without hidden reason validation; fallback summaries now treat them as ordinary authored routes.
- AC-5: preserved explicit child-workflow `failed`/`blocked` mapping behavior; parity coverage was kept in the targeted engine contract slice.

## Assumptions
- Phase scope is limited to route/artifact contract changes; lazy worklist restore, worklist source policy, public `Effects` narrowing, and broader docs sweeps remain deferred.
- Existing pure workflow-level duplicate-name validation should keep its simpler legacy error shape to avoid widening unrelated fallout.

## Preserved invariants
- Step-local artifacts still bind to `step.artifact` qualified names when not declared workflow-level.
- Ambiguous short-name artifact references still fail rather than silently preferring one declaration.
- Provider/runtime validation still treats `question` as the only built-in route with special payload requirements.
- Child workflow runtime errors still name the step, child terminal, mapped route, declared routes, and recommended fix.

## Intended behavior changes
- `Artifact.managed(...)`, `ArtifactRole`, and `role=` support were removed from the artifact declaration surface.
- A workflow-level artifact may also be written by one or more steps without being rebound to `step.artifact`.
- Rendered provider JSON may omit `reason`; missing values now normalize to `""`.
- Authored `blocked` and `failed` no longer inherit reserved-looking fallback summaries.
- Authored global `blocked`/`failed` routes now receive generic fallback summaries instead of `None`.

## Known non-changes
- No worklist materialization, checkpoint restore, session continuity, or inspection semantics were changed in this phase.
- No broad authoring-doc sweep was done here beyond prompt-contract text emitted by the runtime provider renderer.

## Expected side effects
- Provider prompts now describe `reason` as optional and show `question` as the only special top-level payload field.
- Workflow/static-graph consumers now see canonical workflow-level artifact names for dual-role artifacts and generic authored summaries for global `failed`/`blocked`.

## Validation performed
- `./.venv/bin/python -m pytest tests/unit/test_validation.py -q`
- `./.venv/bin/python -m pytest tests/runtime/test_runtime_providers.py -q -k "parse_outcome_json_accepts_plain_object or parse_outcome_json_accepts_fenced_json_block or parse_outcome_json_accepts_missing_reason_for_authored_routes or parse_outcome_json_rejects_question_without_question_field"`
- `./.venv/bin/python -m pytest tests/unit/test_provider_boundary_core.py -q -k "render_provider_turn_renders_markdown_contract_without_raw_output or parse_outcome_json_defaults_missing_reason_to_empty_string"`
- `./.venv/bin/python -m pytest tests/runtime/test_runtime_static_graph.py -q`
- `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -q -k "blocked_and_failed_routes_do_not_require_reason_field or rendered_provider_matches_direct_reason_optional_behavior_for_explicit_blocked_and_failed_routes or provider_question_route_is_illegal_in_full_auto_mode or rendered_provider_question_route_is_illegal_in_full_auto_mode"`

## Deduplication / centralization
- Kept canonical-name decisions centralized in `collect_artifact_inventory(...)` so compiler, engine, provider contracts, and route-required-write resolution all consume the same artifact identity.
- Centralized optional-reason and question-only payload handling in `parse_outcome_json(...)` rather than splitting rendered-provider behavior across parser and engine call sites.
- Kept rendered question-payload failures in the shared invalid-payload retry bucket by attaching failure metadata at parse time instead of teaching `Engine._provider_retry_kind(...)` another message-matching special case.
