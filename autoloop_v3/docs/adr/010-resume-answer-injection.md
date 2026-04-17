# ADR 010: Resume Answer Injection

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: checkpointed pause/resume behavior in the strict engine

Final decision:
- Clarification questions are captured in the checkpoint when execution pauses.
- Resume answers are injected into the resumed step exactly once through structured checkpoint state.
- The answer is not a hidden long-lived runtime global that bleeds across later steps.
- Workflow-owned harnesses may persist extra clarification artifacts when parity requires them.

Rejected shape:
- no answer recovery from raw-log parsing
- no prompt-only answer injection without structured checkpoint state
- no workflow-specific clarification persistence in the generic engine
