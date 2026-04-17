# ADR 005: Checkpoint Persistence Model

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `9. Checkpoint Model`

Final decision:
- Checkpoints are typed snapshots containing stage, state, session bindings, pending question, and pending answer.
- Pause, failure, and resume operate on structured checkpoint data rather than log reconstruction.
- The runtime event log remains operational history, not the sole source of resume state.
- Generic resume refuses session-only or event-only recovery when no checkpoint exists.

Rejected shape:
- no event-log-only checkpoint model
- no provider-owned opaque resume blobs
- no implicit resume from partial persisted state
