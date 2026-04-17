# ADR 003: Topology And Routing Representation

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: canonical routing semantics captured by the strict compiler and engine

Final decision:
- Workflows declare `transitions`; the compiler normalizes them into explicit routing tables.
- The engine resolves routes in one order only: step-local route, then `GLOBAL`, else runtime error.
- Terminal destinations remain explicit through `SUCCESS`, `PAUSE`, and `FAIL`.
- The runtime does not know workflow-domain concepts such as phases or plan/implement/test.

Rejected shape:
- no workflow-specific routing rules inside the runtime
- no hidden fallback destinations
- no topology encoded through side-effectful helper logic
