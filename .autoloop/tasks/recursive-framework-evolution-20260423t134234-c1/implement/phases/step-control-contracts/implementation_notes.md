# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t134234-c1
- Pair: implement
- Phase ID: step-control-contracts
- Phase Directory Key: step-control-contracts
- Phase Title: Add Step Control Contracts
- Scope: phase-local producer artifact

## Files changed

- `core/steps.py`
- `core/validation.py`
- `core/compiler.py`
- `core/engine.py`
- `core/providers/models.py`
- `core/providers/fake.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched

- `Step.__init__`, `PairStep.__init__`, `LLMStep.__init__`, `SystemStep.__init__`
- `validate_workflow_definition`, `step_available_route_tags`, `compile_expected_output_contract`, `_validate_control_contracts`
- `CompiledStep`, `_compile_steps`, `_compile_expected_output_contract`
- `Engine._run_pair_step`, `Engine._run_llm_step`, `Engine._validate_outcome`, `Engine._request_control_contract`
- `ProducerRequest`, `VerifierRequest`, `LLMRequest`, `ProviderCall`

## Checklist mapping

- `AC-1`: strict steps can now declare optional `expected_output_schema` and `route_contracts`; compiled steps expose those fields plus runtime-derived `available_routes`.
- `AC-2`: engine/provider request plumbing now carries `expected_output_schema`, `available_routes`, and `route_contracts`; runtime validates illegal routes and invalid payloads without changing existing transition resolution.

## Assumptions

- Control contracts are provider-facing only for `PairStep` and `LLMStep`; `SystemStep` remains runtime-owned and rejects those declarations.
- Payload schemas may be declared as pydantic-compatible type specs or raw JSON Schema mappings.

## Preserved invariants

- `Outcome.tag` remains the only route carrier.
- `available_routes` are derived from declared transitions; no duplicate route tables were introduced.
- Workflows that do not declare control contracts keep their existing behavior.

## Intended behavior changes

- Provider outcomes with illegal route tags now fail early with `ProviderExecutionError`.
- When a step declares `expected_output_schema`, `Outcome.payload` is validated before outcome handlers run.

## Known non-changes

- No CLI, workspace layout, checkpoint format, or session persistence changes.
- No real Codex/Claude provider adapters or new provider-facing packet abstraction.
- No out-of-phase recursive template or wrapper edits were made.

## Expected side effects

- Provider request objects now expose `expected_output_schema`, `available_routes`, and `route_contracts`.
- Fake-provider call records include the same control-contract fields for test assertions.

## Validation performed

- `.venv/bin/python -m pytest -q tests/unit/test_validation.py`
- `.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_workflow_integration_parity.py`
- `.venv/bin/python -m pytest -q tests/test_architecture_baseline_docs.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_package_cli.py` -> unrelated existing failures in untouched recursive wrapper/template files (`require_package_autoloop_cli` missing in shell script parsing and legacy `src/autoloop/` references in recursive templates)

## Deduplication / centralization decisions

- Centralized route derivation and schema-compilation helpers in `core/validation.py` so validation and compilation share one control-contract source of truth.
