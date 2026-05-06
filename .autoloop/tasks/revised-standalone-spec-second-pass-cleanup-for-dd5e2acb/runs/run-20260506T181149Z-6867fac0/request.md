## Revised standalone spec: second-pass cleanup for async-native branch groups

* **Spec purpose**

  * Make the current async-native branch-group implementation merge-ready.
  * Keep this pass focused on correctness and technical-debt cleanup.
  * Do not use this pass to redesign branch groups, provider architecture, operation runtime, fan-in, or worklists.
  * Preserve the current good direction:

    * async engine spine;
    * async step dispatcher;
    * async provider-shaped execution;
    * `asyncio` branch scheduling;
    * branch evidence under `workflow_folder/_branch_groups`;
    * public non-parallel API compatibility;
    * compile-time rejection of scoped, child-workflow, and operation branch steps. 

---

## 1. Scope of this pass

* Keep the pass small.
* Fix only merge-blocking correctness issues and obvious technical debt.
* Do not add broad new abstractions.
* Do not add compatibility shims.
* Do not add thread-backed fallbacks.
* Do not add sync-provider fallbacks.
* Do not redesign provider internals.
* Do not redesign operation runtime.
* Do not redesign fan-in.
* Do not add worklist fan-out.
* Do not add child workflow branches.
* Do not add workspace isolation.
* Do not add branch state merge policies.
* Do not add async local filesystem I/O.
* Do not re-enable compile cache for branch-group workflows unless trivial and safe.

---

## 2. Preserve public non-parallel API behavior

* Existing non-parallel authoring APIs must remain stable.
* Do not require ordinary workflow authors to change:

  * `Workflow`;
  * `step(...)`;
  * `llm(...)`;
  * `produce_verify_step(...)`;
  * `python_step(...)`;
  * `workflow_step(...)`;
  * `Session`;
  * `Session.fresh()`;
  * `Session.run()`;
  * route declarations;
  * artifact declarations;
  * CLI/run entrypoints.
* `Engine.run(...)` may remain as a public synchronous wrapper around `Engine.run_async(...)`.
* `Engine.run(...)` must remain only an outer wrapper.
* `Engine.run(...)` must not preserve sync provider execution internally.
* `Engine.run(...)` must not introduce threads.

---

## 3. Preserve current async-native branch-group model

* Branch groups continue to use async execution.
* Branch runtime continues to use:

  * `asyncio.create_task(...)`;
  * `asyncio.Semaphore`;
  * task cancellation.
* Branch groups execute branch steps with:

  * `route_mode="capture"`.
* Branch routes are captured, not followed.
* Branch route `on_taken` hooks must not run.
* Fan-in runs after branch settlement.
* Fan-in finalizes exactly once through the composite branch-group route.
* Branch evidence remains under:

  * `{workflow_folder}/_branch_groups/<group_name>/results.json`;
  * `{workflow_folder}/_branch_groups/<group_name>/context.md`.

---

## 4. Mandatory fix: remove duplicate branch final-state mutation

* `RouteFinalizer.capture(...)` is the single owner of capture-mode final-state updates.
* `BranchGroupRuntime._branch_result_from_step_result(...)` must not mutate final runtime state.
* Remove manual calls equivalent to:

  * `_engine._update_final_step_runtime_state(...)`;
  * `_engine._update_final_item_runtime_state(...)`.
* Branch result construction should be observational.
* Branch result construction may:

  * read `StepExecutionResult`;
  * collect artifacts;
  * collect provider session metadata;
  * write raw-output evidence;
  * return a branch result payload.
* Branch result construction must not update:

  * step state;
  * item state;
  * workflow state;
  * parent session state.
* Rationale:

  * capture finalization already updates runtime state;
  * duplicate updates can double-count `rework_count` or `replan_count` for produce/verify branches.
* Required regression test:

  * a produce/verify branch returning `needs_rework` increments `rework_count` exactly once.

---

## 5. Mandatory fix: make `BranchSessionStoreView` branch-local only

