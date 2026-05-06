# Implementation Notes

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-claude-regression
- Phase Directory Key: policy-claude-regression
- Phase Title: Claude Emission And Regression Sweep
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/core/providers/rendering.py`
- `autoloop/core/providers/turns.py`
- `autoloop/runtime/config.py`
- `autoloop/runtime/providers/_common.py`
- `autoloop/runtime/providers/claude.py`
- `autoloop/runtime/providers/claude_policy.py`
- `tests/runtime/test_provider_backends.py`
- `tests/runtime/test_provider_policy_config.py`
- `tests/runtime/test_provider_policy_emitters.py`
- `tests/runtime/test_runtime_providers.py`
- `docs/architecture.md`
- `run decisions.txt` for non-obvious phase decisions

## Symbols Touched
- `RenderedProviderTurn.workspace_root`
- `render_provider_turn_with_policy()`
- `_context_workspace_root()`
- `_merge_provider_policy_config()`
- `_policy_layers_set_any_field()`
- `run_text_subprocess()`
- `ClaudeTransport`
- `build_claude_transport()`
- `build_claude_operation_executor()`
- `_prepare_turn_command()`
- `_emit_turn_policy()`
- `_with_policy_metadata()`
- `_emit_policy_event()`
- `_claude_subprocess_options()`
- `_validate_claude_surface()`
- `ClaudeCapabilities`
- `ClaudePolicyEmitter`

## Checklist Mapping
- Plan milestone 5 / AC-1: implemented Claude target-scoped `settings.json`, `effective_policy.json`, and `capability_report.json` emission under `provider_policy/<step-key>/claude/`.
- Plan milestone 5 / AC-1: Claude emission now writes lossy capability warnings even for default workspace-write fallback when native filesystem enforcement is unavailable.
- Plan milestone 5 / AC-2: wired emitted Claude policy artifacts into async and sync transport execution, runtime events, isolated launch state, and stable provider metadata paths.
- Plan milestone 5 / regression sweep: added coverage for isolated Claude launch env/cwd, legacy `permission_strategy=bypass` compatibility mapping, metadata path stability, and CLI capability gating; updated architecture config example with `provider_policy`.

## Assumptions
- Claude policy-backed turns can safely launch from a run-owned directory when they add the actual workspace via `--add-dir`; this preserves workspace access without re-loading workspace `.claude/settings*.json`.
- Enabling `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` is the compatibility bridge for project `CLAUDE.md` and rules while still isolating Claude settings under a run-owned `CLAUDE_CONFIG_DIR`.

## Preserved Invariants
- Claude transport still rejects cross-provider resume.
- Legacy no-policy Claude turns keep the previous prompt/output-format/model ordering.
- Runtime policy files remain run-scoped and no user-level Claude settings file is mutated.
- Runtime events and provider metadata still exclude env values and only expose policy fingerprints and artifact paths.
- Explicit authored `provider_policy` fields still beat legacy Claude compatibility mapping; legacy inputs only fill the default policy when those newer fields were not set.

## Intended Behavior Changes
- Policy-backed Claude turns now emit run-scoped settings and capability reports, launch from a run-owned Claude config/cwd, and reach the real workspace through `--add-dir`.
- Legacy `provider.claude.permission_strategy=bypass` now maps into the resolved default provider policy as `full_auto_unsandboxed` plus `danger_full_access` when no newer policy field already overrides it.
- Claude help-surface validation now requires both `--settings` and `--add-dir` support.
- Claude capability reports mark lossy filesystem fallback whenever sandboxed filesystem enforcement is expected but native filesystem settings are unavailable, including the default workspace-write case.

## Known Non-Changes
- No MCP, hooks, subagents, plugins, or enterprise emitters were added.
- No broader trace-writer refactor was needed; existing runtime event plumbing was reused.
- No attempt was made to let legacy Claude `bypass` override an explicit authored/runtime `provider_policy` field or a strict policy rejection.

## Expected Side Effects
- Policy-backed Claude runs will add `provider_policy_emitted` and `provider_policy_capability_report` events alongside the existing resolved-policy events.
- Older Claude CLI builds without `--settings` or `--add-dir` will now fail capability verification instead of running without isolated policy emission.
- Policy-backed Claude settings now contain workspace-rooted filesystem paths because the isolated launch cwd is no longer the workspace root.

## Validation Performed
- `.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/runtime/test_runtime_providers.py tests/runtime/test_provider_backends.py -q`
- `.venv/bin/python -m pytest tests/runtime/test_provider_policy_steps.py tests/runtime/test_provider_policy_config.py -q`
- `python3 -m compileall autoloop/runtime/providers/claude.py autoloop/runtime/providers/claude_policy.py`
- `.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/runtime/test_runtime_providers.py tests/runtime/test_provider_policy_config.py tests/runtime/test_provider_backends.py -q`
- `.venv/bin/python -m pytest tests/runtime/test_provider_policy_steps.py -q`
- `python3 -m compileall autoloop/runtime/providers/claude.py autoloop/runtime/providers/claude_policy.py autoloop/runtime/config.py autoloop/core/providers/rendering.py autoloop/core/providers/turns.py autoloop/runtime/providers/_common.py`

## Deduplication / Centralization
- Legacy Claude `permission_strategy=bypass` compatibility is now mirrored once during runtime policy resolution instead of being conditionally reintroduced in the transport.
- Claude launch isolation lives in the provider transport plus emitter seam; workflow logic and policy resolution stay unaware of Claude-specific cwd/env mechanics.
