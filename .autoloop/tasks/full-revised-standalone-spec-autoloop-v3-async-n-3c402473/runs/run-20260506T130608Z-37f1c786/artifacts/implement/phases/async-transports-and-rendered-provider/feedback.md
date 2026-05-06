# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: implement
- Phase ID: async-transports-and-rendered-provider
- Phase Directory Key: async-transports-and-rendered-provider
- Phase Title: Async transports and rendered provider
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` [autoloop/runtime/providers/_common.py:183](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/providers/_common.py:183): `terminate_text_subprocess(...)` calls `process.terminate()` and, on timeout, `process.kill()` without guarding `ProcessLookupError`. That creates a race during cancellation: if the provider subprocess exits between the `returncode is None` check and the signal call, the cancellation path can raise `ProcessLookupError` instead of preserving the expected `CancelledError`, which violates the phase requirement that built-in CLI transports support cancellation cleanly. Minimal fix: harden the shared helper in `_common.py` by catching `ProcessLookupError` around both signal calls and then awaiting `process.wait()` when needed so Codex and Claude inherit the fix centrally.
