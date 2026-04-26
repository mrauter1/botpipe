# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: implement
- Phase ID: runtime-cli-transports
- Phase Directory Key: runtime-cli-transports
- Phase Title: Runtime CLI Transports
- Scope: phase-local producer artifact

## Files changed
- `runtime/providers/codex.py`
- `runtime/providers/claude.py`
- `runtime/provider_backends.py`
- `runtime/providers/__init__.py`
- `tests/runtime/test_runtime_providers.py`
- `tests/runtime/test_provider_backends.py`
- `.autoloop/tasks/recursive-framework-evolution-20260425t234529-bootstrap-bootstrap/decisions.txt`

## Symbols touched
- `CodexTransport`
- `ClaudeTransport`
- `build_codex_transport`
- `build_claude_transport`
- `resolve_provider_backend`

## Checklist mapping
- Runtime CLI transports: completed
- Backend resolver wrapper update: completed
- Transport purity tests: completed
- Renderer/retry/handoff work: deferred by phase contract

## Preserved invariants
- CLI providers still own capability probing, subprocess execution, session resume, CLI envelope parsing, and transport errors.
- Core `RenderedLLMProvider` remains the owner of semantic request handling and outcome JSON parsing.
- Provider selection semantics and config keys did not change.

## Intended behavior changes
- Built-in backend resolution now returns `RenderedLLMProvider(transport)` instead of concrete semantic runtime providers.
- Runtime provider modules no longer import semantic provider request/response types or core parsing/rendering helpers.

## Known non-changes
- `ScriptedLLMProvider` and other semantic providers were untouched.
- `runtime/providers/_common.py` still contains the old verifier packet helper but no runtime transport imports or uses it.

## Validation performed
- `.venv/bin/pytest -q tests/runtime/test_runtime_providers.py tests/runtime/test_provider_backends.py tests/unit/test_provider_boundary_core.py`
- Result: `60 passed`
