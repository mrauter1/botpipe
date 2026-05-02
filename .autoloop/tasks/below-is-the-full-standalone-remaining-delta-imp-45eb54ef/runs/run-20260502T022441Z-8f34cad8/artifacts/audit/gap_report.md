# Original intent considered

- Immutable request snapshot in `request.md`, including:
  - final `hook(ctx)` contract for all public hooks;
  - removal of hook state-replacement returns and `AfterStepResult`;
  - `python_step(ctx)` with route/control returns only;
  - public/simple removal of legacy handler surfaces and route effects;
  - updated worklist helpers, trace/history fields, and structured failure context.
- Authoritative clarifications in `raw_phase_log.md`.
- Run decisions in `decisions.txt`.
- Run-local plan / implement / test artifacts.
- Final codebase and focused verification runs.

# Clarifications / superseding decisions

- The user clarified the scoped-item branch to use a built-in runtime-owned `ctx.item_state` surface for active scoped items (`raw_phase_log.md` clarification answer `2`; `decisions.txt` block 4).
- The run explicitly chose fail-fast removals with no compatibility shims for removed surfaces such as `on_route`, route effects, multi-arity hooks, `AfterStepResult`, python-step tuple / `BaseModel` returns, and old `outputs` vocabulary (`decisions.txt` blocks 4, 8, 12).
- No clarification or later decision justified keeping exported workflow packages on the removed hook / python-step contracts.

# Implemented behavior

- The runtime/compiler path reflects the requested core refactor:
  - unified `HookResult` and explicit finalization structures exist in `autoloop/core/engine_collaborators.py`;
  - worklist helper runtime surface exists in `autoloop/core/context.py` and `autoloop/core/worklists.py`;
  - typed `FailureContext` / `WorkflowExecutionError` metadata exists in `autoloop/core/errors.py`;
  - trace/history fields such as `pending_input_id`, `provider_attempted`, `producer_attempted`, and `verifier_attempted` exist in `autoloop/runtime/tracing.py`, `autoloop/core/history.py`, and `autoloop_optimizer/optimization.py`.
- Public-surface cleanup appears implemented in the runtime/compiler/tested slices:
  - `CompiledStep` no longer exposes `on_route_hook` (`tests/unit/test_simple_surface.py`);
  - route effects are rejected (`tests/unit/test_validation.py`);
  - static graph / topology payloads use canonical `writes` / `producer_writes` / `verifier_writes` (`autoloop/runtime/static_graph.py`, `tests/runtime/test_runtime_static_graph.py`).
- Focused verification passed:
  - `./.venv/bin/pytest -q tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/unit/test_primitives_and_stores.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_history.py tests/runtime/test_runtime_tracing.py tests/runtime/test_workspace_and_context.py tests/unit/test_optimization_helpers.py tests/test_architecture_baseline_docs.py`
  - Result: `394 passed`.

# Unresolved gaps

1. Exported workflow packages were not migrated to the final `hook(ctx)` lifecycle-hook contract.
   - Repo-wide package compile sweep over discovered workflow packages produced `TOTAL_OK 0` and `TOTAL_FAIL 16`.
   - Every failure is a removed multi-argument verifier hook form such as:
     - `workflows/autoloop_v1/workflow.py`: `"'plan' after_review hook" must accept 1 positional arguments`
     - `workflows/workflow_idea_to_workflow_package/workflow.py`: `"'frame_candidate' after_review hook" must accept 1 positional arguments`
     - `workflows/release_candidate_to_go_no_go/workflow.py`: `"'frame_release' after_review hook" must accept 1 positional arguments`
     - `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`: `"'frame' after_review hook" must accept 1 positional arguments`
   - Code evidence:
     - `workflows/workflow_idea_to_workflow_package/workflow.py` defines `_after_frame_candidate(ctx, outcome: Outcome)` and wires it via `after_verifier=_after_frame_candidate`.
     - `workflows/workflow_run_traces_to_optimization_candidates/workflow.py` defines `_after_frame(ctx, outcome: Outcome)` and multiple similar `after_verifier` hooks.

2. Those same exported workflow packages still rely on removed hook state-replacement returns.
   - Examples:
     - `workflows/autoloop_v1/workflow.py`: `_after_plan(...)` returns `ctx.state.model_copy(...)`
     - `workflows/release_candidate_to_go_no_go/workflow.py`: `_after_assess_go_no_go(...)` returns `ctx.state.model_copy(...)`
     - `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`: `_after_frame(...)` and related helpers return `ctx.state.model_copy(...)`
   - This conflicts with the request’s final hook return set, which excludes state replacement and requires mutation through `ctx`.

3. The exported workflow packages still rely on removed public `python_step(state, ctx)` handlers.
   - Examples:
     - `workflows/autoloop_v1/workflow.py`: `def activate_next_phase(state: State, ctx):`
     - `workflows/workflow_idea_to_workflow_package/workflow.py`: `def bootstrap(state: State, ctx):` and `def publish_package(state: State, ctx):`
   - A repo scan found the same legacy python-step signature in the same 16 workflow packages that failed the compile sweep.

4. Some workflow-specific tests still exercise the legacy package-local helper shapes instead of the final public contract.
   - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py` directly calls methods such as `WorkflowRunTracesToOptimizationCandidates.on_capture_frame_context(state, ctx)` and `on_route_optimize_tokens(...)`.
   - This is secondary to the compile failure, but it will need migration once the packages move to explicit `ctx`-only hooks and handlers.

# Differences justified by later clarification or analysis

- The clarified built-in `ctx.item_state` contract is intentional and matches the authoritative clarification.
- Internal strict/runtime support for legacy class-level hooks such as `on_start` / `on_outcome` still exists in non-simple paths (`autoloop/core/hook_validation.py`, `autoloop/core/lowering.py`, `autoloop/core/engine.py`), but the public/simple path rejects those handlers. That matches the request, which removed them from the public compiler path rather than requiring deletion of every internal strict path in the repo.
- Typed exception helper readers such as `exception_failure_context(...)` remain, but they read explicit `WorkflowExecutionError` fields rather than `getattr(...)`-attached ad hoc metadata. That is consistent with the structured-error cleanup requested.

# Recommended next run

- Material follow-up is required.
- Narrow the next run to migrating the exported workflow packages under `workflows/*/workflow.py` to the final public contract:
  - convert lifecycle hooks to `hook(ctx)`;
  - replace hook state returns with direct `ctx.state` mutation;
  - convert python-step handlers from `(state, ctx)` to `ctx`;
  - update package-specific tests that directly call the removed helper forms;
  - add a repo-level regression check that all discovered workflow packages compile successfully under the final public contract.
