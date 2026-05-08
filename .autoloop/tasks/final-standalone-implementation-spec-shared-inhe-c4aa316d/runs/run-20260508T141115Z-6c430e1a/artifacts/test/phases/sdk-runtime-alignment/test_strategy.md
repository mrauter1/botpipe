# Test Strategy

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: test
- Phase ID: sdk-runtime-alignment
- Phase Directory Key: sdk-runtime-alignment
- Phase Title: SDK And Runtime Alignment
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- SDK naming surface:
  `tests/unit/test_sdk_facade.py`
  Covers `workspace=`, `input=`, `params=`, and rejection of removed `root=`, `typed_input=`, and `parameters=` keywords.

- SDK helper canonical shapes:
  `tests/unit/test_sdk_facade.py`
  Covers helper-attached `policy=` and tuple-style `writes=(Md(...), ...)` delegation for `prompt_step`, `produce_verify_step`, `python_step`, and `workflow_step`.

- Resolver-owned merge order for workflow steps:
  `tests/runtime/test_sdk_policy.py`
  Covers SDK client default policy plus per-run override on workflow execution.

- Resolver-owned merge order for direct SDK operations:
  `tests/runtime/test_sdk_policy.py`
  Covers direct `client.llm()` / `client.classify()` inheritance from SDK default policy plus explicit operation override.

- Resolver-owned merge order for inline operations:
  `tests/runtime/test_sdk_policy.py`
  Covers runtime-config default policy, SDK default policy, workflow policy, SDK run policy, current step policy, and inline explicit policy on one `simple.llm(...)` call.

- Invocation-local `client.step(..., policy=...)` layering:
  `tests/runtime/test_sdk_policy.py`
  Covers authored-step policy preservation, per-invocation override precedence, and reuse of the same step object without mutation bleed-through.

- Workspace vs state-root contract:
  `tests/runtime/test_sdk_policy.py`
  Covers `context.root == workspace` even when `state_dir` is elsewhere, and preserves relative `allow_write="reports/"` in the effective provider policy.

## Preserved invariants checked

- Public SDK compatibility removals stay enforced as `TypeError`s.
- Step-authored policy remains authored policy after a `client.step(..., policy=...)` call.
- `allow_write` remains a relative policy path string rather than being rewritten to a state-root path.

## Edge and failure paths

- Removed keyword regressions are pinned with explicit failing calls.
- Invocation-local override tests ensure the second reuse of the same step falls back to the authored policy.

## Known gaps

- This phase did not add new provider-emitter tests because the contract here is resolver wiring and SDK surface behavior rather than emitter serialization.
