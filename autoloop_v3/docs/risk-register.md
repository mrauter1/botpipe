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
| Provider-specific loop-control behavior breaks parity | Old runtime wraps provider execution and interprets loop-control output | Keep provider wire behavior in `runtime.providers`, outside the engine core |
| Pydantic v1 or v2 differences change handler behavior | Legacy workflows use `copy(update=...)` while new code should use `model_copy(update=...)` | Compatibility adapters tolerate legacy usage, strict docs require v3 semantics |
