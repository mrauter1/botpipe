# Recursive Framework Evolution Remediation Plan

## Intent

Implement the requested greenfield cleanup exactly as specified: remove public provider-factory surfaces, remove framework/runtime `thread_id`, drop recursive-wrapper legacy CLI and repo-layout assumptions, and harden docs/tests so those compatibility paths cannot return. Preserve feature compatibility only.

## Current Repo Findings

- `runtime/cli.py` still exposes `--provider-factory`, reads `AUTOLOOP_PROVIDER_FACTORY`, and resolves providers through `load_provider_factory(...)`.
- `runtime/config.py` already supports typed provider names but still routes generic model/effort overrides as Codex-only and has no CLI `--provider` override.
- `runtime/runner.py` still owns `module:function` loading through `load_provider_factory(...)`.
- `runtime/stores/filesystem.py` still reads `thread_id`, mirrors `session_id` into `thread_id`, and injects `thread_id` into framework metadata.
- `workflows/autoloop_v1/parity.py` already reads `session_id` from session payloads but still names and emits a `thread_id` field in raw-log helpers.
- `recursive_autoloop/run_recursive_autoloop.sh` still auto-detects package vs legacy CLI mode and can emit `--intent`, `--pairs`, and legacy `--task-id` invocations.
- Recursive templates still point readers at `src/autoloop/...` and old monolithic-runner ownership.
- Tests currently codify the public provider-factory path and only partially guard the wrapper against legacy drift.

## Non-Negotiable Behavior Changes

- `--provider-factory` and `AUTOLOOP_PROVIDER_FACTORY` are removed from the public contract; only `cli.main(..., provider_factory=...)` remains as a non-public test/programmatic seam.
- Persisted session payloads become `session_id`-only. Old payloads that depend on `thread_id` compatibility are intentionally unsupported after this refactor.
- The recursive wrapper requires the package CLI surface on PATH and no longer auto-detects or falls back to legacy CLIs.

## Target Interfaces

### Provider Resolution

- Mutating CLI commands expose `--provider`, `--model`, `--model-effort`, and `--max-steps`.
- `resolve_runtime_config(root, args)` resolves provider choice through typed config plus CLI overrides.
- Generic overrides must target the effective provider:
  - `provider.name=codex` or `--provider codex` means generic model/effort overrides land on `provider.codex`.
  - `provider.name=claude` or `--provider claude` means generic model/effort overrides land on `provider.claude`.
- `runtime/provider_backends.py` becomes the only public CLI-to-provider resolution boundary and exposes:

```python
def resolve_provider_backend(*, config: ResolvedRuntimeConfig) -> LLMProvider:
    ...
```

- `runtime/cli.py::_resolve_provider(...)` keeps this order:
  1. Use the non-public `provider_factory` seam when passed directly to `cli.main(...)`.
  2. Otherwise call `resolve_provider_backend(config=config)`.
  3. Never read CLI/env factory strings.

### Session Payload

Canonical persisted payload:

```json
{
  "mode": "persistent",
  "provider": "codex",
  "session_id": "opaque-provider-session-id-or-null",
  "provider_metadata": {},
  "model_override": null,
  "effort_override": null,
  "pending_clarification_note": null,
  "created_at": "2026-04-23T00:00:00+00:00",
  "last_used_at": null
}
```

- `SessionBinding.session_id` remains the sole framework continuation handle.
- Provider-private naming such as provider-specific thread ids stays inside adapter code only.
- If raw logs need to expose the continuation handle, use `session_id` naming or omit it; no generic `thread_id` field remains outside provider-private code.

### Recursive Wrapper

- Start command:

```bash
autoloop run "$AUTOLOOP_WORKFLOW_NAME" "$task_id" --root "$WORKSPACE" --message "$message"
```

- Resume command:

```bash
autoloop resume "$AUTOLOOP_WORKFLOW_NAME" "$task_id" --root "$WORKSPACE"
```

- Wrapper validation only checks that `autoloop --help` exposes the package CLI surface and fails fast otherwise.

## Out Of Scope

- Any plugin/registry architecture for providers.
- Any backward-compatibility alias for old session payloads, factory flags, or legacy recursive CLI syntax.
- Any broader workflow-kernel redesign beyond the requested boundary cleanup.
- Any edits to verifier-owned criteria artifacts.

## Implementation Phases

### Phase 1: Add the Provider Backend Boundary

- Add `runtime/provider_backends.py` as the framework-owned provider resolver.
- Add minimal internal Codex and Claude adapter entrypoints if the resolver cannot stay local to one file.
- Make unavailable-provider failures precise `ConfigError`s instead of preserving factory injection.
- Add focused resolver tests before public CLI cleanup starts.

Regression control:
- Do not remove the existing CLI factory path until the built-in resolver and tests exist.
- Keep the adapter surface local; do not introduce registries or dynamic import indirection.

Rollback:
- Revert the resolver and adapter files together if provider construction semantics are wrong.

### Phase 2: Remove Public Provider-Factory Surfaces

