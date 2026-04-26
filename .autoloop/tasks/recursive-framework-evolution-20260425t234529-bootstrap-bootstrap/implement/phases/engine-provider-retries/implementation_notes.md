# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: implement
- Phase ID: engine-provider-retries
- Phase Directory Key: engine-provider-retries
- Phase Title: Engine Retry Semantics
- Scope: phase-local producer artifact

## Files changed
- `core/providers/retries.py`
- `core/providers/__init__.py`
- `core/steps.py`
- `core/compiler.py`
- `core/validation.py`
- `core/engine.py`
- `core/providers/fake.py`
- `core/__init__.py`
- `workflow/__init__.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/strictness/test_no_compat.py`

## Symbols touched
- `ProviderRetryPolicy`, `build_retry_feedback`
- `Step.retry_policy`, `LLMStep`, `PairStep`, `SystemStep`
- `CompiledStep.retry_policy`
- `Engine._execute_pair_step`, `Engine._execute_llm_step`
- `Engine._request_control_contract`
- `Engine._provider_artifact_ref`, `Engine._provider_artifact_refs`, `Engine._route_required_artifacts_for_step`
- `Engine._next_retry_feedback`, `Engine._annotate_retry_exhaustion`, `Engine._provider_retry_kind`
- `ScriptedLLMProvider.ProviderCall`

## Checklist mapping
- Provider retry policy module and retry feedback rendering: completed in `core/providers/retries.py`.
- Compiled step retry metadata plus public exports: completed in `core/steps.py`, `core/compiler.py`, `core/validation.py`, `core/__init__.py`, `workflow/__init__.py`.
- Engine retry loop and artifact-ref request enrichment: completed in `core/engine.py`.
- Retry-focused engine contract tests: completed in `tests/contract/test_engine_contracts.py` and `tests/unit/test_validation.py`.
- Strict authoring-surface expectation update for the new public export: completed in `tests/strictness/test_no_compat.py`.
- Deferred by phase contract: route handoff persistence/delivery, docs/baseline wording updates, and public CLI behavior changes.

## Assumptions
- Retry exhaustion metadata can be added inside existing `failure_context` without changing checkpoint schema.
- Provider-attributable artifact retries should apply only when artifact validation is tied to the provider-selected route, not a middleware-overridden route.
- Transport and malformed-output retries can be inferred from `ProviderExecutionError` messages when the originating provider layer did not attach an explicit retry kind.

## Preserved invariants
- Missing required input artifacts still fail before any provider call.
- Middleware/system route failures still do not retry.
- Handler exceptions still do not retry.
- Pair-step retries restart from producer and do not include prior raw output or transcript data in retry feedback.
- Raw output telemetry remains available through existing logs and `StepFinish`; retry feedback does not include raw provider output.

## Intended behavior changes
- `LLMStep` and `PairStep` now default to `ProviderRetryPolicy(max_attempts=3)`.
- Retryable provider failures rebuild semantic provider requests with artifact metadata, route-required artifacts, attempt counters, and retry feedback.
- Exhausted retry failures now checkpoint additive retry-attempt metadata in `failure_context`.

## Known non-changes
- No handoff effect or pending-handoff checkpoint support was added in this phase.
- No runtime transport changes were made beyond consuming the already-refactored rendered provider boundary.
- No docs or prompt README text was updated in this phase.

## Expected side effects
- Existing failure tests that assumed one provider attempt now need explicit `ProviderRetryPolicy(max_attempts=1)`.
- Semantic test providers now record additive request metadata (`required_artifacts`, `writable_artifacts`, retry fields), which broadens observability without changing their core queue behavior.

## Deduplication / centralization
- Retry-kind classification and retry-exhaustion annotation are centralized in `core/engine.py` rather than duplicated across pair/llm branches.
- Artifact-ref construction is centralized in dedicated engine helpers so provider request enrichment uses one path for both llm and pair turns.

## Validation performed
- `.venv/bin/pytest -q tests/unit/test_validation.py`
- `.venv/bin/pytest -q tests/contract/test_engine_contracts.py`
- `.venv/bin/pytest -q tests/runtime/test_runtime_providers.py`
- `.venv/bin/pytest -q tests/runtime/test_provider_backends.py`
- `.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`
- `.venv/bin/pytest -q`
