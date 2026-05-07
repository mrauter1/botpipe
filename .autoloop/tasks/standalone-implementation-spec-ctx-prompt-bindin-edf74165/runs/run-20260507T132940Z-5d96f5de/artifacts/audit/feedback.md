# Intent Audit <-> Intent Audit Verifier Feedback

## Findings

- AUD-001: The runtime implementation is aligned with the requested contract, but the final codebase still contains a stale contract test at `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_without_typed_input` that expects undeclared `{ctx.input.message}` to resolve request text. Running the focused contract subset reproduces this as the only failure (`1 failed, 4 passed`).
