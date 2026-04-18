# Test Strategy

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: test
- Phase ID: workflow-migrations-and-parity-harness
- Phase Directory Key: workflow-migrations-and-parity-harness
- Phase Title: Migrate Workflows And Parity Harnesses
- Scope: phase-local producer artifact

## Behavior Coverage Map
- `autoloop_v1.py` generic runtime happy path: assert explicit workflow-declared session filenames (`plan.json`, `phases/<phase>.json`), explicit prompt resolution, and phase artifact writes.
- `run_autoloop_v1(...)` parity happy path: assert legacy workspace logs, phase events, session sharing, and legacy-readable terminal status remain intact.
- `run_autoloop_v1(...)` parity edge cases: assert unsafe phase ids keep exact `_pid-...` directory/session encoding and clarification resume preserves decisions/raw-log/session-note parity.
- `run_autoloop_v1(...)` failure paths: assert blocked and failed outcomes preserve legacy terminal status mapping; assert workflows missing `SessionPaths(...)` fail before creating any `.autoloop/tasks/<task_id>` state.
- `Ralph_loop.py` success routes: assert `goal_met=True` for both `reflect -> SUCCESS` and direct `plan_action -> SUCCESS`, while keeping strict session and action-log behavior.
- Generic runtime neutrality: keep the unrelated toy/custom session-path workflow coverage so session-path declarations remain generic rather than Autoloop-specific.

## Preserved Invariants Checked
- Runtime stays phase-agnostic while Autoloop-v1 exact filenames remain workflow-owned.
- The parity harness remains a thin composition root over shared runtime services plus workflow-owned parity logging/persistence.
- No ambient cwd prompt fallback is required for the migrated workflows.

## Stabilization
- All coverage is deterministic: `tmp_path` for isolated workspace state and `ScriptedLLMProvider` for fixed provider turns.
- No timing, network, subprocess, or nondeterministic ordering dependencies are introduced in the added coverage.

## Known Gaps
- This phase does not add git-extension-specific parity tests because git policy wiring is out of scope for the migrated workflow changes covered here.
