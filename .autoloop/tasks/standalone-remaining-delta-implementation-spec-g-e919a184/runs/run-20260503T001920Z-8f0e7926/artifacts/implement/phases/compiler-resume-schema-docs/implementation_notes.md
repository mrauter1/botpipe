# Implementation Notes

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: implement
- Phase ID: compiler-resume-schema-docs
- Phase Directory Key: compiler-resume-schema-docs
- Phase Title: Compiler Resume Schema And Docs
- Scope: phase-local producer artifact

## Files Changed

- `autoloop/core/compiler.py`
- `autoloop/core/engine.py`
- `autoloop/core/extensions.py`
- `autoloop/core/history.py`
- `autoloop/core/operations.py`
- `autoloop/core/schema_registry.py`
- `autoloop/extensions/git/runtime.py`
- `autoloop/runtime/config.py`
- `autoloop/runtime/git_tracking.py`
- `autoloop/runtime/inspection.py`
- `autoloop/runtime/runner.py`
- `autoloop/runtime/stores/filesystem.py`
- `autoloop/runtime/tracing.py`
- `autoloop/runtime/workspace.py`
- `docs/architecture.md`
- `docs/authoring.md`
- `tests/runtime/test_optional_extensions.py`
- `tests/runtime/test_provider_backends.py`
- `tests/runtime/test_runtime_git_tracking.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/runtime/test_workspace_and_context.py`

## Symbols Touched

- `compile_workflow`, `_workflow_compile_cache_key`
- `ExtensionFailurePolicy`
- `validate_persisted_schema`, `migrate_schemaless_payload`
- `RuntimeConfig.resume_topology_mismatch_behavior`
- `GitTrackingRuntimeConfig.failure_policy`
- `TracingRuntimeConfig.failure_policy`
- `_resume_topology_mismatch_warning`, `_load_saved_run_topology_payload`, `_load_run_metadata_payload`
- `Engine._validate_resume_checkpoint_target`

## Checklist Mapping

- Plan milestone 4 / compiler cache: replaced class-attached compiled-workflow caching with explicit compiler-module caching keyed by workflow definition and source fingerprint; added regression test proving source changes recompile.
- Plan milestone 4 / resume: resume now validates continuation against the checkpoint step, reads saved topology artifacts, warns by default on saved-contract mismatch, and hard-fails only in strict mode; covered by runtime resume tests.
- Plan milestone 4 / schema: persisted readers now validate schema ids consistently and only accept schema-less legacy payloads through explicit reader-local migration hooks.
- Plan milestone 4 / extension failure policy: runtime tracing/git config and handling now use `propagate` vs `record_and_continue`; optional-extension tests were updated to assert preserved original failure causes.
- Plan milestone 4 / boundaries and docs: public docs describe `autoloop` as the authoring surface and `autoloop.core` as internal/power-user; runtime config tests cover the final policy names and defaults.

## Assumptions

- Saved topology mismatch should not block resume if the checkpoint step still resolves in the current compiled workflow.
- Reader-local schema migration is sufficient for the remaining schema-less persisted payloads in active runtime consumers.

## Preserved Invariants

- Resume still fails clearly when the checkpoint cannot identify a declared current step.
- Critical extension failures still propagate instead of being downgraded silently.
- Persisted artifact readers still reject explicit unknown schema ids.
- No new compatibility alias was added for removed `failure_mode` config keys or class-attached compiler cache state.

## Intended Behavior Changes

- New runs recompile when workflow source or step topology changes instead of reusing `workflow_cls.__compiled_workflow__`.
- Resume topology/source mismatches emit a run warning and continue by default.
- Strict resume mode now requires `RuntimeConfig.resume_topology_mismatch_behavior="fail"`.
- Runtime extension policy names are now `propagate` and `record_and_continue`.

## Known Non-Changes

- This phase does not redesign optimizer behavior beyond keeping runtime/status consumers on stable persisted artifacts and public imports.
- This phase does not introduce broader legacy-schema migration machinery beyond explicit reader-local hooks.

## Expected Side Effects

- Existing runtime config files that still use `failure_mode` now fail validation and must be updated to `failure_policy`.
- Runs resumed against changed workflow source will record a warning in `run.json` instead of failing immediately.

## Validation Performed

- `python3 -m py_compile autoloop/core/compiler.py autoloop/core/schema_registry.py autoloop/core/extensions.py autoloop/core/engine.py autoloop/core/history.py autoloop/core/operations.py autoloop/runtime/config.py autoloop/runtime/git_tracking.py autoloop/runtime/tracing.py autoloop/runtime/runner.py autoloop/runtime/inspection.py autoloop/runtime/workspace.py autoloop/runtime/stores/filesystem.py autoloop/extensions/git/runtime.py tests/runtime/test_workspace_and_context.py tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_git_tracking.py tests/runtime/test_provider_backends.py tests/runtime/test_optional_extensions.py`
- `.venv/bin/pytest -q tests/runtime/test_workspace_and_context.py -k 'resume_topology or compile_workflow_recompiles or migrate_schema_less'`
- `.venv/bin/pytest -q tests/runtime/test_runtime_tracing.py -k 'record_and_continue'`
- `.venv/bin/pytest -q tests/runtime/test_runtime_git_tracking.py -k 'record_and_continue'`
- `.venv/bin/pytest -q tests/runtime/test_provider_backends.py -k 'resolve_runtime_config_defaults_enable_git_tracking_and_tracing or resolve_runtime_config_merges_runtime_file_overrides_and_preserves_defaults'`
- `.venv/bin/pytest -q tests/runtime/test_optional_extensions.py -k 'propagate_policy'`
- `rg -n '^(from|import) (core|runtime|stdlib|extensions)(\\.|\\s|$)' autoloop --glob '*.py'`
- `rg -n '\\bfailure_mode\\b' autoloop tests docs --glob '*.py' --glob '*.md' --glob '*.yaml' --glob '*.yml'`

## Deduplication / Centralization

- Centralized explicit schema-less migration behind `validate_persisted_schema(..., legacy_migrator=...)` instead of leaving per-reader ad hoc missing-schema acceptance.
- Kept resume mismatch policy in runner-level helpers so engine resume logic only validates the executable checkpoint target and does not reintroduce runner-owned topology policy.
