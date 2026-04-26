# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: implement
- Phase ID: engine-provider-retries
- Phase Directory Key: engine-provider-retries
- Phase Title: Engine Retry Semantics
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py): `_execute_pair_step(...)` and `_execute_llm_step(...)` reuse the active `SessionBinding` on retry by calling `_resolve_session(...)` again after a failed provider attempt, and `_run_pair_step(...)` / `_run_llm_step(...)` persist the failed attempt’s updated session before the retry loop decides whether to retry. For any session-bound step, attempt 2 therefore resumes the same provider transcript that produced the illegal route / invalid payload / malformed output on attempt 1. That contradicts the accepted retry contract and AC-3, which explicitly require rebuilding the retry request without previous transcript data. Concrete failure scenario: an `LLMStep(session=main)` returns an illegal route on attempt 1; attempt 2 sends clean retry feedback text, but the Codex/Claude transport resumes the same session and the provider still sees the rejected prior turn in transcript history. Minimal fix: centralize retry-session handling in `core/engine.py` so provider-attributable retries use a fresh dispatch session (or explicitly suppress session resume) while still preserving the step’s normal session persistence on successful completion, and add a regression test covering a session-bound llm/pair retry path.
- Review cycle 2: `IMP-001` is resolved. `core/engine.py` now captures a pre-step baseline session for llm/pair retries, keeps failed-attempt session updates attempt-local until an attempt is accepted, and persists only the accepted attempt’s resulting session. Added regression coverage in `tests/contract/test_engine_contracts.py` for both session-bound llm and pair retries. No new findings in this re-review.
