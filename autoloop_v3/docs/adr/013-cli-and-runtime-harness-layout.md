# ADR 013: CLI And Runtime Harness Layout

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `11. Runtime Harness Design`, `12. Configuration Boundary`, `14. Workflow Extension Seam`, `15. Git Extension Placement`, and `16. Session-Path Strategy Placement`

Final decision:
- The generic CLI and runtime harness expose only workflow-agnostic controls plus provider wiring.
- The runner binds workflow-declared extensions through `Workflow.extensions`.
- Generic configuration stays small and typed, covering runtime/provider policy such as `max_steps`, `intent_mode`, provider settings, and extension config.
- Git tracking, tracing, and session-path strategy remain explicit opt-in modules rather than runtime-core policy.

Rejected shape:
- no phase-aware runtime CLI
- no workflow-specific policy hidden in generic config
- no runtime-owned git enablement or hardcoded session naming rules
