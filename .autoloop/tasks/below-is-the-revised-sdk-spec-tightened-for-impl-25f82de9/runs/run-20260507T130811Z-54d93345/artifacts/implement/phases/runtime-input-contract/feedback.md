# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: implement
- Phase ID: runtime-input-contract
- Phase Directory Key: runtime-input-contract
- Phase Title: Refactor Runtime Input Contract
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [autoloop/core/context.py:350](../../../../../../../../autoloop/core/context.py)
  `Context.input` now constructs `WorkflowInputView(message=self.message, ...)`, which eagerly resolves `self.message` on every `ctx.input` access. That is a compatibility regression for any direct `Context(...)` caller that provides typed `workflow_input` but has no `request.md`: previously `ctx.input.topic` still worked because `ctx.input` was the raw model, but now `ctx.input` first tries to read the missing request snapshot and raises `WorkflowExecutionError`. This contradicts the phase goal of separating message from typed input, because typed-input access is still implicitly coupled to request snapshot availability. Minimal fix: make message fallback lazy inside the composite view itself so `ctx.input.topic` can read raw typed fields without touching `ctx.message` or `request.md`; centralize that laziness in `WorkflowInputView` / `Context.input` rather than adding per-callsite guards.

Re-review note: IMP-001 is resolved in cycle 2. `WorkflowInputView` now keeps omitted-message fallback lazy, and the new direct-`Context(...)` regression test covers typed-input access without a request snapshot.
