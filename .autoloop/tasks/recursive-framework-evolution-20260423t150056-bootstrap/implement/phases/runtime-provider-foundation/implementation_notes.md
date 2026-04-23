# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t150056-bootstrap
- Pair: implement
- Phase ID: runtime-provider-foundation
- Phase Directory Key: runtime-provider-foundation
- Phase Title: Shared Provider Foundation
- Scope: phase-local producer artifact

## Files changed

- `runtime/provider_backends.py`
- `runtime/providers/__init__.py`
- `runtime/providers/_common.py`
- `runtime/providers/codex.py`
- `runtime/providers/claude.py`
- `tests/runtime/test_provider_backends.py`
- `tests/runtime/test_runtime_providers.py`
- `docs/architecture.md`
- `docs/authoring.md`
- `.autoloop/tasks/recursive-framework-evolution-20260423t150056-bootstrap/decisions.txt`

## Symbols touched

- `resolve_provider_backend`
- `build_codex_provider`, `CodexProvider`, `CodexCLICommand`
- `verify_codex_exec_capabilities`, `resolve_codex_cli_commands`, `parse_codex_exec_json`
- `build_claude_provider`, `ClaudeProvider`
- `verify_claude_code_capabilities`, `claude_permission_args`, `parse_claude_exec_json`
- `require_prompt_text`, `format_subprocess_streams`, `ensure_session_provider_match`
- `parse_outcome_json`, `render_verifier_input`, `build_session_binding`

## Checklist mapping

- Milestone 1: completed via `runtime/providers/__init__.py`, `runtime/providers/_common.py`, and backend dispatch rewiring in `runtime/provider_backends.py`.
- Milestone 2: completed via `runtime/providers/codex.py` plus Codex backend and parser tests.
- Milestone 3: completed via `runtime/providers/claude.py`, `tests/runtime/test_provider_backends.py`, `tests/runtime/test_runtime_providers.py`, `docs/architecture.md`, and `docs/authoring.md`.

## Assumptions

- `provider_implementation.md` remains the authoritative local command-surface baseline because no separate uploaded helper implementation exists in the repository.
- Freshly opened session slots can still carry synthetic local placeholder `session_id` values before a provider writes canonical metadata, so resumability must key off matching provider metadata rather than raw `session_id` presence alone.

## Preserved invariants

- `core/providers/*` protocol and request/response dataclasses unchanged.
- Framework-owned session persistence schema unchanged: canonical `session_id`, `provider_metadata`, `model_override`, `effort_override`.
- Runtime backend selection remains framework-owned and still rejects `module:function` provider names.
- Provider-specific continuation details stay localized to `runtime/providers/*`.

## Intended behavior changes

- Built-in `codex` and `claude` runtime adapters now resolve through `runtime/provider_backends.py` instead of placeholder “unimplemented adapter” errors.
- Verifier and single-LLM turns now require strict locally validated JSON outcomes for both built-in CLI adapters.
- Cross-provider resume attempts now fail explicitly with `ProviderExecutionError`.
- Claude capability validation now requires permission flags only for the configured `provider.claude.permission_strategy`, so the default `inherit` path no longer rejects otherwise valid headless CLI installations for unused optional flags.

## Known non-changes

- No core engine, workflow protocol, or filesystem session schema redesign.
- No API/SDK-backed Anthropic or OpenAI provider implementation.
- No public provider factory/module loader surface added.

## Expected side effects

- Backend resolution now probes CLI capabilities once per process and caches the discovered help surface.
- Codex/Claude provider builds fail early with precise `ConfigError` messages when required binaries or flags are unavailable.
- Claude backend resolution now distinguishes always-used headless flags from optional permission-strategy flags, preserving compatibility for default `inherit` installs while still failing fast for unsupported `allow_core_tools` / `bypass` selections.
- Provider response metadata surfaces only mode plus provider metadata; raw subprocess streams remain error-only surfaces.

## Validation performed

- `.venv/bin/python -m pytest tests/runtime/test_provider_backends.py tests/runtime/test_runtime_providers.py -q`
- `.venv/bin/python -m pytest tests/runtime/test_provider_backends.py tests/runtime/test_runtime_providers.py tests/runtime/test_compatibility_runtime.py tests/test_architecture_baseline_docs.py -k 'not test_recursive_memory_files_record_cycle_one_closeout_baseline' -q` after fixing reviewer finding `IMP-001`
- `.venv/bin/python -m pytest tests/runtime/test_package_cli.py -q` (fails in unrelated pre-existing recursive package CLI/template assertions outside this phase scope)

## Deduplication / centralization decisions

- Shared prompt validation, subprocess formatting, outcome parsing, verifier-input rendering, and session-binding construction were centralized in `runtime/providers/_common.py`.
- CLI capability probing is cached per process inside provider modules so turn execution does not re-run help probes.
