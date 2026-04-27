# Implementation Notes

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: implement
- Phase ID: provider-and-engine-contract
- Phase Directory Key: provider-and-engine-contract
- Phase Title: Provider and engine contract
- Scope: phase-local producer artifact

## Files changed
- `core/providers/parsing.py`
- `core/providers/models.py`
- `core/providers/__init__.py`
- `core/providers/fake.py`
- `core/providers/rendering.py`
- `core/engine.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/contract/test_engine_contracts.py`
- `decisions.txt`

## Symbols touched
- `core.providers.parsing.parse_outcome_json`
- `core.providers.models.ProviderReadableRef`
- `core.providers.rendering.render_provider_turn`
- `core.providers.rendering._render_control_response`
- `core.engine.Engine._execute_step`
- `core.engine.Engine._execute_workflow_step`
- `core.engine.Engine._finalize_step_result`
- `core.engine.Engine._validate_outcome`
- `core.engine.Engine._request_control_contract`
- `core.engine.Engine._provider_readable_refs`
- `core.engine.Engine._run_workflow_step`
- `core.engine.Engine._resolve_workflow_step_message`
- `core.engine.Engine._write_workflow_step_outputs`

## Checklist mapping
- Plan milestone 3 / AC-1: provider request/rendering now carries readable/required/writable artifacts without legacy route-contract fields and renders the explicit control-response contract.
- Plan milestone 3 / AC-1: shared provider outcome parsing now requires a non-empty top-level `reason` so rendered control-response prompts and runtime parsing enforce the same `{tag, reason, payload}` shape.
- Plan milestone 3 / AC-1: provider boundary tests now assert runtime contract sections, declared-vs-workspace readable refs, and producer-vs-control response modes.
- Plan milestone 3 / AC-2: engine finalization now re-resolves artifacts after after-hook state changes, preserves provider-attributable retry behavior across route overrides, and validates `question` / `blocked` / `failed` control-route requirements.
- Plan milestone 3 / AC-2: `WorkflowStep` now executes directly through `ctx.invoke_workflow(...)`, maps child terminals to runtime events, writes declared output artifacts, and works in verifier rework loops.
- Deferred within this phase: repo-wide migration of remaining legacy `route_contracts` references in bundled workflows, active docs, and untouched contract/runtime tests.

## Assumptions
- Relative workspace-path reads should resolve from `Context.root` at runtime when they are not declared artifact reads.
- Producer turns keep returning raw text; only verifier/llm turns render the `{tag, reason, payload}` control-response contract.

## Preserved invariants
- Required inputs still fail before provider/system/workflow execution.
- Provider retries still use `ProviderRetryPolicy`; this phase only changes which failures remain provider-attributable after hook-driven route overrides.
- Runtime runner still provides filesystem prompt resolution; low-level engine usage without a prompt registry remains limited for relative file prompts.

## Intended behavior changes
- Readable refs now distinguish declared artifacts from workspace-path reads and surface existence independently of required-input semantics.
- Rendered verifier/llm prompts now include `### Control response` with the exact JSON envelope and route-specific `question` / `blocked` / `failed` rules.
- Rendered-provider JSON parsing now rejects control responses that omit `reason`, even on non-`blocked`/non-`failed` routes.
- Invalid provider outcomes for `question` without `question` text or `blocked` / `failed` without `reason` now fail as `invalid_payload`.
- `WorkflowStep` no longer depends on generated system handlers and now writes child-result payload artifacts directly in the engine.
- After-hook state mutations now affect final artifact resolution and required-output enforcement.

## Known non-changes
- The broader bundled workflow tree under `workflows/*` still contains out-of-phase `route_contracts` usage.
- `tests/contract/test_engine_contracts.py` still contains untouched legacy scenarios outside the focused phase coverage added here.
- Capability payload support-file naming (`contracts_path` vs `spec_paths` / `support_paths`) was not changed in this phase.

## Expected side effects
- Provider-call telemetry now records readable refs with declared/workspace provenance instead of treating them as required/writable artifact refs.
- Workflow-step failures that depend on hook-mutated artifact paths now report the post-hook resolved path in checkpoint failure context.
- Direct workflow-step execution now emits child-result artifacts even when the final route is later overridden by an after hook.

## Validation performed
- `.venv/bin/python -m py_compile core/providers/parsing.py core/providers/models.py core/providers/rendering.py core/providers/fake.py core/providers/__init__.py core/engine.py tests/unit/test_provider_boundary_core.py tests/contract/test_engine_contracts.py`
- `.venv/bin/python -m pytest tests/unit/test_provider_boundary_core.py`
- `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py::test_llm_requests_include_step_control_contracts tests/contract/test_engine_contracts.py::test_pair_requests_include_step_control_contracts tests/contract/test_engine_contracts.py::test_question_route_requires_question_field tests/contract/test_engine_contracts.py::test_blocked_and_failed_routes_require_reason_field tests/contract/test_engine_contracts.py::test_workflow_step_after_hook_can_override_route_after_child_completion tests/contract/test_engine_contracts.py::test_workflow_step_maps_child_terminals_and_writes_outputs tests/contract/test_engine_contracts.py::test_after_hook_route_override_recomputes_required_outputs tests/contract/test_engine_contracts.py::test_after_hook_state_mutation_re_resolves_artifact_paths_before_final_output_validation tests/contract/test_engine_contracts.py::test_workflow_step_honors_hooks_and_can_participate_in_verifier_rework_loops`
- `.venv/bin/python -m pytest tests/unit/test_simple_surface.py`

## Validation limits
- Full-suite `pytest` was not used as an acceptance gate for this phase because many untouched runtime/contract files still contain out-of-phase legacy `RouteContract` coverage and bundled workflow fixtures.
- Repo-wide anti-regression grep for removed terms is still deferred to the later migration/docs phases.

## Deduplication / centralization
- Direct workflow-step child result serialization is centralized in `core.engine` so simple workflows and core workflows share one runtime path.
- Provider rendering now uses one shared readable-artifact model and one shared control-response renderer for verifier/llm turns.
