# ADR 013: CLI And Runtime Harness Layout

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `11. Runtime Harness Design`, `12. Configuration Design`, and `13. Git Policy Placement`

Final decision:
- The generic CLI and runtime harness expose only workflow-agnostic controls and provider wiring.
- Generic configuration is intentionally small: provider selection/settings plus runtime controls such as `max_steps` and `intent_mode`.
- The runtime owns task/run directories, request snapshots, events, checkpoints, prompt lookup, and generic session persistence.
- Workflow-specific operational policy, including any Autoloop-v1 parity behavior, lives in workflow-owned helpers.

Rejected shape:
- no phase-aware runtime CLI
- no workflow-specific policy hidden in generic config flags
- no git or artifact-tracking policy embedded in the generic runtime core
