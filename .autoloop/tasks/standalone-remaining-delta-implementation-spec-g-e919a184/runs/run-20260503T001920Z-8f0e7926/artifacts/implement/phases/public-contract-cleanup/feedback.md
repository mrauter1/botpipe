# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: implement
- Phase ID: public-contract-cleanup
- Phase Directory Key: public-contract-cleanup
- Phase Title: Public Contract Cleanup
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — [autoloop/core/context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/context.py:162) still gives hook code access to `ctx._runtime`, and `_ContextRuntime` exposes the same internal mutators and cache/selection setters the phase was meant to remove (`set_state`, `set_selection`, `cache_worklist_items`, `set_worklist_selection_sync`, and related helpers at [autoloop/core/context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/context.py:560)). That means author hooks can still reach runtime-owned internals through a private backdoor, so AC-3 is not actually satisfied. Minimal fix: keep the runtime mutation service off the public hook object entirely, e.g. move it to a runtime-only wrapper/service used by engine/worklists or pass a proxy `Context` view into hooks that does not expose `_runtime`.

- IMP-002 `blocking` — The legacy class-handler/state-return path is still compiled and validated even though this phase explicitly called for removing legacy public hook signatures, state-return paths, and tightening validation to exact `hook(ctx)` only. `_compile_outcome_handler()` in [autoloop/core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/compiler.py:429), `outcome_middleware_name()` in [autoloop/core/lowering.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/lowering.py:16), `has_start_hook()` in [autoloop/core/discovery.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/discovery.py:291), and `validate_handlers()` in [autoloop/core/hook_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/hook_validation.py:24) still accept `on_<step>(state, outcome, artifacts)`, `on_outcome(state, outcome)`, `on_start(...)`, and 2-arg `PythonStep` handlers. A strict/core workflow can therefore still replace state through the removed path, which leaves AC-1 unmet and silently contradicts the requested final hook model. Minimal fix: remove these compilation/validation branches and require explicit step hooks plus one-arg `python_step` handlers, or get an explicit scope clarification before keeping the legacy path.
