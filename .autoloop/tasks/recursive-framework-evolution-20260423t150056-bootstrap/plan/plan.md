# Built-in Runtime Providers Plan

## Scope

Implement concrete runtime-backed `codex` and `claude` adapters under `runtime/providers/` and wire them through `runtime/provider_backends.py` without changing the core provider protocol, workflow engine contracts, or filesystem session schema.

## Hard Invariants

- Keep `core/providers/*` unchanged as the strict provider protocol and fake/test surface unless a blocker is found.
- Keep `SessionBinding.session_id` as the only canonical continuation handle across the runtime and store payloads.
- Do not add or persist framework-owned `thread_id` fields anywhere; Codex may use a local parse variable only.
- Keep provider-specific state under `SessionBinding.metadata["provider_metadata"]`.
- Keep public provider selection on the typed runtime config and CLI surface: `--provider`, `--model`, `--model-effort`.
- Keep `provider_factory` as a non-public injection seam only; continue rejecting `module:function` provider names.
- Do not add Anthropic/OpenAI API providers, packet abstractions, or per-invocation CLI help probing.

## Implementation Milestones

### 1. Shared runtime provider foundation

- Create `runtime/providers/__init__.py` plus `runtime/providers/_common.py`.
- Define shared helpers for prompt presence checks, subprocess stream formatting, cross-provider resume rejection, strict local outcome parsing, verifier input rendering, and canonical session binding construction.
- Replace placeholder backend builders in `runtime/provider_backends.py` with built-in builder dispatch to `build_codex_provider` and `build_claude_provider`.

### 2. Codex CLI adapter

- Add `runtime/providers/codex.py` with:
  - `CodexCLICommand`
  - `verify_codex_exec_capabilities()`
  - cached `resolve_codex_cli_commands(config)`
  - `parse_codex_exec_json(raw_stdout)`
  - `CodexProvider`
  - `build_codex_provider(config)`
- Use the request snapshot and `provider_implementation.md` as the command-surface baseline for `codex exec`, `resume`, JSONL parsing, continuation extraction, and bypass/full-auto fallback.
- Ensure producer returns parsed assistant text, while verifier/LLM turns locally validate strict JSON outcomes.

### 3. Claude Code adapter, tests, and docs

- Add `runtime/providers/claude.py` with:
  - `verify_claude_code_capabilities()`
  - `claude_permission_args(config.provider.claude)`
  - `parse_claude_exec_json(raw_stdout)`
  - `ClaudeProvider`
  - `build_claude_provider(config)`
- Map permission strategies exactly to `inherit`, `allow_core_tools`, and `bypass`, with precise `ConfigError` failures for unsupported surfaces.
- Update `tests/runtime/test_provider_backends.py` for backend resolution coverage and add one focused runtime provider test module for adapter/helper behavior if needed.
- Update `docs/architecture.md` and `docs/authoring.md` to describe the new runtime provider package, typed provider selection, strict JSON verifier/LLM outcomes, `session_id` resumability, and the absence of `thread_id` and public provider factories.

## Planned File Ownership

- `runtime/provider_backends.py`
  - Replace placeholder builders with real built-in provider dispatch.
- `runtime/providers/__init__.py`
  - Export the runtime provider builders/helpers needed by the runtime package.
- `runtime/providers/_common.py`
  - Shared provider-side utilities only; no engine or store redesign.
- `runtime/providers/codex.py`
  - Codex CLI capability checks, cached command resolution, JSONL parsing, turn execution, and response/session translation.
- `runtime/providers/claude.py`
  - Claude CLI capability checks, permission mapping, JSON parsing, turn execution, and response/session translation.
- `tests/runtime/test_provider_backends.py`
  - Backend dispatch and backend-related configuration failures.
- `tests/runtime/test_runtime_providers.py` if added
  - Codex adapter, Claude adapter, shared parser, and capability verifier coverage.
- `docs/architecture.md`
  - Runtime provider placement, backend selection, session semantics, strict verifier/LLM JSON outcomes.
- `docs/authoring.md`
  - Operator-facing provider selection and author guidance around opaque session handling.

## Interface Contract Notes

