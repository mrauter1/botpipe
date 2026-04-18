# ADR 009: Handler Dispatch And Signature Adaptation

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: strict handler contracts in the final workflow surface

Final decision:
- `on_start(self, ctx)` is the lifecycle hook.
- `on_outcome(state, outcome) -> Event | None` is the middleware hook.
- Pair and LLM handlers use `(state, outcome, artifacts)` and remain optional.
- System handlers use `(state, ctx)` and are required.

Rejected shape:
- no handler arity adaptation
- no alias middleware path
- no hidden dispatch rules beyond the canonical contracts
