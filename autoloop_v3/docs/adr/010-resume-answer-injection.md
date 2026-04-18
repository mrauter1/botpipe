# ADR 010: Resume Answer Injection

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: pause/resume behavior in the strict checkpoint model

Final decision:
- Clarification questions are captured in structured checkpoint state when execution pauses.
- Resume answers are injected exactly once when the paused step resumes.
- The generic runtime does not keep a hidden ambient answer channel across later steps.
- Workflow-owned parity code may persist extra clarification artifacts without redefining engine semantics.

Rejected shape:
- no answer recovery from raw-log parsing
- no hidden long-lived runtime answer global
- no workflow-specific clarification persistence inside the generic engine
