# ADR 003: Topology And Routing Representation

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: strict routing semantics captured by the compiler and engine

Final decision:
- Workflows declare `entry` and `transitions` explicitly.
- Terminal destinations remain explicit through `SUCCESS`, `PAUSE`, and `FAIL`.
- Routing stays deterministic: step-local route first, then `GLOBAL`, otherwise an error.
- Workflow meaning stays in workflow code rather than config or extension behavior.

Rejected shape:
- no inferred entry behavior
- no hidden fallback routing
- no topology encoded through config or side-effectful helper layers
