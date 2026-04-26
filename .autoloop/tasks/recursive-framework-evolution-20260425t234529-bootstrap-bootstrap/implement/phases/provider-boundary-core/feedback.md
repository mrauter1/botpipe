# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: implement
- Phase ID: provider-boundary-core
- Phase Directory Key: provider-boundary-core
- Phase Title: Core Provider Boundary
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — `runtime/providers/codex.py::CodexProvider.run_verifier`, `runtime/providers/codex.py::CodexProvider.run_llm`, `runtime/providers/claude.py::ClaudeProvider.run_verifier`, and `runtime/providers/claude.py::ClaudeProvider.run_llm` still parse assistant text into `OutcomeResponse` inside the runtime provider layer. The parser function moved to `core/providers/parsing.py`, but AC-3 is stricter: verifier/LLM outcome parsing must belong to the new core boundary, not to runtime transport code. As implemented, the runtime side is still semantically aware of workflow outcome JSON, so the rendered-provider boundary is not actually established. Minimal fix: move verifier/LLM parsing responsibility behind `RenderedLLMProvider` and stop the runtime providers from calling `parse_outcome_json(...)` directly, even if the runtime transport refactor remains otherwise incremental.
- IMP-002 `non-blocking` — `core/providers/rendering.py::render_provider_turn` defines `ProviderPromptRenderPolicy`, but the renderer hardcodes a fresh default policy internally and gives callers no way to supply one. That leaves the requested render-policy surface inert and guarantees a follow-up API change before prompt budgets can be enforced by the engine. Minimal fix: accept `policy: ProviderPromptRenderPolicy | None = None` on `render_provider_turn(...)` or expose a sibling helper that applies a caller-provided policy so the new policy type is immediately usable.

Re-review cycle 2: IMP-001 is resolved. Verifier/LLM parsing now occurs in `core/providers/rendered.py::RenderedLLMProvider`, and the runtime provider methods no longer call `parse_outcome_json(...)`.
Re-review cycle 2: IMP-002 is resolved. `core/providers/rendering.py` now exposes `render_provider_turn_with_policy(...)`, making `ProviderPromptRenderPolicy` caller-addressable without another interface change.
Re-review cycle 2: no remaining findings for the `provider-boundary-core` phase slice.
