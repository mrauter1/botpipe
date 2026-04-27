# Test Strategy

- Task ID: recursive-framework-evolution-20260426t220607-bootstrap
- Pair: test
- Phase ID: ranking-and-failure-analysis
- Phase Directory Key: ranking-and-failure-analysis
- Phase Title: Ranking And Failure Analysis
- Scope: phase-local producer artifact

- Behaviors covered:
  - `normalize_trace_corpus()` preserves run-level eligibility while filtering published `step_observations` by `route_tags`.
  - Deterministic ranking still sees upstream locally accepted steps through the internal observation set and can rank them over downstream symptoms.
  - `capture_frame_context` writes a schema-clean public trace corpus, preserves the internal corpus for analysis, and emits deterministic metrics and priority artifacts.
  - `on_mine_failures()` rewrites `workflow_failure_scenarios.json` from deterministic seeds and ranked targets.
  - `insufficient_evidence -> package` does not publish `workflow_failure_scenarios` as refinement evidence.
- Preserved invariants checked:
  - `run_statuses` remain run-level selection only.
  - Public optimizer artifacts stay route-filtered and do not leak internal analysis fields.
  - Phase topology and short-circuit route names remain unchanged in workflow describe/runtime tests.
- Edge cases:
  - Eligible run with no matching `route_tags`.
  - Upstream pass followed by downstream failure under `route_tags=["failed"]`.
  - Historical run missing Plan-1 observability files.
- Failure paths:
  - No eligible runs produce the no-op packet path.
  - Thin ranking evidence short-circuits packaging without publishing mined-failure evidence.
- Flake risks / stabilization:
  - Tests use local fake providers, file-backed seeded runs, and deterministic JSON fixtures only; no network, timing, or nondeterministic ordering dependencies.
- Known gaps:
  - This phase does not extend into later candidate-generation passes, full refinement publication, or full-suite execution.
