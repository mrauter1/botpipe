# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: session-continuity
- Phase Directory Key: session-continuity
- Phase Title: Session Continuity Model
- Scope: phase-local producer artifact

## Files Changed

- `core/sessions.py`
- `core/steps.py`
- `core/context.py`
- `core/compiler.py`
- `core/engine.py`
- `core/stores/protocols.py`
- `core/stores/memory.py`
- `core/workflow_capabilities.py`
- `runtime/stores/filesystem.py`
- `runtime/runner.py`
- `runtime/providers/_common.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_compatibility_runtime.py`

## Symbols Touched

- `Continuity`, `SessionKey`, `DEFAULT_SESSION_NAME`, `derive_session_key`
- `Session`
- `Context.open_session`, `Context.get_session`
- `CompiledWorkflow.sessions`, `CompiledWorkflow.default_session_name`
- `Engine._select_session`
- `SessionBinding`, `SessionSnapshot`
- `InMemorySessionStore`
- `FilesystemSessionStore`, `FilesystemCheckpointStore`

## Checklist Mapping

- Phase 4 / Session model: implemented continuity model, default session support, `SessionKey`, and auto-open behavior.
- Phase 4 / Context APIs: preserved `ctx.open_session(..., scope=...)` and positional scope; added `continuity=` and `key=`.
- Phase 4 / Store migration: implemented new session-key store paths and backward-readable checkpoint/session restore.
- Deferred intentionally: typed params, routes/effects, worklists, child IO, docs/public root-shim broadening.

## Assumptions

- Worklist-backed continuity is allowed to exist as a hook before full worklist runtime support; using it without a current item raises at resolution time.
- The implicit default session should affect runtime behavior now, but authoring-facing capability snapshots can keep suppressing it until the public-surface phase.

## Preserved Invariants

- `ctx.open_session(session)` still works.
- `ctx.open_session(session, scope="x")` and `ctx.open_session(session, "x")` still work.
- Legacy checkpoint/session payloads with `ref_name`/`scope` and `active_scopes` still restore.
- Provider boundary remains `session_id` plus provider metadata; cross-provider resume checks still apply only when provider metadata is actually present.

## Intended Behavior Changes

- LLM and pair steps now auto-open declared sessions on first use instead of failing when `on_start` did not open them first.
- Provider-owned steps without an explicit session now use the implicit runtime default session slot.
- Session persistence now resolves filesystem paths by continuity domain (`run`, `task`, `work_item`, `explicit_scope`, `explicit_key`, `fresh`) instead of only by global/scope.

## Known Non-Changes

- Root `workflow` shim export broadening is deferred; `Continuity` stays available via `core.sessions` for now.
- `SessionPaths` callback shape was not expanded; custom strategies still receive `(run_dir, ref_name, scope)`.

## Expected Side Effects

- Checkpoints now serialize both `active_keys_by_slot` and compatibility `active_scopes`.
- Capability/decomposition helper snapshots continue to show `session_name=None` for steps that only use the implicit default session.

## Validation Performed

- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/unit/test_primitives_and_stores.py -q`
- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/contract/test_engine_contracts.py -q`
- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/runtime/test_compatibility_runtime.py tests/runtime/test_runtime_providers.py -q`
- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/runtime/test_workspace_and_context.py tests/runtime/test_package_cli.py -q`
- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/unit/test_stdlib_and_extensions.py -q`
- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/strictness/test_no_compat.py -q`
- `/home/rauter/autoloop_v3/.venv/bin/pytest -q`

## Full Suite Status

- `pytest -q` still reports unrelated out-of-phase failures in:
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `tests/test_architecture_baseline_docs.py`
- The first two fail on directory-backed artifact validation paths owned by prior artifact-contract work; the docs baseline failures depend on repository memory/doc state outside this phase.

## Deduplication / Centralization

- Session-key derivation is centralized in `core/sessions.py`.
- Legacy/new session serialization compatibility is centralized in `core/stores/protocols.py` and `runtime/stores/filesystem.py`.
