# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: implement
- Phase ID: contract-test-alignment
- Phase Directory Key: contract-test-alignment
- Phase Title: Align Remaining ctx.input.message Contract Test
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` [autoloop/core/artifacts.py:239](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/artifacts.py:239), [autoloop/core/artifacts.py:590](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/artifacts.py:590): the current resolver still routes `ctx.input.*` through `Context.input` and still exempts `ctx.input.message` from the no-input guard. On the current tree, reviewer rerun of the focused slice fails 4 tests: undeclared `{ctx.input.message}` does not raise, and declared `{ctx.input.message}` still resolves request text instead of the typed `Input.message`. This misses AC-1, AC-2, and the decision ledger entry that `ctx.*` must stop treating `ctx.input.message` as a request-text alias. Minimal fix: make `ctx.*` resolution read `context.input_fields` rather than the compatibility view, and remove the `field_name != "message"` special-case so the no-input guard applies uniformly while bare `{input.message}` remains on `_resolve_input_placeholder`.
