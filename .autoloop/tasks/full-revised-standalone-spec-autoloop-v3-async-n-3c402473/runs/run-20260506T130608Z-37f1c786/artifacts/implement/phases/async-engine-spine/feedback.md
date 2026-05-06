# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: implement
- Phase ID: async-engine-spine
- Phase Directory Key: async-engine-spine
- Phase Title: Async engine spine
- Scope: phase-local authoritative verifier artifact

## Findings

### IMP-001 — blocking — Sequential `Engine.run(...)` no longer supports the current sync `LLMProvider` contract
- Reference: `autoloop/core/engine.py:179`, `autoloop/core/engine.py:478`, `autoloop/core/engine_collaborators.py:458`, `autoloop/core/providers/protocols.py:11`
- Concrete failure: `Engine.run(...)` now always enters `run_async(...)`, which always awaits `StepDispatcher.execute_async(...)`. That async path hard-requires `supports_async_llm_provider(...)`, so an existing provider that still satisfies the repository’s current public `LLMProvider` protocol but does not implement `run_*_async(...)` now fails with `ProviderExecutionError` during ordinary sequential workflows.
- Regression scenario: a caller with a pre-existing sync-only custom provider that previously worked for non-branch workflows now gets `provider 'X' does not implement async step execution methods` from `Engine.run(...)`, even though provider protocol removal is explicitly out of scope for this phase.
- Minimal fix direction: keep the async engine spine, but centralize temporary sequential-provider compatibility at the provider-dispatch boundary rather than in `engine.py`. A focused helper inside `StepDispatcher.execute_async(...)` (or a dedicated provider adapter owned by the dispatcher) should preserve current sync `LLMProvider` behavior for ordinary sequential execution until the later provider-cutover phase lands. Branch-group/runtime async-only enforcement can remain separate.

### IMP-002 — non-blocking — Large dead sync provider helpers remain in `engine.py`
- Reference: `autoloop/core/engine.py:790`
- Concrete issue: after `Engine.run_async(...)` and `StepDispatcher.execute(...)` were switched to the async-authoritative path, the old sync provider execution helpers (`_execute_pair_step`, `_execute_llm_step`, `_execute_workflow_step`, and their lower-level sync helpers) remain in place but are no longer on the main execution path.
- Technical-debt risk: this leaves a large duplicated implementation body in `engine.py` that future provider/runtime changes can drift against, even though the phase intent was to remove duplicated sync provider logic.
- Minimal fix direction: delete the unreachable sync helper stack or fold any still-needed shared logic into dispatcher-owned helpers so there is only one maintained provider-backed execution implementation.
