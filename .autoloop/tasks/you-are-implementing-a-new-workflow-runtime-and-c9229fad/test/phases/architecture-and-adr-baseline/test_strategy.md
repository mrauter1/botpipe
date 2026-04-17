# Test Strategy

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: test
- Phase ID: architecture-and-adr-baseline
- Phase Directory Key: architecture-and-adr-baseline
- Phase Title: Architecture Baseline
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- ADR inventory completeness
  - Coverage: assert the exact 14 required ADR files exist under `autoloop_v3/docs/adr/`.
  - Preserved invariant: phase completion cannot regress to a topic list or partial ADR set.
- ADR structure contract
  - Coverage: assert each ADR has exactly three candidate sections and all mandated evaluation fields.
  - Edge case: prevent an ADR from silently dropping one candidate or an evaluation category.
- Frozen public authoring surface
  - Coverage: assert architecture or authoring docs still name the required exported symbols for `workflow` and `workflow.primitives`.
  - Preserved invariant: import ergonomics and public contracts remain explicit before implementation.
- Concrete legacy parity coverage
  - Coverage: assert the docs still mention the required legacy behaviors and compatibility risks from `autoloop_v1.py`, `Ralph_loop.py`, and the old runtime.
  - Edge cases: phase-scoped sessions, phase-local artifacts, `thread_id` session compatibility, `on_verdict`, `SessionLifecycle.ON_START`, produced-artifact attribute access, config discovery, and loader-safe annotation handling.
- Risk inventory coverage
  - Coverage: assert the docs still capture the loader and resume risks plus phase-local session scoping risk.
  - Failure path: catch future edits that remove the risk register or weaken the documented parity obligations.

## Determinism And Flake Control

- Tests are pure filesystem reads over committed docs.
- No network, time, subprocess, or nondeterministic ordering is involved.
- Assertions target required symbols and behavior markers instead of large prose snapshots to avoid churn from harmless wording edits.

## Known Gaps

- No runtime or engine behavior tests are added in this phase because the phase output is documentation and ADRs, not executable runtime code.
- End-to-end parity and provider behavior remain deferred to later phases with actual implementation.