- Add `--provider` to mutating CLI parsers.
- Fix `resolve_runtime_config(...)` merge semantics so generic config and CLI overrides target the effective provider rather than hard-coding Codex fields.
- Remove `--provider-factory`, `AUTOLOOP_PROVIDER_FACTORY`, and `load_provider_factory(...)` from the public CLI path.
- Delete `load_provider_factory(...)` from `runtime/runner.py` once no code uses it.
- Preserve `cli.main(..., provider_factory=...)` with its current direct-injection role for tests.

Regression control:
- Add CLI tests for help text, unknown-argument rejection, selected-provider config merging, and the retained non-public seam.
- Keep provider resolution typed; do not add any public “factory” config field.

Rollback:
- Revert phases 1 and 2 together if the public CLI cannot construct providers reliably.

### Phase 3: Remove Framework `thread_id` Compatibility

- Update `runtime/stores/filesystem.py` so `load_session_payload(...)`, `write_session_payload(...)`, `_session_payload_from_values(...)`, and `ensure_session_payload_placeholder(...)` only use canonical `session_id`.
- Remove the missing-provider Codex compatibility branch from session loading.
- Rename or remove `thread_id` helpers and raw-log fields in `workflows/autoloop_v1/parity.py`.
- Keep checkpoint and `SessionBinding` semantics unchanged apart from the field cleanup.

Regression control:
- Add tests for placeholder schema, roundtrip persistence, provider metadata preservation, and resumability through `session_id`.
- Treat old `thread_id`-only payloads as intentionally unsupported and verify only canonical payload behavior.

Rollback:
- Revert the entire session-schema change as one slice; do not cherry-pick mixed readers and writers.

### Phase 4: Make the Recursive Wrapper Package-Only

- Remove `AUTOLOOP_CLI_MODE`, `detect_autoloop_cli_mode`, and all legacy branching from `recursive_autoloop/run_recursive_autoloop.sh`.
- Keep nested-git environment isolation, recovery logging, and package-mode task discovery intact.
- Rewrite bootstrap/cycle templates to current repo layout and package-CLI doctrine.
- Update `framework_evolution_charter.md.tmpl` and `framework_roadmap.md.tmpl` if they still imply `src/autoloop/main.py` ownership.

Regression control:
- Strengthen wrapper tests to assert forbidden strings and branches are absent, not just that package commands are present.
- Review every recursive template in `recursive_autoloop/run_recursive_autoloop_templates/` for stale layout references before closing the phase.

Rollback:
- Revert the wrapper and template set together if generated task instructions become inconsistent.

### Phase 5: Harden Docs, Strictness, And Full Verification

- Update `docs/architecture.md` and `docs/authoring.md` to document provider selection via typed config and generic flags, opaque `session_id`, and package-only recursive operation.
- Scrub any remaining active doc references to removed surfaces if they are within the maintained docs set.
- Extend `tests/test_architecture_baseline_docs.py` and `tests/strictness/test_no_compat.py` to forbid `--provider-factory`, `AUTOLOOP_PROVIDER_FACTORY`, `thread_id`, `src/autoloop/`, and wrapper legacy branches across active source/docs/tests.
- Run targeted suites first, then full `pytest`, and fix any Autoloop-v1 parity fallout.

Regression control:
- Keep strictness scan scope limited to active source/docs/tests so task artifacts and historical snapshots do not create false failures.
- Do not land doc and strictness assertions until the code and templates already reflect the cleaned contract.

Rollback:
- Revert doc and strictness changes only after the underlying code rollback, not before.

## Validation Plan

Targeted suites:

- `pytest tests/runtime/test_package_cli.py`
- `pytest tests/runtime/test_workflow_integration_parity.py`
- `pytest tests/runtime/test_compatibility_runtime.py`
- `pytest tests/test_architecture_baseline_docs.py tests/strictness/test_no_compat.py`

Full verification:

- `pytest`

Manual smoke expectations:

- `autoloop --help` and mutating subcommand help show `--provider` and no `--provider-factory`.
- Fresh session JSON contains `session_id` and no `thread_id`.
- The recursive wrapper emits only package `autoloop run/resume` commands.

## Risk Register

- `R1`: The repo currently has no built-in production provider adapters. Mitigation: introduce the resolver boundary first and fail with precise `ConfigError`s rather than preserving public factory injection.
- `R2`: Generic model/effort overrides can silently remain Codex-only. Mitigation: add selected-provider merge tests for both Codex and Claude paths before deleting the factory flag.
- `R3`: Old on-disk runs that relied on `thread_id` become unresumable. Mitigation: make the behavior break explicit in docs/tests and validate only canonical new payloads.
- `R4`: One stale recursive template can silently reintroduce old repo-shape guidance. Mitigation: review every template under `recursive_autoloop/run_recursive_autoloop_templates/` and backstop with strictness tests.
- `R5`: Repo-wide forbidden-string scans can become noisy because task artifacts intentionally preserve old text. Mitigation: scope strictness checks to maintained source, docs, templates, and tests only.
