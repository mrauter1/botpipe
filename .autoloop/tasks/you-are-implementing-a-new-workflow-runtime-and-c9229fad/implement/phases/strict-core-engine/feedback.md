# Implement ↔ Code Reviewer Feedback

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: implement
- Phase ID: strict-core-engine
- Phase Directory Key: strict-core-engine
- Phase Title: Strict Core Engine
- Scope: phase-local authoritative verifier artifact

## Findings

- `IMP-001` `blocking` [autoloop_v3/workflow/validation.py:234](../../../../../../autoloop_v3/workflow/validation.py#L234), [autoloop_v3/workflow/compiler.py:155](../../../../../../autoloop_v3/workflow/compiler.py#L155), [autoloop_v3/workflow/engine.py:92](../../../../../../autoloop_v3/workflow/engine.py#L92): step names that collide with reserved hook names are currently accepted as valid workflows, but they execute incorrectly. A pure v1.1 workflow with a step named `start` compiles, then crashes before the first step because `Engine.run()` treats `on_start` as the lifecycle hook and calls the step handler with the wrong arity (`TypeError: ... missing 1 required positional argument: 'outcome'`). A step named `outcome` or `verdict` is also broken because the same method is compiled both as the step handler and as global middleware, causing a `ProviderExecutionError` or skipped state updates. This violates P2-AC1 for otherwise valid strict-core workflows. Minimal fix: centralize reserved-hook-name handling in one place, either by rejecting step names that collide with lifecycle or middleware hooks during definition-time validation or by separating lifecycle and middleware lookup from step-handler lookup so `on_start`, `on_outcome`, and `on_verdict` cannot be double-purposed.

## Re-review Cycle 2

- `IMP-001` resolved: verified that reserved hook-name precedence is now centralized through `has_start_hook()` and `middleware_handler_name()`, `Engine.run()` only invokes the lifecycle hook when that hook is active, and regression tests cover steps named `start`, `outcome`, and `verdict`.
- No remaining `blocking` or `non-blocking` findings in this review pass.
