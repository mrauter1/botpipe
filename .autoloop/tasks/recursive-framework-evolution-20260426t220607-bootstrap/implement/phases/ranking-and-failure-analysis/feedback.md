# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260426t220607-bootstrap
- Pair: implement
- Phase ID: ranking-and-failure-analysis
- Phase Directory Key: ranking-and-failure-analysis
- Phase Title: Ranking And Failure Analysis
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `stdlib/optimization.py:255-267`, `build_step_trace_metrics()`, `rank_optimization_targets()`
  The deterministic ranking path only ever sees `trace_corpus.step_observations`, and those observations are filtered by `route_tags` inside `normalize_trace_corpus()`. With the default `route_tags` (`needs_rework`, `needs_replan`, `failed`, `blocked`), any upstream step that locally passed but caused a downstream failure is removed before metrics/ranking run. Concrete failure scenario: `assessment` routes `assessment_complete`, `package` later routes `failed`; the optimizer cannot rank `assessment` even if static centrality and downstream blast radius make it the highest-leverage target, which breaks AC-2 and the request’s upstream-attribution requirement. Minimal fix: keep an unfiltered internal observation set for deterministic ranking/upstream attribution while continuing to publish the filtered `step_observations` artifact required by the earlier phase decision.

- IMP-002 | blocking | `workflows/workflow_run_traces_to_optimization_candidates/workflow.py:603-652`, `_optimization_evidence_entries()` at `workflow.py:843-869`
  `workflow_failure_scenarios.json` is now generated during `capture_frame_context` and later included in publication evidence whenever packaging runs, regardless of whether `rank_targets` chose `insufficient_evidence`. That creates a concrete contradiction in the required control flow: the workflow can short-circuit to `package` because ranking evidence is too thin, yet still publish a failure-scenario artifact and refinement-evidence entry that imply failure mining happened. Minimal fix: only materialize or publish `workflow_failure_scenarios.json` after `targets_ranked` succeeds, or gate publication/evidence-entry inclusion on the recorded `ranking_status` / `failure_status` so the `insufficient_evidence` short-circuit remains truthful.

- Review cycle 2: verified `IMP-001` and `IMP-002` are resolved. No remaining findings in this phase scope after rechecking the live code paths and rerunning `./.venv/bin/python -m pytest -q tests/unit/test_optimization_helpers.py tests/runtime/test_workflow_run_traces_to_optimization_candidates.py` (`29 passed`).
