# Original intent considered

- The immutable request requires explicit `parallel(...)` / `fan_out(...)` branch groups with optional authored `fan_in`, compile-time fresh-session enforcement for provider-backed branch steps, shared parent state / values / workspace semantics, deterministic `_branch_groups/<group>/results.json` and `context.md` evidence, mechanical no-`fan_in` outcomes, branch-local provider session isolation, additive static-graph/topology inspection, and composite-boundary checkpoint/resume behavior.
- The request’s explicit runtime test matrix also called out:
  - state assignment in branch reaches the shared state cell;
  - values mutation in branch reaches the shared values mapping;
  - same-file / overlapping writes are not rejected;
  - fan-in pending input resumes through normal workflow resume behavior.

# Clarifications / superseding decisions

- The authoritative raw log does not contain later user clarification entries that change the requested behavior; intent remains the original request snapshot.
- Run-local decisions that materially shape interpretation:
  - `decisions.txt` block 1: reuse `StepDispatcher.execute()` for nested single-step execution and keep checkpointing at the composite boundary.
  - block 2: fan-in support stays explicit for LLM/prompt, produce/verify, Python, and operation steps; `results.json` / `context.md` are part of the required persisted contract.
  - block 7 and 8: branch execution must share one state cell while keeping branch-local session-store overlays and child-local worklist bookkeeping.
  - block 10: `all_settled` must honor `success_routes`, not just terminal completion.
  - block 11, 12, 13, and 14: concurrent execution only guarantees declaration-ordered persisted evidence, `fail_fast` coverage is intentionally stabilized with `concurrency=1`, and evidence-write failure is tested at the imported runtime call site.
  - block 15 and 16: additive static-graph/topology metadata and topology hashing are part of the final shipped surface.

# Implemented behavior

- Public authoring and compile surface is present:
  - `autoloop/simple.py` exports `parallel`, `fan_out`, and `FanIn`.
  - `autoloop/core/discovery.py`, `autoloop/core/branch_groups/validation.py`, and `autoloop/core/compiler.py` lower branch groups as one external composite step, keep nested branches internal, validate fresh sessions for provider-backed branch steps, reject child-workflow branch/fan-in steps, validate branch/fan-in placeholders, and wire `FanIn.results()` / `FanIn.context()`.
- Runtime behavior is implemented in a dedicated subsystem rather than in `Engine.run()`:
  - `autoloop/core/branch_groups/runtime.py` schedules branches with a bounded `ThreadPoolExecutor`, captures branch results without following branch destinations, writes `_branch_groups/<group>/results.json` and `context.md`, runs authored fan-in steps, or applies mechanical outcomes.
  - `autoloop/core/branch_groups/context.py` and `autoloop/core/context.py` provide shared `StateCell` state, branch/fan-in metadata, and branch-scoped execution IDs.
  - `autoloop/core/branch_groups/sessions.py` keeps fresh branch sessions local to a `BranchSessionStoreView` rather than activating the parent slot.
  - `autoloop/core/branch_groups/manifest.py` and `autoloop/core/branch_groups/outcomes.py` implement the persisted branch manifest/context contract and the built-in no-`fan_in` outcome policies.
- Static graph / topology / tracing support is shipped:
  - `autoloop/runtime/static_graph.py` surfaces additive nested `branch_group` metadata.
  - `autoloop/core/compiler.py` includes branch-group internals in `topology_hash`.
  - `tests/runtime/test_runtime_tracing.py` covers the new branch-group runtime events.
- Final verification run during this audit:
  - `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k 'branch_group or fan_in or provider_backed_branch'` -> `14 passed`
  - `.venv/bin/python -m pytest -q tests/contract/test_branch_group_runtime.py` -> `8 passed`
  - `.venv/bin/python -m pytest -q tests/unit/test_branch_group_context_sessions.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_runtime_tracing.py -k 'branch_group or fan_in or topology or static_graph'` -> `23 passed`

# Unresolved gaps

- Missing committed regression coverage for shared-state, shared-values, and overlapping-write semantics that the request explicitly called out.
  - Evidence:
    - The request’s runtime matrix explicitly requires tests for shared state assignment, shared values mutation, and overlapping writes.
    - The committed branch-group runtime contract file `tests/contract/test_branch_group_runtime.py` covers evidence writing, fan-in routing, `Goto`, `RequestInput`, `fail_fast`, and mechanical outcomes, but does not include assertions for those three shared-effect behaviors.
    - Audit-only runtime probes confirmed the current implementation does appear to satisfy the behavior today:
      - a two-branch state update probe finished with `counter=2`;
      - a values-sharing probe showed downstream access to both branch-written keys;
      - an overlapping-write probe showed both branches writing the same file without runtime rejection.
  - Why this is material:
    - These shared-effect semantics are central to the requested author-responsibility model and are easy to regress in future runtime/session/workspace refactors if they remain unpinned by committed tests.

- Missing committed regression coverage for fan-in pending-input checkpoint/resume behavior.
  - Evidence:
    - The request explicitly requires that fan-in pending input use normal workflow resume behavior.
    - The committed tests cover branch-level `RequestInput` without fan-in and fan-in happy-path routing, but there is no test that makes the fan-in step itself ask a question, persists a composite-boundary checkpoint, and resumes to completion.
  - Why this is material:
    - Composite-boundary checkpoint/resume is a core behavioral requirement, and the nested-result-to-composite mapping in `autoloop/core/branch_groups/runtime.py` is exactly the sort of logic that can regress without targeted coverage.

# Differences justified by later clarification or analysis

- The request recommended a branch-group `static_graph.py` module under `autoloop/core/branch_groups`, but the implementation extends the existing `autoloop/runtime/static_graph.py` and compiler topology hashing instead. This is justified because the request labeled that layout as recommended rather than mandatory, and the delivered behavior still provides additive branch-group graph/topology inspection without moving scheduling logic back into `engine.py`.
- Concurrent branch execution is only guaranteed to preserve declaration order in persisted manifests and context summaries, not provider callback ordering or log interleaving. That is explicitly recorded in `decisions.txt` block 11 and is consistent with the original request’s deterministic-order requirement for persisted evidence rather than transport-level callback timing.
- `fail_fast` regression coverage intentionally uses `concurrency=1` to assert deterministic admission stopping and persisted `skipped` rows. This is a testing clarification from `decisions.txt` block 13, not a reduction in runtime behavior.

# Recommended next run

- Keep scope narrow and finish the missing branch-group regression coverage rather than reopening the whole feature.
- Add committed branch-group runtime/contract coverage for:
  - shared `ctx.state` updates across real branch execution;
  - shared `ctx.values` mutation visibility after branch settlement;
  - overlapping writes to the same workspace path not being rejected;
  - a fan-in step that returns `RequestInput`, checkpoints at the composite boundary, and resumes through normal workflow resume.
- If any new test exposes a bug, apply the smallest runtime/checkpoint fix required to make the requested behavior pass.
