# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: implement
- Phase ID: execution-normalization
- Phase Directory Key: execution-normalization
- Phase Title: Execution Normalization
- Scope: phase-local authoritative verifier artifact

## Findings

### IMP-001 — blocking
File/symbol: `autoloop/core/engine_collaborators.py:41-45`, `autoloop/core/engine_collaborators.py:690-744`, `autoloop/core/engine_collaborators.py:871-924`, `HookExecutionResult`, `HookRunner.normalize_result`

The phase contract asked for one normalized hook result model and dataclass-based hook/python-step normalization, but the active hook path still depends on positional tuple unpacking. `HookExecutionResult` remains a wrapper around `HookResult`, and `normalize_result()` still returns `(HookResult, explicit_event_override, redirect)` which is unpacked by `run_before`, `run_after`, `run_route`, and the python-step path. This leaves the normalization slice incomplete and keeps the most important hook-control path on the same tuple-based convention the phase was supposed to remove.

Minimal fix direction: finish the hook normalization seam by returning a single dataclass from `normalize_result()` and have `run_before`, `run_after`, `run_route`, and the python-step dispatch path consume that object directly. Centralize the explicit-event-override and redirect fields on that dataclass instead of returning them positionally.

### IMP-002 — blocking
File/symbol: `autoloop/core/engine.py:1201-1260`, `Engine._run_llm_step`

The llm-provider execution path still returns a positional tuple `(Outcome, SessionBinding | None, StepProviderUsage)`, and `_execute_llm_step()` still depends on unpacking it. That means the provider execution plumbing is only partially migrated: pair execution uses `PairProviderResult`, but the plain llm step path still violates the requested dataclass-based normalization across active provider execution paths. This leaves AC-1 / the provider-side part of the deliverable unmet.

Minimal fix direction: replace the `_run_llm_step()` tuple with a dataclass-backed result, ideally alongside the new `ProviderExecResult` seam or a small llm-provider result object in the same collaborator layer, so both pair and llm provider paths follow the same non-positional execution contract.