* `BranchSessionStoreView` must be branch-local only.
* `BranchSessionStoreView.get(...)` must not fall back to parent active sessions.
* `BranchSessionStoreView.open(...)` must not fall back to parent active sessions.
* `BranchSessionStoreView.snapshot(...)` must not expose parent active sessions.
* Branch-local provider session lookup may use only:

  * branch-local bindings;
  * branch-local active keys;
  * branch-local fresh keys.
* Branch-local provider session lookup must not use:

  * parent active keys;
  * parent run-session bindings;
  * parent store fallback.
* New branch-fresh provider sessions must start with:

  * `session_id=None`.
* No synthetic provider session ids may be fabricated.
* Provider receives `session_id=None` on the first turn of a fresh branch session.
* Branch result records a provider session id only after the provider returns a real one.
* Parent active session slots must remain unchanged after branch execution.
* Do not add a separate diagnostic snapshot API in this pass.
* If parent session diagnostics are needed later, add a separate helper in a future pass.
* Required regression test:

  * create a parent active provider session;
  * run a provider-backed branch with explicit `Session.fresh()`;
  * assert the first branch provider request receives `session_id=None`;
  * assert the parent active session remains unchanged;
  * assert the branch result does not report the parent session id.

---

## 6. Mandatory fix: remove unreachable scoped/worklist runtime handling inside branch execution

* Scoped branch steps are out of v1.
* Compile-time validation should continue rejecting scoped branch steps.
* Runtime should not partially support scoped branch execution.
* In branch execution, if `compiled_step.scope_name is not None`, raise an internal assertion/error.
* Do not initialize worklist selections inside branch execution.
* Do not initialize branch item-state stores inside branch execution.
* Do not initialize branch step-item-state stores inside branch execution.
* Keep only branch-scoped step state.
* Rationale:

  * partial scoped runtime support creates ambiguity;
  * future worklist fan-out should be explicitly designed.
* Required compile-time test:

  * a scoped branch step fails.
* Optional defensive runtime test:

  * a manually constructed scoped compiled branch raises an internal assertion instead of executing worklist logic.

---

## 7. Mandatory fix: contain operation bridge usage

* Operation branch steps remain rejected in v1.
* The sync operation bridge may remain only for existing non-parallel public API compatibility.
* Operation bridge usage must not leak into:

  * provider-backed branch execution;
  * prompt branch execution;
  * produce/verify branch execution;
  * provider-backed fan-in execution.
* Do not redesign operation runtime in this pass.
* Do not remove public non-parallel behavior unless necessary.
* Required regression test:

  * provider-backed branch execution cannot call `run_operation(...)`.
* Required compile-time tests:

  * `parallel(...)` rejects operation branch steps;
  * `fan_out(...)` rejects operation branch steps.

---

## 8. Mandatory fix: strictness rule for `subprocess.run(...)`

* Provider turn execution must not use `subprocess.run(...)`.
* Provider turn execution must use async subprocess execution.
* Codex/Claude turn execution should use:

  * `asyncio.create_subprocess_exec(...)`.
* Do not ban `subprocess.run(...)` globally if it is used only for construction-time or startup-time CLI capability probing.
* Acceptable:

  * `subprocess.run(...)` in explicit CLI probing functions such as `--help` checks.
* Not acceptable:

  * `subprocess.run(...)` inside provider turn execution;
  * `subprocess.run(...)` during branch execution;
  * `subprocess.run(...)` as a provider fallback path.
* Strictness tests should inspect provider turn execution paths.
* Strictness tests should not blindly fail on all `subprocess.run(...)` occurrences across configuration or probing code.
* Required tests:

  * Codex turn execution uses async subprocess execution;
  * Claude turn execution uses async subprocess execution;
  * provider turn execution cannot reach `subprocess.run(...)`.

---

## 9. Mandatory fix: avoid repeated provider session snapshot reads

* In failed branch result construction, compute provider session snapshot once.
* Do not call `_provider_session_snapshot(...)` twice for the same result.
* Required shape:

  * `provider_session, provider_sessions = self._provider_session_snapshot(...)`;
  * use those values in the returned branch result.
