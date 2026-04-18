# ADR 005: Checkpoint Persistence Model

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `9. Checkpoint Model`

Final decision:
- Checkpoints are typed structured snapshots and the canonical resume source.
- `events.jsonl` remains operational history, not the sole source of resume state.
- Pause and resume preserve pending question and answer data through checkpoint state.
- Generic runtime recovery requires a checkpoint instead of reconstructing state from partial artifacts.

Rejected shape:
- no event-log-only resume model
- no provider-owned opaque resume blob as the primary contract
- no implicit recovery from sessions or logs alone
