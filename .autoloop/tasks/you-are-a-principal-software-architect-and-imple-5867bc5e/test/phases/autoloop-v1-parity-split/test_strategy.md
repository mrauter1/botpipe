# Test Strategy

- Task ID: you-are-a-principal-software-architect-and-imple-5867bc5e
- Pair: test
- Phase ID: autoloop-v1-parity-split
- Phase Directory Key: autoloop-v1-parity-split
- Phase Title: Replace The Support Mini-Runtime With Workflow-Owned Parity Modules
- Scope: phase-local producer artifact

## Coverage Map

- `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
  - Source-shape coverage for deleting `autoloop_v1_support.py`
  - Confirms `autoloop_v1.py` inlines `parse_phase_ids(...)` and explicit `Artifact(...)` templates
  - Confirms parity modules delegate session payload persistence to runtime-store helpers
  - Preserves generic runtime workspace neutrality and absence of phase-owned filesystem artifacts in generic workspaces
- `autoloop_v3/tests/runtime/test_workflow_integration_parity.py`
  - Happy path for `run_autoloop_v1(...)` with raw logs, decisions file, phase events, and legacy session filenames
  - Resume path for clarification persistence and cycle/attempt reuse
  - Failure paths for blocked and failed terminal-status mapping
  - Strict-workflow coverage for `Ralph_loop.py` reflected success and direct `goal_met` success
  - Edge case for unsafe phase ids preserving exact legacy `_pid-...` artifact/session naming
- `autoloop_v3/tests/contract/test_engine_contracts.py`
  - Preserved invariants for generic observer purity, explicit sessions, and optional/required handler rules
- `autoloop_v3/tests/test_architecture_baseline_docs.py`
  - Docs freeze for the split parity/conventions module names and the no-compat-layer architecture story

## Preserved Invariants Checked

- No provider wrapper or engine subclass is needed for parity behavior
- Generic runtime remains workflow-agnostic and phase-unaware
- Legacy `plan.json` and `sessions/phases/{phase}.json` filenames remain intact
- `phase_started` / `phase_completed` are still derived correctly from the observer-driven parity harness
- `Ralph_loop.py` leaves `goal_met=True` on both success paths

## Edge Cases

- Unsafe phase id requiring exact `_pid-...` encoding
- Clarification resume reusing the paused question cycle/attempt
- Blocked pause vs failed terminal mapping

## Failure Paths

- Generic runtime resume without checkpoint remains rejected elsewhere in runtime tests
- Parity harness failed and blocked terminals keep legacy-readable `run_finished.status`

## Flake Controls

- All tests use `ScriptedLLMProvider` and temporary filesystems only
- Assertions rely on deterministic file contents and ordered JSONL events, not timestamps

## Known Gaps

- Resume-time cycle/attempt recovery is covered through persisted log output, not by directly unit-testing the private raw-log parser helper