* Rationale:

  * the session store is mutable;
  * duplicate reads are unnecessary;
  * duplicate reads can produce inconsistent metadata in edge cases.
* Required test:

  * failed branch result has consistent `provider_session` and `provider_sessions`.

---

## 10. Preserve capture-only branch semantics

* Branch execution uses `route_mode="capture"`.
* Capture mode must:

  * run before hooks;
  * run provider/system body;
  * run after hooks;
  * validate artifacts;
  * validate route legality;
  * compute route destination;
  * record route/destination.
* Capture mode must not:

  * run route `on_taken`;
  * schedule handoffs;
  * follow destination.
* Required tests:

  * branch `on_taken` hook is not called;
  * branch `Goto` is captured and not followed;
  * branch `RequestInput` becomes `needs_input`;
  * branch `Fail` becomes `failed`.

---

## 11. Preserve fan-in single finalization

* Fan-in runs after branch settlement.
* Fan-in may run in capture mode internally.
* Composite branch group finalizes the fan-in result once.
* There must not be:

  * fan-in internal full finalization plus composite finalization;
  * double route `on_taken`;
  * double artifact enforcement;
  * double transition recording.
* Required tests should verify observable finalization side effects:

  * fan-in route `on_taken` hook executes exactly once;
  * fan-in artifact enforcement happens once;
  * final transition is recorded once;
  * fan-in `RequestInput` maps to composite input behavior once.

---

## 12. Evidence write failure behavior

* Keep current ordering:

  * run branches;
  * build manifest;
  * write `results.json`;
  * write `context.md`;
  * then run fan-in or mechanical outcome.
* If writing `results.json` fails:

  * do not run fan-in;
  * do not run mechanical outcome;
  * fail the branch group.
* If writing `context.md` fails:

  * do not run fan-in;
  * do not run mechanical outcome;
  * fail the branch group.
* Required targeted test:

  * evidence write failure prevents fan-in execution.
* Do not build a larger evidence-failure framework in this pass.

---

## 13. Existing behavior to keep

* Keep async provider protocol validation.
* Keep async transport protocol validation.
* Keep `Engine.run_async(...)`.
* Keep public `Engine.run(...)` wrapper.
* Keep `StepDispatcher.execute_async(...)`.
* Keep branch-group task scheduling.
* Keep deterministic branch manifest ordering.
* Keep evidence under `workflow_folder/_branch_groups`.
* Keep compile-time rejection of:

  * scoped branch steps;
  * child workflow branch steps;
  * operation branch steps;
  * scoped fan-in;
  * child workflow fan-in;
  * invalid branch placeholders;
  * invalid fan-in placeholders;
  * `FanIn.results()` outside fan-in;
  * `FanIn.context()` outside fan-in.

---

## 14. Explicitly out of scope for this pass

* No bounded artifact excerpts in context markdown.
* No partial branch checkpoint/resume.
* No branch-level interactive resume.
* No worklist fan-out.
* No child workflow branch support.
* No child workflow fan-in support.
* No provider session forking.
* No workspace overlays.
* No automatic file conflict detection.
* No state merge policy.
* No async local filesystem conversion.
* No full compile-cache redesign for branch-group workflows.
* No operation runtime redesign.
* No new branch synchronization primitives.
* No new session diagnostics API.

---

## 15. Required compile-time tests

* Missing provider branch session fails.
* Non-fresh provider branch session fails.
* Explicit fresh provider branch session passes.
* Produce/verify branch with non-fresh verifier session fails.
* Scoped branch step fails.
* Child workflow branch step fails.
* Operation branch step fails.
* Scoped fan-in fails.
* Child workflow fan-in fails.
* Operation fan-in fails unless explicitly supported.
* Branch placeholder outside branch step fails.
* Fan-in placeholder outside fan-in step fails.
* `FanIn.results()` outside fan-in fails.
* `FanIn.context()` outside fan-in fails.
* Unsafe group name fails.
* Unsafe branch name fails.

---

## 16. Required runtime tests

