# Risk Register

| Risk | Why it matters | Control in the v3 design |
| --- | --- | --- |
| Loader cannot import `Ralph_loop.py` as-is | Missing annotation imports can fail before compatibility normalization runs | `runtime.loader` provides a legacy-safe namespace and postponed annotation handling |
| Compatibility rules leak into the core engine | The engine would become harder to reason about and harder to test | All drift is normalized in `workflow.compat` before compilation |
| Resume behavior diverges from legacy runs | Resume spans events, sessions, clarifications, and phase scope | Snapshot checkpoints plus append-only events, with explicit resume tests |
| Session scope collisions across phases | Implement and test must share the active phase session but isolate different phases | Scoped session bindings keyed by slot plus scope in the session store |
| Artifact path regressions | Existing workflows rely on phase-local paths and produced-artifact attribute access | Compiled artifact registry plus resolver tests for dot notation, missing keys, and phase scopes |
| Decisions ledger sequence drift | Existing tools treat the ledger as an authoritative history | Centralized runtime logging writer with dedicated sequence tests |
| CLI or config narrowing | Operators depend on current `autoloop` discovery and override behavior | Separate `runtime.config` and `runtime.cli` modules with precedence and smoke coverage |
| Generic runner is used against legacy event-only resume state | Operators may try to resume old runs without a v3 checkpoint | Raise an explicit checkpoint migration error and document the fallback to the legacy runtime |
| Generic runner is expected to emulate legacy pair or phase loop controls | Operators may assume old pair or phase orchestration still lives in the generic v3 CLI | Reject non-default compatibility flags early and document the boundary in the runtime docs |
| Provider-specific loop-control behavior breaks parity | Old runtime wraps provider execution and interprets loop-control output | Keep provider wire behavior in the injected provider factory or legacy runtime, outside the engine core |
| Pydantic v1 or v2 differences change handler behavior | Legacy workflows use `copy(update=...)` while new code should use `model_copy(update=...)` | Compatibility adapters tolerate legacy usage, strict docs require v3 semantics |
