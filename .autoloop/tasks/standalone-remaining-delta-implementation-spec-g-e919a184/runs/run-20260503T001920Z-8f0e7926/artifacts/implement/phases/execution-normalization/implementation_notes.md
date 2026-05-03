# Implementation Notes

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: implement
- Phase ID: execution-normalization
- Phase Directory Key: execution-normalization
- Phase Title: Execution Normalization
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched
- `StepExecutionResult`
- `RouteFinalizationResult`
- `PairProviderResult`
- `ProviderExecResult`
- `ProviderContractBuilder`
- `Engine._execute_pair_step`
- `Engine._execute_llm_step`
- `Engine._execute_workflow_step`
- `Engine._run_pair_step`
- `Engine._provider_exec_result`
- `Engine._build_step_finalization_record`
- `StepDispatcher.execute`
- `RouteFinalizer.finalize`

## Checklist mapping
- Milestone 2 / AC-1: replaced active step-dispatch and finalization tuple plumbing with `StepExecutionResult`, `RouteFinalizationResult`, and `PairProviderResult`.
- Milestone 2 / AC-2: preserved direct-control normalization across `before`, `before_producer`, `before_verifier`, and `on_taken` while routing all execution exits through the same dataclass-backed result path.
- Milestone 2 / AC-3: moved provider-visible contract assembly into `ProviderContractBuilder` and updated producer/verifier/llm requests to consume it.

## Assumptions
- Internal execution dataclasses may carry a small amount of extra data beyond the request sketch when needed to preserve current behavior and avoid a second compatibility layer.

## Preserved invariants
- Hook/direct-control validation still runs through the existing runtime-control and route validation helpers.
- Provider-visible route filtering still honors `provider_visible`.
- Pending input, handoff scheduling, and hook redirect tracing payloads are unchanged.

## Intended behavior changes
- Successful `after_producer` and `before_verifier` state mutations now survive through verifier success and final route finalization instead of being overwritten by the earlier state snapshot.

## Known non-changes
- Hook normalization shape and route-finalizer semantics were not broadened beyond this phase slice.
- Resume/cache/schema work remains deferred to later phases.

## Expected side effects
- `Engine.run` now consumes one step-result object instead of unpacking positional tuples.
- Provider request contract assembly is centralized in one collaborator-owned seam for later extraction/hardening work.

## Validation performed
- `python3 -m py_compile autoloop/core/engine.py autoloop/core/engine_collaborators.py tests/contract/test_engine_contracts.py`
- Added contract regression `test_pair_hooks_before_verifier_preserve_state_mutations_on_success`.
- Dynamic execution validation was blocked in this shell because the available `python3` environment lacks project dependencies such as `pydantic` and `pytest`.

## Deduplication / centralization
- Centralized step-transition construction in `Engine._build_step_finalization_record`, `_step_result_from_direct_control`, and `_step_result_from_route_finalization`.
- Centralized provider contract assembly in `ProviderContractBuilder` instead of three inline request-construction branches in `Engine`.
