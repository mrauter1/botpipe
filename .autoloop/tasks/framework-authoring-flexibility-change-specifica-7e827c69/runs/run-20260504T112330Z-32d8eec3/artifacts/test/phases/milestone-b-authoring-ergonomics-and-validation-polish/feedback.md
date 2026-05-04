# Test Author ↔ Test Auditor Feedback

- Task ID: framework-authoring-flexibility-change-specifica-7e827c69
- Pair: test
- Phase ID: milestone-b-authoring-ergonomics-and-validation-polish
- Phase Directory Key: milestone-b-authoring-ergonomics-and-validation-polish
- Phase Title: Milestone B Authoring Ergonomics
- Scope: phase-local authoritative verifier artifact

- Added coverage for the new no-arg/current-worklist effect helpers, direct `WorklistEffect` returns from both python-step handlers and route `on_taken` hooks, updated prompt/runtime diagnostic expectations, and ownership-ambiguity failures for distinct workflow-level vs produced artifacts.
- Added explicit operation-path prompt coverage by invoking `llm(...)` from a scoped hook, so the duplicated runtime placeholder diagnostics in `autoloop/core/operations.py` are asserted separately from `PromptStep` prompt rendering.
- Addressed `TST-001` by adding a scoped-hook `llm(...)` regression test that reaches `autoloop/core/operations.py` and asserts the same step/worklist-aware placeholder failure wording as the `PromptStep` path.

- TST-001 `blocking` — `autoloop/core/operations.py` was changed to add the same step-aware prompt-placeholder labeling as `autoloop/core/engine.py`, but the new tests only exercise `PromptStep`/engine prompt rendering. There is still no operation-path coverage for `llm()` / `classify()` prompt rendering with late-bound `item`/`worklist` placeholders, so a regression in the duplicated `OperationRuntime` prompt path would pass unnoticed. Add a deterministic scoped operation test that triggers the updated runtime error text through the operation path and asserts the same step/worklist-aware diagnostics.

- TST-001 resolved — the added `test_operation_prompt_runtime_reports_missing_payload_path_with_placeholder_context` now exercises prompt rendering through the engine-bound `OperationRuntime` path in `autoloop/core/operations.py`. No additional audit findings.
