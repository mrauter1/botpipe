# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: scoped-item-state
- Phase Directory Key: scoped-item-state
- Phase Title: Implement Scoped Item State
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `autoloop/simple.py:134-172`, `autoloop/simple.py:359-391`
  The phase contract requires step-level `item_state` authoring for scoped steps, but the simple `step(...)` surface still does not accept or store `item_state`. Only `produce_verify_step(...)` gained that parameter. A scoped simple step such as `step(prompt=\"...\", scope=articles, item_state={\"attempts\": StateVar(0)})` currently fails at call time with an unexpected keyword error, so simple scoped prompt steps cannot use custom per-item state even though the runtime/compiler plumbing was added for it. Minimal fix: add `item_state` to `StepDeclaration` and `step(...)`, lower it through the same scoped item-state path in `core/validation.py`, and add a regression that compiles and exercises a scoped simple `step(...)` with `item_state`.

- Re-review status:
  `IMP-001` is resolved. `autoloop/simple.py` now accepts and stores `item_state` on `step(...)`, and `tests/unit/test_simple_surface.py` covers the scoped prompt-step path plus the unscoped rejection path. No remaining findings in phase scope.
