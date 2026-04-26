# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: implement
- Phase ID: runtime-cli-transports
- Phase Directory Key: runtime-cli-transports
- Phase Title: Runtime CLI Transports
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [runtime/providers/__init__.py], [runtime/providers/codex.py], [runtime/providers/claude.py]: the phase removes the previously exported `CodexProvider` / `ClaudeProvider` classes and `build_codex_provider` / `build_claude_provider` symbols entirely. That is an avoidable compatibility regression: any adjacent or external code importing `autoloop_v3.runtime.providers.CodexProvider`, `autoloop_v3.runtime.providers.ClaudeProvider`, or the old builder names now fails at import time even though the accepted plan only required backend resolution to wrap transports, not removal of the existing import surface. Minimal fix: restore compatibility shims for the old names outside the pure transport implementations, for example in `runtime/providers/__init__.py` or a dedicated compatibility module, so backend resolution stays on `RenderedLLMProvider(transport)` while the prior imports continue to resolve.
