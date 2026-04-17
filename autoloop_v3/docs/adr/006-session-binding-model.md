# ADR 006: Session Binding Model

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `5. Session Model`

Final decision:
- Sessions are declared as slots and opened explicitly with `ctx.open_session(...)`.
- The engine performs direct lookup with `ctx.get_session(...)` during step execution.
- Rebinding is visible from workflow topology and session-opening moments.
- Using an unopened slot is a runtime error that names the missing slot and step.

Rejected shape:
- no computed session identity from workflow state
- no lifecycle enum or automatic opening policy
- no hidden session-sharing rules
