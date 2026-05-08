# Implementation Notes

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: implement
- Phase ID: sdk-runtime-alignment
- Phase Directory Key: sdk-runtime-alignment
- Phase Title: SDK And Runtime Alignment
- Scope: phase-local producer artifact

## Files changed

- `autoloop/sdk.py`
- `autoloop/core/operations.py`
- `autoloop/runtime/provider_policy_resolver.py`
- `autoloop/runtime/runner.py`
- `autoloop/core/engine.py`
- `tests/unit/test_sdk_facade.py`
- `tests/runtime/test_sdk_policy.py`
- `tests/runtime/test_provider_policy_steps.py`

## Symbols touched

- `Autoloop.__init__`
- `Autoloop.run`
- `Autoloop.step`
- `Autoloop.llm`
- `Autoloop.classify`
- `Autoloop.prompt_step`
- `Autoloop.produce_verify_step`
- `Autoloop.python_step`
- `Autoloop.workflow_step`
- `_coerce_sdk_input`
- `_normalize_sdk_policy_input`
- `_sdk_step_invocation_layer`
- `_normalize_sdk_writes`
- `_build_synthetic_step_workflow`
- `ProviderPolicyResolver`
- `create_provider_policy_resolver`
- `RunnerOptions`
- `llm_call`
- `classify_call`

## Checklist mapping

- Plan milestone 3: completed. SDK public naming aligned to `workspace`, `input`, `params`, and `policy`.
- Plan milestone 3: completed. Runner/resolver now own SDK default-policy and run-policy merge order.
- Plan milestone 3: completed. Direct SDK operations use the shared resolver path.
- Plan milestone 3: completed. `client.step(..., policy=...)` is invocation-local and does not mutate the caller step.
- Plan milestone 4: completed for phase scope. Added SDK/runtime policy tests and updated SDK facade tests.

## Intended behavior changes

- Public SDK constructor now accepts `workspace=` and `default_policy=`; removed public `root=` compatibility.
- Public SDK run/step entrypoints now use `input=` and `params=`; removed public `typed_input=` and `parameters=` compatibility.
- Direct SDK `llm()` and `classify()` now inherit runtime-config policy defaults plus SDK client default policy before applying explicit operation policy.
- SDK helper methods now accept `policy=` as authored step policy and simple-style `writes=(Md(...), Json(...), Text(...), Raw(...))`.

## Preserved invariants

- Internal runtime path handling still uses resolved absolute workspace roots.
- `.autoloop` remains state storage only; policy paths remain workspace-relative.
- Inline operations inside workflow execution still inherit the resolved current-step policy before explicit operation policy.
- SDK run policy is execution-only and does not participate in workflow topology hashing.
- No provider emitter behavior or strict-policy semantics changed.

## Centralization / deduplication

- Policy merge ownership stays in `ProviderPolicyResolver`; SDK methods now pass layers via `RunnerOptions` instead of pre-merging.
- Direct SDK operations reuse the same resolver code path as workflow execution instead of ad hoc `resolve_policy_layer(...)` calls.

## Assumptions

- Shallow cloning is sufficient for invocation-local step wrapping because the SDK only rewrites the policy field on the wrapper object.
- Existing runtime-config parsing already produces the concrete runtime-config default provider policy layer; this phase only threads SDK-specific layers around it.

## Known non-changes

- No CLI policy flags were added.
- No runtime config syntax changed.
- No provider policy emitter code changed.

## Expected side effects

- Existing external code using removed SDK keywords now fails fast with `TypeError`.
- Existing tests or examples using mapping-style helper writes remain easy to migrate to tuple-style artifact specs.

## Validation performed

- `python3 -m py_compile autoloop/sdk.py autoloop/core/operations.py autoloop/runtime/provider_policy_resolver.py autoloop/runtime/runner.py autoloop/core/engine.py tests/unit/test_sdk_facade.py tests/runtime/test_sdk_policy.py`
- `.venv-test/bin/python -m pytest tests/unit/test_sdk_facade.py tests/runtime/test_sdk_policy.py -q`
- `.venv-test/bin/python -m pytest tests/unit/test_provider_policy.py tests/runtime/test_provider_policy_steps.py tests/runtime/test_provider_policy_emitters.py tests/runtime/test_provider_policy_config.py tests/unit/test_simple_surface.py tests/unit/test_sdk_facade.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py -q`
