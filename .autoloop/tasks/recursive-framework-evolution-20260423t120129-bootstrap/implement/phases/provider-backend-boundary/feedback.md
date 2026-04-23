# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: implement
- Phase ID: provider-backend-boundary
- Phase Directory Key: provider-backend-boundary
- Phase Title: Add Built-In Provider Backend Resolver
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | [runtime/cli.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/cli.py:52), [runtime/cli.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/cli.py:428), [tests/runtime/test_provider_backends.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_provider_backends.py:97)
  The CLI still advertises and accepts `--provider-factory`, but `_resolve_provider(...)` now ignores `args.provider_factory` and always routes the normal path to `resolve_provider_backend(...)`. A user running `autoloop run ... --provider-factory provider_backend:build` will no longer get the requested factory-backed provider; instead they will hit the built-in backend error path. That is a silent public behavior regression and leaves the help text lying about a still-parsed flag. The new test at `test_cli_resolve_provider_uses_builtin_backend_resolver_when_not_injected` locks in that incorrect behavior.
  Minimal fix: until the later CLI cleanup phase removes the public flag/help surface, either keep the parsed `--provider-factory` path wired through the old loader or, preferably, reject the parsed flag immediately with a precise `ConfigError` and add a user-facing CLI test for that rejection path. Do not silently ignore a still-documented public flag.
