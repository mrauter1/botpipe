# Test Strategy

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: test
- Phase ID: policy-config-authoring
- Phase Directory Key: policy-config-authoring
- Phase Title: Config And Authoring
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Runtime config defaults and preserved invariants:
  - `tests/runtime/test_provider_policy_config.py` covers no-config resolution to `SYSTEM_DEFAULT_PROVIDER_POLICY`, global/workspace default merges, explicit workspace strict merges, legacy provider model and effort mapping, and legacy `runtime.full_auto` mapping.
- Policy file entry shapes:
  - Covers both supported `--policy-file` payload forms: root-level `provider_policy` payload and full runtime-config document containing `provider_policy`.
- Null-handling distinctions:
  - Covers explicit rejection of `provider_policy.default: null` and `provider_policy.validation: null`.
  - Covers the one allowed explicit null reset path: workspace `provider_policy.strict: null` clearing inherited strict config.
- CLI and authoring-adjacent behavior:
  - Covers CLI validation-mode overrides and explicit CLI `model` / `model_effort` mapping into `provider_policy.default`.
  - Existing unit coverage in `tests/unit/test_simple_surface.py` retains workflow-level and step-level policy authoring behavior for `simple.Workflow`, `step`, and `python_step`.
- Narrow fallback YAML loader:
  - Covers inline list parsing and nested `null` parsing under `provider_policy.strict.*` with PyYAML disabled.

## Edge Cases

- Explicit null values are tested separately from omitted keys to preserve merge-layer semantics.
- Policy-file shape coverage distinguishes wrapper and non-wrapper payloads to catch future parser regressions.
- CLI model mapping is tested independently from config-file mapping to guard the explicit-only mirroring rule.

## Failure Paths

- Unknown `provider_policy` keys fail with a path-aware error.
- Invalid policy enums fail with a path-aware error.
- Invalid explicit nulls for `default` and `validation` fail fast.

## Known Gaps

- This phase does not add new transport or emitter tests because those behaviors are explicitly out of scope.
- Workflow-level policy retention is already covered in unit authoring tests; this turn adds no extra core-workflow metaclass-specific test because the active phase deliverables are runtime config and simple authoring surfaces.
