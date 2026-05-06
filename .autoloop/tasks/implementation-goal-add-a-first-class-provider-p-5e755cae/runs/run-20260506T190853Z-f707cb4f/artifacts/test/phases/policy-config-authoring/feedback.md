# Test Author ↔ Test Auditor Feedback

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: test
- Phase ID: policy-config-authoring
- Phase Directory Key: policy-config-authoring
- Phase Title: Config And Authoring
- Scope: phase-local authoritative verifier artifact

## Test Additions

- Extended `tests/runtime/test_provider_policy_config.py` with regression coverage for:
  - full runtime-config `--policy-file` shape acceptance,
  - inherited strict-policy clearing via explicit `provider_policy.strict: null`,
  - explicit CLI `model` / `model_effort` mirroring into `provider_policy.default`.
- Re-ran the focused runtime-config suite: `16 passed` via `.venv/bin/python -m pytest tests/runtime/test_provider_policy_config.py -q`.

## Audit Follow-up

- No new findings in this pass.
- The added tests cover the highest-risk phase-local regressions: no-config system-default preservation, explicit-only legacy model mirroring, the two supported policy-file entry shapes, explicit-null rejection for `default` and `validation`, and the allowed `strict: null` reset path.
