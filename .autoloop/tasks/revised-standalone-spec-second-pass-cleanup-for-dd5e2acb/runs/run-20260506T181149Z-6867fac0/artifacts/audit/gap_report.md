# Original intent considered

- The immutable request in `request.md` asked for a small cleanup pass that keeps the async-native branch-group design, preserves public non-parallel APIs, and fixes the listed merge-blocking correctness issues only.
- I compared that request against the final code in `autoloop/core/branch_groups/runtime.py`, `autoloop/core/branch_groups/sessions.py`, `autoloop/core/providers/rendered.py`, the runtime transports in `autoloop/runtime/providers/codex.py` and `autoloop/runtime/providers/claude.py`, the compile/runtime/provider/strictness tests under `tests/`, and the run-local plan/implement/test artifacts.

# Clarifications / superseding decisions

- I found no explicit raw-log clarification entry that changed user intent after the initial request snapshot.
- Later decisions narrowed execution details without reducing scope:
  - `decisions.txt` block 1 and block 3 keep `subprocess.run(...)` allowed only for explicit CLI probing and scope strictness to provider `run_turn` execution rather than repo-wide subprocess usage.
  - `decisions.txt` block 2 preserves the public non-parallel API contract and requires `Engine.run(...)` and `BranchGroupRuntime.run(...)` to remain outer sync wrappers only.
  - `decisions.txt` block 4 records the strictness follow-up that fixed direct-import detection for `ThreadPoolExecutor`, `Future`, and `FIRST_COMPLETED`.

# Implemented behavior

- Duplicate branch final-state mutation was removed. `autoloop/core/branch_groups/runtime.py` now builds branch result payloads observationally in `_branch_result_from_step_result(...)` and does not perform manual final-state updates there. `tests/unit/test_branch_group_context_sessions.py` verifies the produce/verify `needs_rework` case does not double-increment `rework_count`.
- Failed branch result construction now snapshots provider session metadata once in `_failed_branch_result(...)`. `tests/unit/test_branch_group_context_sessions.py` verifies the snapshot helper is called exactly once and that `provider_session` and `provider_sessions` stay consistent.
- `BranchSessionStoreView` is branch-local only. `autoloop/core/branch_groups/sessions.py` now resolves `get(...)`, `open(...)`, and `snapshot(...)` from branch-local bindings/active keys only, and fresh branch bindings start with `session_id=None`. `tests/unit/test_branch_group_context_sessions.py` and `tests/contract/test_branch_group_runtime.py` cover no parent-session fallback, first branch request receiving `session_id=None`, distinct branch-local fresh keys, unchanged parent active session state, and manifests that omit parent provider session ids.
- Scoped branch runtime handling is now assertion-only instead of partial runtime support. `autoloop/core/branch_groups/runtime.py` raises on `compiled_step.scope_name is not None`, and `tests/contract/test_branch_group_runtime.py` covers the defensive runtime assertion while `tests/unit/test_simple_surface.py` covers compile-time rejection paths.
- The retained sync operation bridge is contained to public non-parallel compatibility. `autoloop/core/providers/rendered.py` keeps the bridge only in `_run_operation_turn(...)` with an explicit comment that provider-backed branches, prompt steps, produce/verify steps, and provider-backed fan-in remain on async transport paths. Existing async-provider validation in `autoloop/core/providers/protocols.py`, `tests/unit/test_provider_boundary_core.py`, and `tests/contract/test_async_engine_spine.py` continues to enforce async-native provider/transport behavior.
- Provider turn execution remains async subprocess based. `autoloop/runtime/providers/codex.py` and `autoloop/runtime/providers/claude.py` use `asyncio.create_subprocess_exec(...)` in `run_turn(...)`, while capability probing still uses `subprocess.run(...)` outside provider turn execution. `tests/runtime/test_runtime_providers.py` and `tests/strictness/test_no_compat.py` cover both transports, forbid provider-turn fallback to `subprocess.run(...)`, and now also catch direct-import thread-backed primitives inside `run_turn(...)`.
- Capture-only branch semantics, single fan-in finalization, deterministic branch evidence, and evidence-write gating remain covered in `tests/contract/test_branch_group_runtime.py`, including captured `Goto`/`Fail`/`RequestInput`, suppressed branch `on_taken`, single fan-in `on_taken`, same-file writes, shared state/value visibility, manifest ordering, deterministic context output, and stopping before fan-in when `results.json` or `context.md` writes fail.
- Validation artifacts report focused test success rather than a full-repo sweep:
  - `artifacts/test/phases/async-branch-group-cleanup/feedback.md` records `115 passed` across the targeted branch-group/runtime/provider/strictness suites and `7 passed` for the explicit simple-surface compile-time checks.
  - `artifacts/implement/phases/async-branch-group-cleanup/feedback.md` records the strictness follow-up closure with `36 passed` on the strictness subset after the direct-import scanner fix.

# Unresolved gaps

- No material unresolved gaps found.
- I did not find requested behavior that is absent, contradicted, or insufficiently tested without later justification.
- The only notable limitation is that validation stayed intentionally targeted rather than full-suite, but the request required the compile/runtime/provider/strictness matrix, not a repository-wide test sweep.

# Differences justified by later clarification or analysis

- `subprocess.run(...)` was not banned globally. That is consistent with request sections 8 and 17 and was made explicit in `decisions.txt`: provider turn execution is strict, capability probing is allowed.
- The sync operation bridge was not removed entirely. That is consistent with request sections 2 and 7, which preserve the public non-parallel API while forbidding that bridge from leaking into branch/provider execution.
- The run used focused regression suites instead of the full repository suite. That matches the request’s narrow cleanup scope and the run-local test strategy, which concentrated on the changed branch-group, provider, and strictness surfaces.

# Recommended next run

- No follow-up implementation run is required for this request.
- If additional confidence is desired later, a separate non-blocking validation pass could run a wider repository suite, but that is outside the minimal follow-up needed here.
