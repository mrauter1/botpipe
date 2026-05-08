# Original intent considered

The original request required the full correction spec, not only the first implementation phase: public `Policy(...)` payloads must serialize as `policy_layer`; concrete core payloads must serialize as `provider_policy` / `provider_policy_override`; compiler/topology fingerprinting must hash the unified payload path for every policy-input kind; public SDK/simple/core-normalization errors must stop leaking `ProviderPolicyOverride`; the public SDK must remain strict on `workspace`, `input`, and `params`; runtime CLI must require `--workspace` and reject `--root` if `autoloop/runtime/cli.py` is touched; public exports must stay clean; and the requested regression tests must exist.

# Clarifications / superseding decisions

No later user clarification in `raw_phase_log.md` overrides the request. The task-global decisions in `decisions.txt` reinforce the original spec rather than narrowing it:

- runtime CLI rename/removal stayed in scope because `autoloop/runtime/cli.py` was part of the touched public surface;
- compiler/topology fingerprinting had to stop special-casing concrete `ProviderPolicy`;
- public wording had to collapse internal core types into “core provider policy object”.

Early phase-local implementation notes deferred some work between phases, but those were execution-order notes, not authoritative intent changes. The final codebase includes subsequent public-surface and runtime-CLI phases, so those temporary deferrals do not justify any missing behavior at end state.

# Implemented behavior

- `autoloop/policy.py:292-311` now serializes nested public `Policy` bases as `{"kind": "policy_layer", ...}` and concrete `ProviderPolicy` bases as `{"kind": "provider_policy", ...}`.
- `autoloop/core/compiler.py:1589-1615` now emits `policy_layer`, `provider_policy`, and `provider_policy_override` from `_policy_input_payload(...)`, and `_policy_input_fingerprint(...)` hashes that unified payload for every non-`None` policy input.
- Public normalization/discovery wording is cleaned up in `autoloop/sdk.py:443-518,1140-1146`, `autoloop/simple.py:797-800`, `autoloop/core/steps.py:428-431`, `autoloop/core/discovery.py:358-364`, and `autoloop/policy.py:516-528`; public errors now refer to `Policy` or a `core provider policy object`.
- The public SDK surface remains strict: `Autoloop` exposes `workspace` in `autoloop/sdk.py:439-469`; `run(...)` and `step(...)` take `input` / `params` in `autoloop/sdk.py:483-520` and `689-743`; synthetic step workflows now synthesize `Params` models when needed in `autoloop/sdk.py:1692-1733`.
- Runtime CLI now requires `--workspace` with `WORKSPACE` metavar and keeps `root` internal only in `autoloop/runtime/cli.py:48-65`. Public help/examples were updated, including `docs/authoring.md:1235-1237`.
- Public export cleanup is covered and matches the requested surface: `autoloop.policy.__all__`, `autoloop.__all__`, `autoloop.sdk.__all__`, and `autoloop.simple.__all__` include the required policy symbols and do not expose `PolicyOverride`.

Evidence from tests:

- Policy payload/fingerprint coverage exists in `tests/unit/test_policy.py:174-344`.
- SDK/public-surface coverage exists in `tests/unit/test_sdk_facade.py:666-723,864-991`, `tests/unit/test_simple_surface.py:40-104`, and `tests/unit/test_simple_policy.py:15-171`.
- Runtime CLI coverage exists in `tests/runtime/test_package_cli.py:221-297` and `tests/runtime/test_runtime_cli_metadata_integration.py:390-418`.
- Recorded prior validation: `./.venv/bin/pytest tests/runtime/test_package_cli.py tests/runtime/test_runtime_cli_metadata_integration.py` passed with `49 passed`.
- Additional audit validation run on the final codebase: `./.venv/bin/pytest tests/unit/test_policy.py tests/unit/test_sdk_facade.py tests/unit/test_simple_surface.py tests/unit/test_simple_policy.py` passed with `167 passed in 3.53s`.

# Unresolved gaps

None material.

I did not find any remaining mismatch between the active correction spec and the final implementation. The required payload kinds, fingerprint behavior, public wording cleanup, strict SDK naming, runtime CLI `--workspace` migration, export cleanup, and targeted regression coverage are all present.

# Differences justified by later clarification or analysis

- Earlier implementation/test artifacts recorded blocked unit-test execution because they used the system interpreter without project dependencies. That is not an implementation gap: later phases already proved the repo virtualenv works, and this audit re-ran the missing unit suites successfully in `./.venv`.
- Early phase-local deferrals for public-surface and CLI work were resolved by later phases in the same run. Those notes describe sequencing, not a final divergence from intent.

# Recommended next run

No follow-up implementation run is required for this correction spec.
