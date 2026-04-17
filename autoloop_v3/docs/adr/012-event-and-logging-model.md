# ADR 012: Event And Logging Model

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `14. Observability / Event Model`

Final decision:
- The generic runtime owns append-only `events.jsonl`.
- Workflow-owned helpers may add raw logs, ledgers, or other policy-specific files beside the generic event stream.
- Event status values remain readable by legacy operational helpers where parity requires that.
- The engine stays unaware of raw-log filenames and workflow-specific event taxonomies.

Rejected shape:
- no workflow-specific log files in the generic runtime core
- no engine-owned filesystem logging policy
- no per-workflow event schema for the shared runtime log
