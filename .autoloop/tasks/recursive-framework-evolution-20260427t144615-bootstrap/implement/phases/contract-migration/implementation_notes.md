# Implementation Notes

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: contract-migration
- Phase Directory Key: contract-migration
- Phase Title: Compiler And Contract Migration
- Scope: phase-local producer artifact

## Files changed
- `core/steps.py`
- `core/validation.py`
- `core/compiler.py`
- `core/engine.py`
- `core/providers/models.py`
- `core/providers/rendered.py`
- `core/providers/rendering.py`
- `core/providers/fake.py`
- `core/workflow_capabilities.py`
- `runtime/static_graph.py`
- `runtime/cli.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_runtime_static_graph.py`
- `decisions.txt`

## Symbols touched
- `Step`, `PairStep`, `LLMStep`, `SystemStep`
- `normalize_step_route_metadata`, `normalize_step_route_contracts`
- `CompiledStep`
- `Engine._request_control_contract`, `Engine._required_output_artifacts`
- `ProviderTurnContext`, `ProducerRequest`, `VerifierRequest`, `LLMRequest`
- `render_provider_turn`
- `WorkflowStepCapability`, `workflow_static_step_graph_payload`

## Checklist mapping
- Plan milestone 2 / active phase AC-1: added compiled/provider/static support for `reads`, `route_infos`, and `route_required_outputs` with legacy aliases preserved.
- Plan milestone 2 / active phase AC-2: relaxed validation so application routes no longer require `route_contracts`; still validate artifact references and impossible read/require ordering.
- Plan milestone 2 / active phase AC-3: updated provider rendering wording so declared writable artifacts are governed surfaces, not an exclusive allow-list.

## Assumptions
- Legacy bundled workflows still rely on `route_contracts`; compatibility aliases must remain active in this phase.
- Route-specific required outputs should continue resolving against the existing artifact inventory model rather than introducing a new produced-only restriction mid-migration.

## Preserved invariants
- Runtime missing-artifact failure still applies only to `requires`.
- Route-contract-derived required-output enforcement still works for legacy workflows through normalized `route_required_outputs`.
- Undeclared workspace outputs remain allowed; provider prompts no longer imply otherwise.

## Intended behavior changes
- Compiled/provider/static metadata now exposes optional readable inputs separately from required inputs.
- Route summaries and route-required outputs are available through `route_infos` / `route_required_outputs` even when a step omits legacy `route_contracts`.
- Strict validation no longer rejects application routes solely because some routes omit legacy contracts.

## Known non-changes
- Public `RouteContract` exports and bundled workflow source imports were not removed in this phase.
- `WorkflowStep`, hook ordering, and simple-workflow lowering remain out of scope for this slice.
- `route_required_artifacts` remains available as a compatibility alias for existing callers.

## Expected side effects
- Static graph and workflow-capability payloads now include `reads`, `route_infos`, and `route_required_outputs`.
- Provider renderings show a new readable-inputs section and stronger wording around non-exclusive writable artifacts.

## Validation performed
- `.venv/bin/python -m pytest tests/unit/test_validation.py -q`
- `.venv/bin/python -m pytest tests/unit/test_provider_boundary_core.py -q`
- `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -q`
- `.venv/bin/python -m pytest tests/runtime/test_runtime_static_graph.py -q`

## Deduplication / centralization
- Centralized route summary and route-required-output normalization in `core.validation.normalize_step_route_metadata` so compiler, runtime enforcement, and provider payloads consume the same compatibility-normalized view.
