# Test Strategy

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: test
- Phase ID: provider-backend-boundary
- Phase Directory Key: provider-backend-boundary
- Phase Title: Add Built-In Provider Backend Resolver
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- `resolve_provider_backend(...)` dispatches built-in provider names through the framework-owned builder map.
- `resolve_provider_backend(...)` rejects `module:function` provider names instead of treating them as dynamic loaders.
- Unavailable backend failures are covered for both branches used in this phase:
  missing `claude` CLI on PATH and detected-but-unimplemented `codex` adapter.
- CLI shared resolver behavior is covered for:
  normal built-in resolver usage when no seam is injected,
  explicit rejection of parsed public `--provider-factory`,
  preserved precedence of the non-public `cli.main(..., provider_factory=...)` seam.
- User-facing CLI coverage keeps one deterministic mutating command path:
  `run` rejects parsed public `--provider-factory` with `EXIT_USAGE_ERROR`,
  `run` still succeeds through the non-public injected seam.

## Preserved invariants checked

- The built-in resolver remains the normal public CLI path.
- Parsed public provider-factory input is never silently ignored.
- The non-public injection seam remains available and wins when explicitly supplied.

## Edge cases and failure paths

- Provider names containing `:` are rejected.
- Backend unavailability is tested for both “missing executable” and “CLI present but adapter absent” cases.
- Public mutating CLI rejection is tested without depending on any real provider implementation.

## Stabilization / flake control

- Tests use only local temp dirs, monkeypatching, and deterministic stubs.
- No timing, network, ordering, or external-service dependencies were introduced.

## Known gaps

- I did not add duplicate user-facing rejection tests for `resume` and `answer`; shared `_resolve_provider(...)` unit coverage plus the `run` CLI regression test covers the common branch without redundant churn.
- `pytest` execution is still unavailable in this environment, so validation here is limited to syntax compilation.
