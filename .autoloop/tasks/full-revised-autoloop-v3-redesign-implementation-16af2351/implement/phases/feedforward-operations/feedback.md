# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: implement
- Phase ID: feedforward-operations
- Phase Directory Key: feedforward-operations
- Phase Title: Feedforward operations
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` `core/operations.py:_resolve_prompt`, `autoloop/simple.py` direct `llm(...)` / `classify(...)` surface: plain string prompts are treated as registry references instead of inline prompts. The canonical API required by this phase is `llm("Generate a title", ...)` / `classify("Classify risk.", ...)`, but `_resolve_prompt()` returns `ResolvedPrompt(path=<raw string>, text=None, source="registry")` for bare strings. With the real rendered provider path, `_require_prompt_text()` then raises `prompt ... did not resolve to text` before any provider call. This also breaks helper-function usage inside `python_step` when authors call `llm("...")` or `classify("...")` with the intended shorthand. Minimal fix: centralize prompt normalization for feedforward operations so bare strings become `Prompt.inline(...)` at the shared operation API boundary used by both direct calls and generated `.step(...)` handlers, and add a rendered-provider regression test that executes direct/helper string prompts through `RenderedLLMProvider`.
