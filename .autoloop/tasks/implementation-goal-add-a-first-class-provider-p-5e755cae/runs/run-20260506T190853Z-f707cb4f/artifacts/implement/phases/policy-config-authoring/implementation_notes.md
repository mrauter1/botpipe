# Implementation Notes

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-config-authoring
- Phase Directory Key: policy-config-authoring
- Phase Title: Config And Authoring
- Scope: phase-local producer artifact

## Files changed
- `autoloop/runtime/config.py`
- `autoloop/runtime/cli.py`
- `autoloop/core/steps.py`
- `autoloop/simple.py`
- `autoloop/core/discovery.py`
- `autoloop/core/__init__.py`
- `tests/runtime/test_provider_policy_config.py`
- `tests/runtime/test_package_cli.py`
- `tests/unit/test_simple_surface.py`

## Symbols touched
- `ProviderPolicyRuntimeConfig`
- `ProviderPolicyRuntimeConfigOverride`
- `parse_policy_runtime_config()`
- `resolve_runtime_config()`
- `Step.provider_policy`
- `PromptStep`, `ProduceVerifyStep`, `PythonStep`, `ChildWorkflowStep`
- `simple.step()`, `produce_verify_step()`, `python_step()`, `workflow_step()`

## Checklist mapping
- AC-1: added resolved `provider_policy` defaults, legacy-field-to-policy mapping, and CLI validation override merge.
- AC-2: extended the narrow YAML loader to parse inline lists and null values used by `provider_policy` examples.
- Authoring surface scope: added workflow-level `policy` slots plus per-step `policy=` retention across simple declarations and lowering.

## Assumptions
- `--policy-file` may contain either a full runtime-config document or a root-level `provider_policy` payload.
- Legacy provider model, effort, and `runtime.full_auto` inputs should fill policy defaults only when those policy fields were not explicitly set in merged `provider_policy` layers.

## Preserved invariants
- Existing provider config fields remain first-class runtime inputs.
- No provider user config files are written or mutated.
- This phase does not add runtime resolver, emitter, transport, or replay-fingerprint behavior.

## Intended behavior changes
- Runtime config now accepts top-level `provider_policy.default`, `provider_policy.strict`, and `provider_policy.validation`.
- CLI mutate commands now accept `--policy-file` and the three policy validation override flags.
- Simple/core step declarations now retain authored provider policy metadata, including `python_step(policy=...)` with explicit scope documentation.

## Known non-changes
- No compile-time topology hashing or compiled-step policy fields yet.
- No per-turn resolved policy, capability reports, or subprocess wiring yet.
- No inline `llm()` or `classify()` policy overrides yet.

## Validation performed
- `python3 -m py_compile autoloop/runtime/config.py autoloop/runtime/cli.py autoloop/core/steps.py autoloop/simple.py autoloop/core/discovery.py autoloop/core/__init__.py tests/runtime/test_provider_policy_config.py tests/unit/test_simple_surface.py`
- `.venv/bin/python -m pytest tests/runtime/test_provider_policy_config.py tests/runtime/test_provider_backends.py tests/runtime/test_package_cli.py tests/unit/test_simple_surface.py -q`

## Validation notes
- `py_compile` passed.
- `pytest` collection failed before reaching these tests because importing `autoloop` in this environment hits an existing circular import path through `autoloop.core.primitives` and `autoloop.core.providers.__init__`.

## Deduplication / centralization
- Kept provider-policy merge, legacy-field mapping, and validation-override handling centralized in `autoloop/runtime/config.py`.
- Reused core step objects as the single retention point for authored step policy metadata so later compiler/runtime phases can consume one surface.
