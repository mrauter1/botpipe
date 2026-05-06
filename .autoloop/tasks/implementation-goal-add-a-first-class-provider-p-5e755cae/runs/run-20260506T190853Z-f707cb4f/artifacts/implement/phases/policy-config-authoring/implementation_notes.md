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
- `autoloop/core/compiler.py`
- `autoloop/core/__init__.py`
- `tests/runtime/test_provider_policy_config.py`
- `tests/runtime/test_package_cli.py`
- `tests/unit/test_simple_surface.py`

## Symbols touched
- `ProviderPolicyRuntimeConfig`
- `ProviderPolicyRuntimeConfigOverride`
- `parse_policy_runtime_config()`
- `resolve_runtime_config()`
- `_resolve_explicit_legacy_provider_model_overrides()`
- `Step.provider_policy`
- `WorkflowDefinition.workflow_policy`
- `_validate_workflow_policy()`
- `PromptStep`, `ProduceVerifyStep`, `PythonStep`, `ChildWorkflowStep`
- `simple.step()`, `produce_verify_step()`, `python_step()`, `workflow_step()`

## Checklist mapping
- AC-1: added resolved `provider_policy` defaults, legacy-field-to-policy mapping, and CLI validation override merge.
- AC-2: extended the narrow YAML loader to parse inline lists and null values used by `provider_policy` examples.
- Authoring surface scope: added workflow-level `policy` retention on `WorkflowDefinition` plus per-step `policy=` retention across simple declarations and lowering.

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
- Explicit `provider_policy.default: null` and `provider_policy.validation: null` now fail fast instead of silently falling back to inherited defaults.
- Workflow-level `policy = ProviderPolicy(...)` is now retained on discovered workflow metadata and validated as a concrete `ProviderPolicy`.

## Known non-changes
- No compile-time topology hashing or compiled-step policy fields yet.
- No per-turn resolved policy, capability reports, or subprocess wiring yet.
- No inline `llm()` or `classify()` policy overrides yet.

## Validation performed
- `python3 -m py_compile autoloop/runtime/config.py autoloop/runtime/cli.py autoloop/core/steps.py autoloop/simple.py autoloop/core/discovery.py autoloop/core/__init__.py tests/runtime/test_provider_policy_config.py tests/unit/test_simple_surface.py`
- `python3 -m py_compile autoloop/runtime/config.py autoloop/core/discovery.py autoloop/core/compiler.py tests/runtime/test_provider_policy_config.py tests/unit/test_simple_surface.py`
- `.venv/bin/python -m pytest tests/runtime/test_provider_policy_config.py tests/unit/test_simple_surface.py -q`

## Validation notes
- Focused `py_compile` checks passed before and after the reviewer-follow-up edits.
- Focused pytest passed: `96 passed` with only pre-existing schema-shadowing warnings from exported workflow fixtures.

## Deduplication / centralization
- Kept provider-policy merge, legacy-field mapping, and validation-override handling centralized in `autoloop/runtime/config.py`.
- Reused core step objects as the single retention point for authored step policy metadata and added `WorkflowDefinition.workflow_policy` as the matching workflow-level source of truth for later compiler/runtime phases.
