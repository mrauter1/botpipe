# Implement ↔ Code Reviewer Feedback

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: maintainability-refactors
- Phase Directory Key: maintainability-refactors
- Phase Title: Maintainability Refactors
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` `autoloop/core/operations.py:_operation_fingerprint`, `autoloop/core/operations.py:_provider_configuration`
  The new replay fingerprint does not actually cover the provider operation configuration requested by the spec. It hashes only the provider class/module and `default_session_name`, so rerunning the same run with the same provider type but a different model/effort or other backend config will silently reuse cached operation values under the new default warn-and-replay path instead of detecting a mismatch. Minimal fix: carry the effective provider operation configuration into `OperationRuntime` and include that concrete config in the fingerprint payload; while touching this, replace the placeholder `_prompt_reference_values()` payload with the real resolved prompt-reference/render inputs the spec calls for.

- `IMP-002` `blocking` `autoloop/core/discovery.py`, `autoloop/core/inventory.py`, `autoloop/core/lowering.py`, `autoloop/core/topology.py`, `autoloop/core/hook_validation.py`, `autoloop/core/prompt_validation.py`, `autoloop/core/state_validation.py`, `autoloop/core/validation.py`
  The requested compiler/validation split was not actually implemented. The new phase modules are facades over private helpers that still live in the monolithic `validation.py`, and `compiler.py` now just imports those facades back into the same underlying file. That misses AC-1’s ownership split and leaves future changes still concentrated in `validation.py`, with extra indirection on top. Minimal fix: move the relevant logic into the new modules and make `validation.py` a thin orchestration/re-export layer or remove it from canonical call paths.

- `IMP-003` `blocking` `autoloop/runtime/loader.py`, `autoloop/core/context.py`, `autoloop/runtime/workspace.py`, `autoloop/runtime/stores/filesystem.py`
  AC-3’s “normalize Mapping inputs to dicts once at public boundaries” is still not met. The diff leaves repeated `dict(...)` normalization at multiple public and internal boundaries (`coerce_workflow_parameter_mapping`, `materialize_workflow_params`, `Context.__init__`, `Context._set_values`, run-workspace metadata readers, filesystem store readers/writers, etc.), so normalization semantics remain scattered instead of centralized. That is an explicit phase deliverable miss and keeps future mapping behavior brittle and repetitive. Minimal fix: introduce shared boundary normalizers for workflow params/input, context values, and persisted payload mappings, apply them once at ingress, and remove the internal defensive copies that become redundant.

- Cycle 2 re-review: `IMP-001`, `IMP-002`, and `IMP-003` are resolved by the current diff.

- `IMP-004` `blocking` `autoloop/core/operations.py:_resolve_runtime`, `autoloop/core/operations.py:_provider_configuration`
  Replay fingerprinting is still incorrect for the public inline override surface `llm(..., provider=...)` / `classify(..., provider=...)` when those calls happen under an active workflow runtime. `_resolve_runtime()` swaps `runtime.provider` to the explicit override provider, but it keeps `provider_configuration=ambient.provider_configuration`, so `_operation_fingerprint()` hashes the ambient engine provider config instead of the actual override provider config. Concrete failure: on a rerun of the same step, changing only the explicit override provider/model can silently reuse a cached operation value with no mismatch warning. I reproduced this with two `RenderedLLMProvider` overrides under the same ambient runtime: the second call replayed the first provider's cached result and never invoked the second provider. Minimal fix: when `_resolve_runtime()` selects a provider different from `ambient.provider`, recompute `provider_configuration()` for that effective provider instead of copying the ambient snapshot, and add a regression test that exercises `llm(..., provider=...)` or `classify(..., provider=...)` inside an active step runtime.
