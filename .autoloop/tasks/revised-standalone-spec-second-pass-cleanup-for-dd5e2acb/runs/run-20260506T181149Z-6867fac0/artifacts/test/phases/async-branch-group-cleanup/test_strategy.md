# Test Strategy

- Task ID: revised-standalone-spec-second-pass-cleanup-for-dd5e2acb
- Pair: test
- Phase ID: async-branch-group-cleanup
- Phase Directory Key: async-branch-group-cleanup
- Phase Title: Async Branch-Group Cleanup
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 branch result construction is observational only:
  `tests/unit/test_branch_group_context_sessions.py` covers failed-branch provider session snapshot single-read behavior, and `tests/contract/test_branch_group_runtime.py` covers produce/verify branch outcomes plus manifest session metadata stability.
- AC-2 branch session isolation is branch-local only:
  `tests/unit/test_branch_group_context_sessions.py` covers default `get()` not falling back to a parent active session, fresh branch bindings starting at `session_id=None`, distinct branch-local fresh keys, branch-local snapshots, and hook snapshot/restore staying isolated from the parent store.
  `tests/contract/test_branch_group_runtime.py` covers provider-backed fresh branches receiving `session_id=None`, parent active session state remaining unchanged, and manifests omitting parent provider session ids unless the provider returns a real branch id.
- AC-3 scoped/worklist branch runtime remains rejected or assertion-only:
  `tests/unit/test_simple_surface.py` covers compile-time rejection for scoped, child-workflow, and operation branch/fan-in shapes, and `tests/contract/test_branch_group_runtime.py` covers defensive runtime assertion for manually scoped compiled branches.
- AC-4 preserved branch-group behavior remains green:
  `tests/contract/test_branch_group_runtime.py` covers composite question routing without fan-in, same-file branch writes, shared state/value visibility, manifest declaration ordering, deterministic context markdown, evidence under `workflow_folder/_branch_groups`, and evidence-write failure preventing fan-in.
- AC-5 capture-mode and fan-in finalization semantics remain exact-once:
  `tests/contract/test_branch_group_runtime.py` covers captured `Goto`, `RequestInput`, and `Fail` controls without destination following, branch `on_taken` suppression in capture mode, and fan-in `on_taken`/artifact/transition behavior finalizing once at the composite boundary.
- AC-6 provider execution stays async-native and strictness stays scoped:
  `tests/runtime/test_runtime_providers.py` covers async provider entrypoints awaiting transport and provider-backed branch execution not reaching `run_operation(...)`.
  `tests/strictness/test_no_compat.py` covers `asyncio.create_subprocess_exec(...)` transport use, `subprocess.run(...)` prohibition inside `run_turn`, allowed CLI probing outside `run_turn`, and forbidden direct-import executor primitives in `run_turn`.
- AC-7 public sync wrappers remain outer wrappers only:
  existing contract and strictness coverage continues to validate the async engine/provider path without reintroducing sync-provider or thread-backed fallbacks.

## Edge cases and failure paths

- Branch session lookup is asserted before any branch-local binding exists so a regression to parent active-session fallback fails even if fresh-session tests still pass.
- Failed-branch metadata capture is exercised separately from successful manifests to catch mutable-session-store reread bugs.
- Strictness probes use minimal synthetic provider modules to keep direct-import/thread-fallback detection deterministic and independent of external CLIs.

## Known gaps

- I ran focused regression suites only, not the full repository test suite.
- No timing-stress or cancellation-fuzz coverage was added beyond the deterministic async branch cases already present in the contract tests.
