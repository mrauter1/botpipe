# ADR 006: Session Binding Model

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `5. Session Model`

Final decision:
- Sessions are declared as slots and opened explicitly with `ctx.open_session(...)`.
- Session sharing and rebinding are visible in workflow code.
- The engine performs direct lookup only and fails clearly if a required session was never opened.
- Exact workflow-specific filename conventions remain outside the generic session model.

Rejected shape:
- no computed session identity
- no lifecycle enum or automatic opening
- no hidden sharing rules
