# Implementation Notes

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-claude-regression
- Phase Directory Key: policy-claude-regression
- Phase Title: Claude Emission And Regression Sweep
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/runtime/providers/claude.py`
- `autoloop/runtime/providers/claude_policy.py`
- `tests/runtime/test_provider_policy_emitters.py`
- `tests/runtime/test_runtime_providers.py`
- `docs/architecture.md`
- `run decisions.txt` for non-obvious phase decisions

## Symbols Touched
- `ClaudeTransport`
- `build_claude_transport()`
- `build_claude_operation_executor()`
- `_prepare_turn_command()`
- `_emit_turn_policy()`
- `_with_policy_metadata()`
- `_emit_policy_event()`
- `_validate_claude_surface()`
- `ClaudeCapabilities`
- `ClaudePolicyEmitter`

## Checklist Mapping
- Plan milestone 5 / AC-1: implemented Claude target-scoped `settings.json`, `effective_policy.json`, and `capability_report.json` emission under `provider_policy/<step-key>/claude/`.
- Plan milestone 5 / AC-2: wired emitted Claude policy artifacts into async and sync transport execution, metadata, and runtime policy events.
- Plan milestone 5 / regression sweep: added Claude emitter and transport coverage for capability-loss warnings, metadata path stability, and CLI capability gating; updated architecture config example with `provider_policy`.

## Assumptions
- Claude Code `--settings <file>` is the preferred run-scoped override seam for this patch because it preserves existing session continuity better than swapping `CLAUDE_CONFIG_DIR`.
- Legacy `provider.claude.permission_strategy=bypass` should not silently defeat the resolved provider policy or strict envelope; only additive `allow_core_tools` remains active when policy emission is present.

## Preserved Invariants
- Claude transport still rejects cross-provider resume.
- Legacy no-policy Claude turns keep the previous prompt/output-format/model ordering.
- Runtime policy files remain run-scoped and no user-level Claude settings file is mutated.
- Runtime events and provider metadata still exclude env values and only expose policy fingerprints and artifact paths.

## Intended Behavior Changes
- Policy-backed Claude turns now emit and use run-scoped settings plus capability reports before subprocess execution.
- Claude help-surface validation now requires `--settings` support.
- Claude capability reports mark lossy filesystem fallback when native sandbox filesystem support is unavailable.

## Known Non-Changes
- No MCP, hooks, subagents, plugins, or enterprise emitters were added.
- No broader trace-writer refactor was needed; existing runtime event plumbing was reused.
- No attempt was made to let legacy Claude `bypass` override a strict or resolved policy.

## Expected Side Effects
- Policy-backed Claude runs will add `provider_policy_emitted` and `provider_policy_capability_report` events alongside the existing resolved-policy events.
- Older Claude CLI builds without `--settings` will now fail capability verification instead of running without policy emission.

## Validation Performed
- `.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/runtime/test_runtime_providers.py tests/runtime/test_provider_backends.py -q`
- `.venv/bin/python -m pytest tests/runtime/test_provider_policy_steps.py tests/runtime/test_provider_policy_config.py -q`
- `python3 -m compileall autoloop/runtime/providers/claude.py autoloop/runtime/providers/claude_policy.py`

## Deduplication / Centralization
- Reused the existing Codex-side transport pattern for policy emission, metadata attachment, and runtime event naming instead of introducing a separate Claude-only runtime seam.
