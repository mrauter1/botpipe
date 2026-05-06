# gap_report.md
## Original intent considered

- Original request snapshot: async-native provider execution, async-native provider transports, async-first engine/dispatcher internals, explicit `parallel(...)` / `fan_out(...)` branch groups, branch-local fresh sessions, deterministic branch evidence under `workflow_folder/_branch_groups/...`, additive public APIs, and strictness/runtime/provider/compile-time coverage.
- Authoritative sources reviewed:
  - `request.md`
  - `raw_phase_log.md`
  - `decisions.txt`
  - phase-local implement/test artifacts under `artifacts/implement` and `artifacts/test`
  - final code and focused validation in the current tree

## Clarifications / superseding decisions

- The raw log contains one material clarification that supersedes the original absolute prohibition on sync provider execution in one narrow case. In `decisions.txt` block 8 and the corresponding raw-log Q&A, the run explicitly chose `YES` for preserving public `llm()` / `classify()` behavior inside synchronous Python steps under an already-active workflow event loop.
- That clarification narrows the allowed exception to a compatibility-only helper path:
  - not part of the `LLMProvider` protocol
  - not part of the `ProviderTransport` protocol
  - not allowed in branch/capture execution
- The planner decision to keep branch-group compile-cache bypass in v1 unless a full cache key lands is also authoritative and consistent with request section 42.

## Implemented behavior

- Async-only provider and transport contracts are in place in `autoloop/core/providers/protocols.py`:
  - `LLMProvider` exposes only async `run_producer`, `run_verifier`, and `run_llm`
  - `ProviderTransport` exposes only async `run_turn`
  - constructor validation rejects sync-only implementations
- The engine is async-first:
  - `Engine.run(...)` and `Engine.resume(...)` are sync shells
  - `Engine.run_async(...)` and `Engine.resume_async(...)` are the real execution paths in `autoloop/core/engine.py`
  - `StepDispatcher.execute_async(...)` is the authoritative dispatcher path in `autoloop/core/engine_collaborators.py`
- Branch-group execution is delegated outside `engine.py` into `autoloop/core/branch_groups/runtime.py` and runs in capture mode for branch/fan-in internals.
- Branch-group runtime semantics match the requested v1 shape:
  - async scheduling with `asyncio.create_task(...)` and `asyncio.Semaphore`
  - deterministic manifest order
  - branch evidence under `{workflow_folder}/_branch_groups/<group>/results.json` and `context.md`
  - `ctx.branch` and `ctx.fan_in` metadata
  - shared `StateCell` and shared `ctx.values`
  - branch-local `BranchSessionStoreView` fresh-session overlays
- Public additive APIs are exported:
  - `parallel(...)`
  - `fan_out(...)`
  - `FanIn.results()`
  - `FanIn.context()`
  - evidence: `autoloop/simple.py` and `autoloop/__init__.py`
- Built-in Codex and Claude workflow-turn transports are async-native and use `asyncio.create_subprocess_exec(...)` in `autoloop/runtime/providers/codex.py` and `autoloop/runtime/providers/claude.py`.
- Strictness and regression coverage exists for the requested merge-gate themes:
  - async-only provider/transport protocol assertions in `tests/strictness/test_no_compat.py`
  - branch-group runtime/session coverage in `tests/contract/test_branch_group_runtime.py` and `tests/unit/test_branch_group_context_sessions.py`
  - backend and transport coverage in `tests/runtime/test_provider_backends.py` and `tests/runtime/test_runtime_providers.py`
  - public simple-surface and placeholder validation coverage in `tests/unit/test_simple_surface.py`

Validation evidence:

- Implement/test artifacts already record passing phase-local matrices, including:
  - provider/test strictness re-review: `381 passed, 15 warnings`
  - branch-group runtime/session bundle: `196 passed`
- Final audit rerun in the current tree:
  - `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/contract/test_async_engine_spine.py tests/contract/test_branch_group_runtime.py tests/runtime/test_provider_backends.py tests/runtime/test_runtime_providers.py tests/runtime/test_runtime_static_graph.py tests/unit/test_provider_boundary_core.py tests/unit/test_simple_surface.py -q`
  - result: `264 passed, 15 warnings`

## Unresolved gaps

- No material unresolved implementation gaps found.

## Differences justified by later clarification or analysis

- The remaining sync compatibility bridge for `llm()` / `classify()` is intentional, explicit, and authoritative rather than unresolved:
  - implementation surface: `autoloop/core/providers/rendered.py`, `autoloop/runtime/provider_backends.py`, `autoloop/runtime/providers/_common.py`, `autoloop/runtime/providers/codex.py`, and `autoloop/runtime/providers/claude.py`
  - justification: the authoritative raw-log clarification accepted this temporary exception to preserve existing public non-parallel helper behavior inside synchronous Python steps under the async engine
  - containment: strictness tests explicitly treat this as the only allowed non-operation sync bridge surface
- Branch-group compile caching remains bypassed for workflows containing branch groups in `autoloop/core/compiler.py`. That is explicitly permitted by request section 42 when the full cache-key implementation is judged too risky for v1, so it is not an unresolved gap.
- The request’s module-boundary list for `branch_groups/scheduler.py` and `branch_groups/static_graph.py` was phrased as recommended rather than mandatory. The current tree still keeps branch runtime logic out of `engine.py` and exposes branch-group static graph payloads through the existing runtime static-graph surface, so this is not a material contract miss.

## Recommended next run

- No follow-up implementation run is required for this request.
- If product direction later removes the temporary helper-compatibility exception, the next targeted run should redesign `llm()` / `classify()` operation execution around a fully async-safe path for synchronous Python-step authoring or intentionally deprecate that helper behavior with an explicit public compatibility decision.
