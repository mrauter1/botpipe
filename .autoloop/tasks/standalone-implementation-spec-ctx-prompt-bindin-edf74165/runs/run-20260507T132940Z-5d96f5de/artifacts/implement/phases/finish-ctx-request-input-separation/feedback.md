# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: implement
- Phase ID: finish-ctx-request-input-separation
- Phase Directory Key: finish-ctx-request-input-separation
- Phase Title: Finish Ctx Request And Input Separation
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — `autoloop/core/context.py:91`, `autoloop/core/context.py:359`, and `autoloop/core/discovery.py:1404` still preserve the built-in `ctx.input.message` alias. `WorkflowInputView.message` and `model_dump()` still synthesize request text, `Context.input` still wires `_message_value/_request` into that view, and discovery still returns success for undeclared `ctx.input.message`. In the current tree, direct Python `ctx.input.message`, `ctx.input.model_dump()`, runtime rendering, and prompt validation all continue to treat request text as built in even when `Input.message` is not declared, which violates AC-1 and AC-6. Minimal fix: make `WorkflowInputView` expose only declared input fields, remove the `ctx.input.message` allowlist branches in discovery/runtime `ctx.*` resolution, and keep any legacy bare `{input.message}` fallback isolated in `_resolve_input_placeholder`.
