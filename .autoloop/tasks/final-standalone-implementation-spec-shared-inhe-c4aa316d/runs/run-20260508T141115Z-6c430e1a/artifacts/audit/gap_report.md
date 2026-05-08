# Original intent considered

- Implement a single shared public `Policy(...)` facade in `autoloop/policy.py`.
- Align public SDK/simple naming on `workspace`, `input`, `params`, and shared `PolicyInput` handling where applicable.
- Remove conflicting public compatibility layers, especially SDK `root=`, SDK `typed_input=`, public `PolicyOverride`, and raw strings for enum-backed `Policy(...)` fields.
- Preserve the exact export contract: `autoloop.policy` exports `PolicyInput`, `autoloop.sdk` re-exports it, and `autoloop.__init__` / `autoloop.simple` do not.

# Clarifications / superseding decisions

- The raw phase log contains no later user clarification that changes the initial request; the request snapshot remains authoritative.
- Planner decision block 2 records that the export contract is exact: `autoloop.simple` must not publicly export `PolicyInput` ([decisions.txt:6-7](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/final-standalone-implementation-spec-shared-inhe-c4aa316d/runs/run-20260508T141115Z-6c430e1a/decisions.txt:6)).
- Implementer/test decisions record one analyzed divergence for dangerous manual access: when a public layer requests `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS` over the system default `full_auto_sandboxed` base, resolution coerces that inherited permission mode to manual `ask` so the public dangerous-manual example can resolve under the unchanged core schema ([decisions.txt:11-14](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/final-standalone-implementation-spec-shared-inhe-c4aa316d/runs/run-20260508T141115Z-6c430e1a/decisions.txt:11)).

# Implemented behavior

- `autoloop/policy.py` exists and provides the shared public enums, sparse `Policy`, `PolicyInput`, `resolve_policy_layer`, and layer payload support.
- `autoloop.__init__`, `autoloop.simple`, and `autoloop.sdk` re-export the shared policy enums and `Policy`; `autoloop.sdk` also re-exports `PolicyInput`.
- SDK constructor and run/step surfaces use `workspace=`, `input=`, and `params=`; removed public `root=` / `typed_input=` usage is enforced by tests.
- Runtime policy merge order is centralized in `autoloop/runtime/provider_policy_resolver.py`.
- Verified passing suites:
  - `./.venv/bin/pytest tests/unit/test_policy.py tests/runtime/test_sdk_policy.py`
  - `./.venv/bin/pytest tests/unit/test_sdk_facade.py -q`
  - `./.venv/bin/pytest tests/unit/test_provider_policy.py tests/runtime/test_provider_policy_steps.py tests/runtime/test_provider_policy_emitters.py`
  - `./.venv/bin/pytest tests/runtime/test_provider_policy_config.py tests/unit/test_simple_surface.py`

# Unresolved gaps

- `autoloop.simple` still leaks `PolicyInput` as a public importable symbol. The module imports `PolicyInput` directly from `autoloop.policy` and keeps it bound at module scope ([autoloop/simple.py:29-44](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py:29)).
- `autoloop.simple` also defines a duplicate public-facing alias `ProviderPolicyInput = PolicyInput` at module scope ([autoloop/simple.py:42-44](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py:42)), which conflicts with the greenfield requirement not to duplicate policy type definitions on the simple surface.
- This is observable public behavior, not just an internal style issue:
  - `from autoloop.simple import PolicyInput` succeeds.
  - `from autoloop.simple import ProviderPolicyInput` succeeds.
- The dedicated export-contract regression test fails:
  - `./.venv/bin/pytest tests/unit/test_simple_policy.py -q`
  - Failure: `tests/unit/test_simple_policy.py::test_policy_input_export_matrix_matches_phase_contract`
  - The failing expectation is the required `ImportError` for `from autoloop.simple import PolicyInput` ([tests/unit/test_simple_policy.py:95-110](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_simple_policy.py:95)).

# Differences justified by later clarification or analysis

- Dangerous manual access semantics differ from one sentence in the original spec. The spec simultaneously required `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` to preserve inherited permission mode and required the dangerous-manual example to resolve correctly while also forbidding changes to the core provider-policy schema and keeping `SYSTEM_DEFAULT_PROVIDER_POLICY.permissions.mode == "full_auto_sandboxed"`.
- Under the unchanged core schema, inheriting `full_auto_sandboxed` into `danger_full_access` is invalid. The recorded implementation choice to coerce only that inherited default case to manual `ask` is consistent with the example-driven intent and is explicitly captured in the decisions ledger and tests. I do not treat that difference as an unresolved gap.

# Recommended next run

Implement a narrow follow-up that finishes the simple-surface export cleanup:

- Remove `PolicyInput` from the public `autoloop.simple` module namespace while keeping internal typing support.
- Remove or privatize the stale `ProviderPolicyInput` alias from `autoloop.simple`.
- Keep `PolicyInput` re-exported only from `autoloop.policy` and `autoloop.sdk`.
- Re-run at least:
  - `./.venv/bin/pytest tests/unit/test_simple_policy.py`
  - `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py tests/unit/test_sdk_facade.py`