- Shared helpers should accept existing runtime/core types directly:
  - `require_prompt_text(ResolvedPrompt, provider_name, step_name) -> str`
  - `format_subprocess_streams(stdout, stderr) -> str`
  - `ensure_session_provider_match(provider_name, SessionBinding | None) -> None`
  - `parse_outcome_json(raw_text) -> Outcome`
  - `render_verifier_input(verifier_prompt_text, producer_raw_output) -> str`
  - `build_session_binding(...) -> SessionBinding`
- `build_session_binding(...)` must preserve `ref_name` and `scope`, set the resolved `session_id`, and produce metadata shaped as:
  - `provider`
  - `mode`
  - `provider_metadata`
  - `model_override`
  - `effort_override`
- `run_producer()` returns `ProducerResponse(raw_output=<provider text>, session=<binding>, metadata=<debug/provider metadata>)`.
- `run_verifier()` and `run_llm()` must convert parsed provider text into typed `OutcomeResponse`.

## Regression Prevention

- Preserve engine assumptions that pair-step producer output is raw text and verifier/LLM output is a typed `Outcome`.
- Preserve existing filesystem session payload semantics by adapting providers to the current metadata shape instead of changing the store.
- Enforce same-provider resume only; resuming a `codex` session with `claude` or vice versa must raise `ProviderExecutionError`.
- Reject missing prompt text early so CLI providers never execute unresolved prompt placeholders.
- Keep CLI capability probing isolated to explicit verifier helpers and cached command resolution; no turn-time help probes.
- Ensure metadata returned from providers never exposes `thread_id` even when Codex output contains one.

## Validation Plan

- Backend resolution tests:
  - real provider class resolution when capability verification is monkeypatched successful
  - module:function rejection
  - missing binary and unsupported capability errors with precise `ConfigError` text
  - configured Codex `model_effort` without CLI support
  - configured Claude `effort` without CLI support
- Codex adapter tests:
  - successful help probing, start/resume command construction, JSONL parsing, producer/verifier/LLM turns
  - malformed JSONL, missing assistant text, non-zero subprocess exit, provider mismatch on resume
  - canonical `session_id` persistence and no `thread_id` leakage
- Claude adapter tests:
  - valid JSON stdout, verifier/LLM strict JSON outcome parsing, resume behavior
  - malformed JSON, missing `result`, non-zero exit, provider mismatch on resume
  - permission strategy handling and provider metadata preservation
- Shared helper tests:
  - plain JSON object and fenced JSON block outcomes
  - invalid JSON, missing `tag`, non-dict `payload`, default payload behavior, raw output preservation
- Documentation review:
  - docs mention built-in runtime providers under `runtime/providers/`
  - docs keep typed provider selection and `session_id` resumability as the public contract

## Compatibility Notes

- This task intentionally removes the placeholder “unimplemented adapter” behavior in favor of built-in runtime adapters, but it does not widen the public provider loading surface.
- Existing runtime config semantics remain typed and provider-agnostic; generic `provider.model` and `provider.model_effort` still target the selected provider.
- No migration of persisted session files should be required because the metadata shape already supports `provider`, `provider_metadata`, `model_override`, `effort_override`, and `session_id`.

## Risk Register

- CLI surface drift:
  - Risk: installed Codex or Claude CLI differs from the expected flags.
  - Control: isolate verification helpers, cache Codex command surface resolution, and fail with precise `ConfigError` messages covered by tests.
- Cross-provider resume corruption:
  - Risk: a stored session is resumed with the wrong provider and produces invalid continuation behavior.
  - Control: centralize provider-match checks in `_common.py` and cover both adapters with provider mismatch tests.
- Outcome parsing fragility:
  - Risk: verifier/LLM turns accept prose or malformed JSON and violate engine contracts.
  - Control: use a strict local parser that only accepts a plain JSON object or a single fenced top-level `json` block.
- Codex continuation leakage:
  - Risk: internal `thread_id` leaks into framework-owned state or docs.
  - Control: translate any parsed continuation immediately to canonical `session_id` and assert the exposed metadata excludes `thread_id`.

## Rollback

- If a provider-specific implementation proves unstable, revert only the new runtime provider package and backend dispatch changes, restoring placeholder backend builders while leaving core protocol, config, and session-store contracts intact.
