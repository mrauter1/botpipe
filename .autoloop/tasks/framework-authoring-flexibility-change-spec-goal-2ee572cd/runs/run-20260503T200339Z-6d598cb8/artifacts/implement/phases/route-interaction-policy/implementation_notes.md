# Implementation Notes

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: implement
- Phase ID: route-interaction-policy
- Phase Directory Key: route-interaction-policy
- Phase Title: Route Policy Rebase
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/steps.py`
- `autoloop/simple.py`
- `autoloop/core/discovery.py`
- `autoloop/core/lowering.py`
- `autoloop/core/compiler.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/providers/models.py`
- `autoloop/core/providers/rendering.py`
- `autoloop/core/providers/retries.py`
- `autoloop/runtime/config.py`
- `autoloop/runtime/runner.py`
- `autoloop/core/__init__.py`
- `autoloop/__init__.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/unit/test_provider_retries.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_canonical_runtime_contracts.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_provider_backends.py`
- `decisions.txt`

## Symbols touched

- `ControlRoutes`
- `normalize_control_routes`
- `RuntimeInteractionPolicy`
- `WorkflowDefinition.authored_transitions`
- `WorkflowDefinition.runtime_control_routes_by_step`
- `CompiledStep.authored_routes`
- `CompiledStep.runtime_control_routes`
- `CompiledStep.provider_visible_routes_interactive`
- `CompiledStep.provider_visible_routes_full_auto`
- `CompiledRoute.provider_visible_interactive`
- `CompiledRoute.provider_visible_full_auto`
- `CompiledRoute.is_runtime_control`
- `Engine(..., interaction_policy=...)`
- `ProviderContractBuilder.available_routes()`

## Checklist mapping

- AC-1: Implemented via `RuntimeInteractionPolicy`, provider-contract filtering, and runner `full_auto -> allow_provider_questions=False`.
- AC-2: Implemented by removing default `blocked`/`failed` injection and updating provider contract expectations.
- AC-3: Implemented by deleting hard-coded `blocked`/`failed` reason validation for provider and non-provider events.
- AC-4: Implemented by normalizing simple booleans and core declarations through `ControlRoutes`.

## Assumptions

- Phase scope stops at route-policy/runtime-plumbing work and does not add the later inspection/doc surfaces beyond the compiled metadata needed to keep route views consistent.
- Global authored `question` routes follow the same full-auto visibility rule as step-authored `question` routes unless a provider-facing step opts into `question="always"`.

## Preserved invariants

- `CompiledStep.available_routes` remains the full execution-legal route set.
- Explicit authored `blocked`/`failed` routes remain legal and keep existing status/terminal behavior.
- Runtime provider failures still flow through retry/failure context; no provider `failed` shim was added back.
- Existing simple `control_routes=False` still means no injected question route.

## Intended behavior changes

- Provider-facing defaults now inject only `question`; default `blocked`/`failed` are gone.
- Python and child-workflow steps no longer receive default `failed`.
- Provider-visible `question` is hidden in full-auto unless the step explicitly opts into `ControlRoutes(question="always")`.
- Provider prompt/retry guidance no longer instructs models to supply special `blocked`/`failed` reasons.

## Known non-changes

- No lazy worklist/session/effects/validation-helper work was started in this phase.
- No broad inspection/static-graph payload expansion was added yet; the compiled metadata exists for later phases.
- No compatibility shim preserves legacy provider-visible `blocked`/`failed`.

## Expected side effects

- Topology hashes change because compiled route-view metadata now includes authored/runtime-control/provider-visible distinctions.
- Runtime config now accepts `runtime.full_auto`.

## Validation performed

- `python3 -m compileall autoloop tests` succeeded.
- Executable smoke tests could not run in this shell because `pytest` and runtime dependency `pydantic` are not installed.

## Deduplication / centralization

- Route-visibility policy is centralized in compiled route/step metadata plus `ProviderContractBuilder`, instead of re-deriving visibility ad hoc in provider-facing paths.
- Simple and core authoring now share the same `ControlRoutes` normalization path.
