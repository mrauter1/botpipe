# Test Strategy

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: test
- Phase ID: policy-codex
- Phase Directory Key: policy-codex
- Phase Title: Codex Emission
- Scope: phase-local producer artifact

## Coverage Map

- Behavior: Codex full-auto/workspace-write emission writes run-scoped `config.toml` under `<run_dir>/provider_policy/<step-key>/codex/` and maps writable roots plus network access.
  Coverage: `tests/runtime/test_provider_policy_emitters.py::test_codex_emitter_full_auto_sandboxed_emits_workspace_write_config`
- Behavior: Unsupported Codex mappings produce target-scoped capability reports with validation-mode decisions before execution.
  Coverage: `tests/runtime/test_provider_policy_emitters.py::test_codex_emitter_records_unsupported_deny_read_with_warn_validation`, `test_codex_emitter_records_unsupported_domain_filters`, `test_codex_emitter_raises_when_unsupported_validation_is_fail`
- Behavior: Narrowed `allow_read` remains an unsafe expansion and must not be reported as enforced state.
  Coverage: `tests/runtime/test_provider_policy_emitters.py::test_codex_emitter_raises_for_unsafe_expansion_when_read_roots_are_narrowed`, `test_codex_emitter_does_not_claim_read_root_enforcement_for_narrowed_allow_read`, `tests/runtime/test_runtime_providers.py::test_codex_transport_capability_report_keeps_narrowed_read_roots_unenforced`
- Behavior: Codex transport and sync operation execution pass run-scoped policy env and preserve policy metadata/report paths.
  Coverage: `tests/runtime/test_runtime_providers.py::test_codex_transport_emits_run_scoped_policy_artifacts_and_metadata`, `test_codex_operation_executor_uses_policy_env_and_metadata`

## Preserved Invariants

- No user-level Codex config file is written; tests assert run-scoped `CODEX_HOME`.
- Provider metadata continues to point at emitted `effective_policy.json` and `capability_report.json`.
- Unsupported/unsafe mappings fail or warn deterministically based on explicit validation config.

## Edge Cases

- Narrowed read roots on Codex are treated as unsafe because Codex lacks read-root enforcement.
- Domain allow/deny filters and deny-read rules remain unsupported but still emit capability reports.

## Failure Paths

- Unsupported mappings with `unsupported="fail"` abort emission before provider execution.
- Unsafe narrowed read roots with `unsafe_expansion="fail"` abort emission before provider execution.

## Known Gaps

- Claude-specific emission is intentionally out of scope for this phase.
- Tests rely on fake subprocess/help surfaces; they validate emitted artifacts and wiring without invoking real Codex binaries.
