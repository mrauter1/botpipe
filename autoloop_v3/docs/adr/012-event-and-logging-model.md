# ADR 012: Event And Logging Model

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `17. Observability And Event Model`

Final decision:
- The generic runtime always writes append-only `events.jsonl`.
- Workflow-owned parity code may write raw logs, ledgers, or other domain-specific artifacts beside the generic event stream.
- Optional tracing belongs in the extension layer and does not replace the generic runtime log.
- Shared runtime events remain generic and workflow-agnostic.

Rejected shape:
- no workflow-specific event schema in the generic runtime log
- no tracing-first replacement for `events.jsonl`
- no engine-owned raw-log policy
