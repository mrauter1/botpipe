# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: implement
- Phase ID: provider-backend-boundary
- Phase Directory Key: provider-backend-boundary
- Phase Title: Add Built-In Provider Backend Resolver
- Scope: phase-local producer artifact

## Files changed

- `runtime/provider_backends.py`
- `runtime/cli.py`
- `tests/runtime/test_provider_backends.py`
- `tests/runtime/test_package_cli.py`

## Symbols touched

- `runtime.provider_backends.resolve_provider_backend`
- `runtime.provider_backends._build_codex_backend`
- `runtime.provider_backends._build_claude_backend`
- `runtime.cli._resolve_provider`
- `tests.runtime.test_provider_backends.*`
- `tests.runtime.test_package_cli.test_cli_mutating_commands_accept_non_public_provider_factory_injection_seam`
- `tests.runtime.test_package_cli.test_cli_run_rejects_public_provider_factory_flag`

## Checklist mapping

- Plan Phase 1: completed
  Added the framework-owned provider backend resolver module.
  Switched the normal CLI path to call the resolver.
  Added resolver dispatch/failure tests, updated the surviving injection-seam test, and fixed the public flag regression called out in review.

## Assumptions

- No in-repo production provider adapters exist yet; precise `ConfigError` failures are acceptable for unavailable backends in this phase.
- The later CLI cleanup phase will remove stale parser/help/env references to public provider factories.

## Preserved invariants

- `cli.main(..., provider_factory=...)` remains the non-public direct injection seam for tests/programmatic callers.
- `runtime/runner.py` was left untouched in this phase.
- Non-mutating CLI commands still bypass provider resolution entirely.

## Intended behavior changes

- Public CLI execution no longer loads `module:function` provider factories through `runtime/cli.py`; it resolves providers through `runtime.provider_backends`.
- Until the parser/help cleanup phase removes `--provider-factory`, the parsed public flag now fails fast with a precise `ConfigError` instead of being silently ignored.
- Built-in provider names are dispatched explicitly and reject `module:function`-style names with `ConfigError`.
- The resolver now fails precisely for unavailable/unimplemented `codex` and `claude` backends instead of falling back to public factory loading.

## Known non-changes

- `--provider-factory`, help text, and env-var cleanup were not removed in this phase; the parsed flag is still present but now rejected explicitly on the public CLI path.
- No real Codex or Claude provider implementation was added yet.
- No session payload or recursive-wrapper work was performed in this phase.

## Expected side effects

- Existing tests that asserted the public `--provider-factory` execution path were updated to assert the retained non-public injection seam instead.
- Public invocations that still pass `--provider-factory` now fail with `EXIT_USAGE_ERROR` and a precise guidance message instead of falling through to backend resolution.
- Default mutating CLI execution without the public flag now surfaces backend-unavailable `ConfigError`s until a real built-in adapter is implemented.

## Validation performed

- `python3 -m py_compile runtime/provider_backends.py runtime/cli.py tests/runtime/test_provider_backends.py tests/runtime/test_package_cli.py`
- Attempted:
  `python3 -m pytest tests/runtime/test_provider_backends.py`
  `python3 -m pytest tests/runtime/test_package_cli.py`
  Failed because `pytest` is not installed in this environment.
- Attempted direct runtime smoke import via `python3`; blocked because `pydantic` is not installed in this environment.

## Deduplication / centralization

- Provider-name dispatch now lives in one place: `runtime/provider_backends.py`.
- CLI resolution delegates to that boundary instead of reimplementing factory parsing/loading inline.
