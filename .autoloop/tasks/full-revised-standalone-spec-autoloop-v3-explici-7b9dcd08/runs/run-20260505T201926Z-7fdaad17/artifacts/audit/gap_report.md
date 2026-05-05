# Original intent considered

- Immutable request: `.autoloop/tasks/full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08/runs/run-20260505T201926Z-7fdaad17/request.md`
- Authoritative clarification ledger: `.autoloop/tasks/full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08/runs/run-20260505T201926Z-7fdaad17/raw_phase_log.md`
- Run decisions: `.autoloop/tasks/full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08/runs/run-20260505T201926Z-7fdaad17/decisions.txt`
- Pair artifacts reviewed: plan, implement, and test artifacts for all six planned phases
- Final code and tests reviewed:
  - `autoloop/core/branch_groups/{models,validation,runtime,context,sessions,manifest,outcomes}.py`
  - `autoloop/core/{discovery,compiler,artifacts,engine,engine_collaborators}.py`
  - `autoloop/core/providers/protocols.py`
  - `autoloop/runtime/static_graph.py`
  - `tests/contract/test_branch_group_runtime.py`
  - `tests/contract/test_async_step_dispatcher.py`
  - `tests/runtime/test_runtime_static_graph.py`
  - `tests/runtime/test_runtime_tracing.py`
  - `tests/unit/test_branch_group_context_sessions.py`
  - `tests/unit/test_simple_surface.py`
  - `tests/strictness/test_no_compat.py`
  - Full-suite check: `./.venv/bin/python -m pytest -q`

# Clarifications / superseding decisions

- Plan and decision ledger explicitly superseded the earlier thread-backed prototype. Branch groups are required to be asyncio-only, with no sync-provider fallback inside branch execution.
- The accepted run decisions require runtime-owned evidence under `{workflow_folder}/_branch_groups/...`, not root-level `_branch_groups`.
- The accepted run decisions treat branch-group runtime events, additive static-graph metadata, and composite-boundary checkpoint/resume semantics as required v1 surfaces.
- Branch-group workflows may bypass the compiled-workflow cache in v1 if a complete branch-group-sensitive cache key is not implemented safely.
- An intermediate implementation decision allowing operation-based fan-in was explicitly superseded later in the same run. Final intent is to reject operation fan-in declarations.

# Implemented behavior

- The final code cleanly splits authored vs compiled branch-group metadata:
  - `BranchGroupDeclarationSpec` / `BranchStepDeclarationSpec`
  - `CompiledBranchGroupSpec` / `CompiledBranchStepSpec`
- Compile-time branch-group hardening is present:
  - path-safe group and branch names
  - exact `branch` / `fan_in` placeholder-root validation
  - rejection of scoped, child-workflow, and operation branch steps
  - rejection of operation-based fan-in
  - explicit `Session.fresh()` enforcement for provider-backed branch steps
  - branch-group compile-cache bypass
- Async provider and nested-step execution foundations are present:
  - `AsyncLLMProvider` protocol
  - async Codex/Claude transport paths
  - `StepDispatcher.execute_async(..., route_mode="capture")`
  - async branch-group dispatch through `BranchGroupRuntime.run_async(...)`
- The branch runtime now matches the requested concurrency model:
  - `asyncio.Task` scheduling
  - `asyncio.Semaphore` concurrency limiting
  - fail-fast stop/cancel behavior with `cancelled` vs `skipped` recording
  - captured branch routes without following branch destinations
- Session/state/evidence correctness is largely aligned:
  - branch-local fresh session overlay in `BranchSessionStoreView`
  - `session_id=None` on first fresh branch turn until a provider returns a real id
  - evidence rooted under `workflow_folder/_branch_groups/...`
  - shared state cell and shared values mapping without lock-backed merge logic
- Fan-in/outcomes/surface work is present:
  - fan-in metadata surface
  - additive branch-group static-graph payloads
  - branch-group runtime events
  - deterministic branch-group context rendering
- Validation executed during this audit:
  - Focused branch-group suite:
    - `./.venv/bin/python -m pytest -q tests/contract/test_async_step_dispatcher.py tests/contract/test_branch_group_runtime.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_runtime_tracing.py tests/unit/test_branch_group_context_sessions.py tests/unit/test_provider_boundary_core.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/strictness/test_no_compat.py`
    - Result: `277 passed`
  - Full repository suite:
    - `./.venv/bin/python -m pytest -q`
    - Result: `1280 passed, 2 failed`

# Unresolved gaps

- Material gap: the original merge gate said the full test matrix must pass, but the final repository state does not satisfy that gate.
  - Failing tests:
    - `tests/contract/test_canonical_runtime_contracts.py::test_canonical_step_contract_uses_finish_and_required_writes`
    - `tests/contract/test_canonical_runtime_contracts.py::test_canonical_produce_verify_contract_splits_phase_writes_and_verifier_routes`
  - Current behavior:
    - provider-visible `route_required_writes` is empty for inherited required-write routes such as `done`, `question`, `blocked`, and `failed`
  - Evidence:
    - `autoloop/core/engine_collaborators.py:296` currently returns `tuple(compiled_route.required_writes or ())` for each route, which only exposes explicit route metadata
    - `autoloop/core/route_required_writes.py` already defines `effective_route_required_writes(...)`, and the failing canonical tests expect that effective map to be sent to providers
  - Why this is material:
    - it breaks canonical provider request semantics for ordinary `step(...)` and `produce_verify_step(...)` workflows outside the branch-group-focused test surface
    - no clarification or decision in this run authorizes regressing that contract

# Differences justified by later clarification or analysis

- Branch-group workflows bypass the compile cache instead of extending the cache key immediately. This is explicitly justified by the accepted run decisions and is consistent with the request.
- Top-level sync entrypoints still exist, but branch-group internals no longer rely on sync-provider or thread-backed execution. That matches the accepted clarification that any retained sync entrypoint must remain an outer caller only.
- Operation-based fan-in declarations are rejected in the final code even though an intermediate implementation note temporarily allowed them. The later reviewer decision explicitly superseded that allowance.
- The focused branch-group matrix is green, so I did not classify branch-group runtime behavior itself as an unresolved gap. The remaining blocker is repository-wide validation, not an identified missing branch-group contract feature.

# Recommended next run

- Restore the canonical provider `route_required_writes` contract for ordinary step and produce/verify execution.
  - Likely fix surface: `autoloop/core/engine_collaborators.py::ProviderExecutionSurface.route_required_writes`
  - Required behavior: keep per-route `required_writes` / `explicit_required_writes` metadata unchanged, but populate the provider request’s `route_required_writes` map with effective required writes, including inherited required artifacts when a route does not declare an explicit override
- Re-run the two failing canonical contract tests first, then re-run `./.venv/bin/python -m pytest -q`
- Preserve the branch-group behavior already validated by the focused branch-group matrix