* Branch result construction does not double-update step state.
* Produce/verify branch rework count increments exactly once.
* Branch provider lookup never uses parent active session.
* Fresh branch session first provider request receives `session_id=None`.
* Parent active session remains unchanged after branch execution.
* Two branches using the same `Session.fresh()` declaration get distinct branch-local provider contexts.
* Branch route destination is not followed.
* Branch `on_taken` hook is not run in capture mode.
* Fan-in route finalizes exactly once.
* Branch `RequestInput` is captured as `needs_input`.
* Branch question routes composite to `question` when no fan-in exists.
* Branch `Goto` is captured and not followed.
* Branch `Fail` is captured as failed.
* Same-file writes from branches are not rejected.
* Branch state assignment updates shared state cell.
* Branch values mutation updates shared values mapping.
* Manifest branch order follows declaration order.
* Branch context markdown is deterministic.
* Evidence write failure prevents fan-in.
* Branch evidence path is under `workflow_folder`.

---

## 17. Required strictness tests

* Branch-group runtime must not import or use:

  * `ThreadPoolExecutor`;
  * `Future`;
  * `concurrent.futures`;
  * `FIRST_COMPLETED`;
  * `threading.RLock`;
  * `asyncio.to_thread`.
* Provider turn execution must not use:

  * `subprocess.run`;
  * `ThreadPoolExecutor`;
  * `asyncio.to_thread`.
* `subprocess.run(...)` is allowed only in explicit construction-time capability probing.
* Provider protocol must not expose sync producer/verifier/LLM turn methods.
* Provider transport protocol must not expose sync turn execution.
* Branch-group runtime must not contain provider async capability probing.
* Provider-backed branch execution must not reach `run_operation(...)`.

---

## 18. Required provider tests

* `validate_llm_provider(...)` rejects sync producer/verifier/LLM methods.
* `validate_provider_transport(...)` rejects sync `run_turn`.
* `RenderedLLMProvider.run_producer(...)` awaits transport.
* `RenderedLLMProvider.run_verifier(...)` awaits transport.
* `RenderedLLMProvider.run_llm(...)` awaits transport.
* Codex transport turn execution uses `asyncio.create_subprocess_exec`.
* Claude transport turn execution uses `asyncio.create_subprocess_exec`.
* Fake provider is async-native for producer/verifier/LLM.
* Fake provider does not fake async by calling sync producer/verifier/LLM methods.

---

## 19. Code cleanup checklist

* Delete duplicate final-state update code from `BranchGroupRuntime._branch_result_from_step_result(...)`.
* Remove or assert unreachable scoped branch runtime code.
* Tighten `BranchSessionStoreView` so it is branch-local only.
* Keep new fresh branch bindings at `session_id=None`.
* Compute provider session snapshot once per failed branch result.
* Add comments around any retained operation bridge:

  * public non-parallel compatibility only;
  * not branch provider execution;
  * not provider fallback.
* If `BranchGroupRuntime.run(...)` remains:

  * document it as an outer bridge only;
  * ensure engine branch execution uses `run_async(...)`.

---

## 20. Acceptance criteria

* No duplicate final-state mutation remains in branch result construction.
* `BranchSessionStoreView` is branch-local only.
* Parent active provider sessions cannot leak into branch provider execution.
* Scoped/worklist branch runtime code is removed or assertion-only.
* Operation bridge is contained to non-branch compatibility use.
* Strictness tests distinguish provider turn execution from CLI capability probing.
* Fan-in finalizes exactly once.
* Branch capture mode remains capture-only.
* Evidence write failures stop fan-in/outcome.
* Public non-parallel authoring API remains unchanged.
* All required compile-time, runtime, provider, and strictness tests pass.

---

## 21. Merge recommendation

* Merge after the mandatory fixes and tests above pass.
* Do not block merge on lower-priority markdown/context polish.
* Do not block merge on full compile-cache support if branch-group workflows safely bypass the cache.
* Do not block merge on async local filesystem I/O.
* Do not expand this pass into a new architecture project.
* After this cleanup pass, the implementation should be considered merge-ready unless tests expose new correctness issues.
