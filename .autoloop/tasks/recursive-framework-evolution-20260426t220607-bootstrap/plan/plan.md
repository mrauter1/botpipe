# Workflow Optimization Process Plan

## Outcome

Implement `workflow_run_traces_to_optimization_candidates` as a bundled, authoring-only workflow that consumes completed run observability bundles and publishes optimization candidate artifacts plus `workflow_refinement_evidence.json`. The workflow must not change runtime execution semantics, must not mutate the selected workflow source package, must not run the target workflow implicitly, and must not execute ablations.

## Existing seams to reuse

- Workflow discovery is manifest-backed through `workflow.toml` package discovery; registration work should follow the current package-and-docs pattern instead of introducing a new runtime registry.
- Selected-workflow snapshots already exist for capability, authoring surface, and decomposition surface via `stdlib/adaptation.py`, `stdlib/refinement.py`, and `stdlib/decomposition.py`; the optimizer should reuse those helpers and add only optimizer-specific artifacts.
- Run-history diagnostics already prove the pattern for a deterministic capture step plus LLM pair steps and publish-time validation in `workflows/workflow_run_history_to_failure_modes/`.
- Refinement already proves the pattern for source-surface immutability, candidate-only publication, and evidence handoff in `workflows/workflow_and_eval_to_refined_workflow_package/`.

## Implementation shape

### New stdlib seam

- Add `stdlib/optimization.py` as a deterministic helper module only.
- Scope:
- parse and validate `run_refs`
- discover runs for `selected_workflow` when `run_refs` is empty
- load and validate required Plan-1 observability files
- normalize trace corpus and excluded-run reporting
- compute step metrics, static centrality, deterministic ranking inputs, and failure seeds
- write and validate selected-workflow source manifests
- write optimizer-specific refinement evidence
- Avoid LLM calls, runtime control changes, or hidden workflow execution.

### New workflow package

- Add `workflows/workflow_run_traces_to_optimization_candidates/` with `__init__.py`, `workflow.py`, `contracts.py`, `params.py`, `workflow.toml`, `assets/optimization_package_checklist.md`, and the full `prompts/` set from the request snapshot.
- Model the package after the existing diagnostics/refinement workflow style:
- typed `State`
- deterministic bootstrap/frame/package system steps
- pair steps for ranking, failure mining, producer optimization, verifier/rubric optimization, token optimization, adversarial cases, workflow-level optimization, and packaging
- explicit route contracts and ordered-prefix `pairs` subset enforcement

### Integration updates

- Expose the new stdlib exports from `stdlib/__init__.py`.
- Ensure package discovery finds the workflow via the new manifest and package directory.
- Extend `workflow_and_eval_to_refined_workflow_package` to accept optimization evidence kinds without treating candidate artifacts as proof of improvement.
- Update workflow docs, architecture/authoring docs, and architecture baseline assertions to freeze the new boundaries.

## Interfaces and contracts

### Parameters

- Required:
- `selected_workflow: str`
- `task_title: str`
- Optional:
- `run_refs: list[str] = []`
- `run_statuses: list[str] = ["failed", "paused", "blocked"]`
- `route_tags: list[str] = ["needs_rework", "needs_replan", "failed", "blocked"]`
- `history_limit: int = 25`
- `top_k_steps: int = 1`
- `optimization_depth: Literal["cheap", "standard", "ablation"] = "cheap"`
- `include_adversarial_generation: bool = True`
- `include_token_optimization: bool = True`
- `include_workflow_level_candidates: bool = True`
- `max_failure_scenarios: int = 25`
- `max_candidates_per_pass: int = 3`
- `focus: str | None = None`
- `sponsor_role: str | None = None`
- `desired_outcome: str | None = None`
- `constraints: list[str] = []`
- Validation must enforce the request snapshot exactly, especially `run_refs` shape, uniqueness of `run_statuses` and `route_tags`, positive ints, and non-empty normalized constraints.

### Deterministic data contracts

- `contracts.py` should define strict top-level payloads for:
- scope
- excluded runs
- trace corpus
- step metrics
- priority report
- failure scenarios
- producer candidates
- verifier/rubric candidates
- token candidates
- adversarial cases
- workflow-level candidates
- scorecard
- optimization refinement evidence
- Publish-step validation should stay strict on artifact structure and boundary invariants, while leaving narrative rationale fields loosely typed.

### Artifact boundaries

- All optimizer artifacts live under the optimizer workflow folder only.
- The selected workflow package remains read-only.
- `selected_workflow_source_manifest.json` is captured at frame time and recomputed at package time; any diff is a terminal failure.
- Historical runs missing any of `run.json`, `trace.jsonl`, `git_tracking.jsonl`, `static_step_graph.json`, or `raw/` are excluded with reason, not treated as workflow failure.

## Milestones

### 1. Deterministic ingestion and workflow shell

- Add `stdlib/optimization.py`.
- Add `params.py`, `contracts.py`, workflow package files, prompt README, checklist, and `workflow.toml`.
- Export stdlib helpers and make the new package discoverable.
- Implement bootstrap/frame logic, selected-workflow snapshots, source manifest capture, run discovery, eligibility filtering, excluded-run reporting, and no-op packaging for zero eligible runs.

### 2. Ranking and failure analysis

- Implement static centrality, step metrics, deterministic scoring, and top-k ranking support.
- Implement `rank_targets` and `mine_failures` around the deterministic corpus and metrics.
- Preserve the distinction between highest failure count and highest leverage upstream target.

### 3. Candidate generation and publication

- Implement `optimize_producer`, `optimize_verifier_rubric`, `optimize_tokens`, `adversarial_cases`, `workflow_level`, and `package`.
- Enforce skip behavior for disabled optional passes.
- Ensure `optimization_depth="ablation"` only changes labeling and optional planning fields; no ablation execution.
- Publish scorecard, refinement evidence, packet, and receipt only after the source manifest re-check passes.

### 4. Refinement integration and docs

- Extend refinement evidence acceptance in `workflow_and_eval_to_refined_workflow_package`.
- Update refinement prompts/docs to treat optimization candidates as candidate-only evidence and ablation results as stronger evidence when present.
- Add `docs/workflows/workflow_run_traces_to_optimization_candidates.md`.
- Update `docs/architecture.md`, `docs/authoring.md`, `docs/workflows/workflow_and_eval_to_refined_workflow_package.md`, `docs/workflows/workflow_to_eval_suite.md`, and `docs/workflows/workflow_run_history_to_failure_modes.md`.

### 5. Test coverage and validation

- Add unit tests for `stdlib/optimization.py`.
- Add runtime workflow tests for registration, describe output, frame/ranking/failure/candidate/package behavior, ordered-prefix pair subsets, skip routes, non-mutation guarantee, and ablation-depth non-execution.
- Extend refinement integration tests and architecture baseline docs assertions.
- Finish with targeted suites first, then the full test suite.

## Compatibility and regression controls

- Preserve runtime-owned observability and replay semantics; the optimizer only reads run artifacts.
- Preserve `workflow.toml` as metadata-only; do not move topology, routing, or optimization policy into manifests.
- Preserve selected-workflow helper separation; do not merge capability, authoring, decomposition, and optimization-specific source-manifest concerns into one serializer.
- Preserve refinement workflow boundaries; accepting optimization evidence must not auto-materialize adversarial cases or treat candidate estimates as proven improvements.
- Prefer reuse of `runtime.workspace.list_run_records` or equivalent safe filesystem helpers when possible, but keep optimizer ingestion at the filesystem/artifact layer rather than adding runtime-owned optimization APIs.

## Validation approach

- `phase_plan.yaml` phases align to shippable slices and dependency order.
- Each workflow step should have deterministic publish-side assertions for workflow identity alignment, artifact presence, schema conformance, allowed route behavior, and non-mutation guarantees.
- Ranking helpers should be unit-tested against seeded upstream/downstream symptom cases.
- Source-manifest tests should prove both stable pass and mutation detection.
- Runtime tests should cover both happy-path and zero-eligible-run/no-op behavior.

## Risk register

| Risk | Why it matters | Control |
| --- | --- | --- |
| Duplicate selected-workflow serializers | Would fragment artifact meaning and drift validation behavior | Reuse existing capability/authoring/decomposition helpers and keep optimizer-specific logic limited to source manifests and optimization artifacts |
| Accidental runtime coupling | Could turn optimizer logic into hidden engine behavior | Keep all optimization behavior in `stdlib/optimization.py` plus the workflow package; no runner or engine semantics changes |
| Misclassification of old runs as failures | Historical missing observability is expected | Exclude with deterministic reason codes and publish a no-op packet when no eligible runs remain |
| Ranking downstream symptoms over upstream causes | Would optimize the wrong step and waste follow-on work | Combine deterministic metrics, static centrality, and explicit LLM attribution rules that must justify upstream/downstream adjustments |
| Silent selected-workflow mutation | Would violate the main non-mutation boundary | Hash full selected workflow package surfaces at frame and package steps and fail publication on any drift |
| Candidate evidence overclaimed as proof | Would contaminate refinement and promotion decisions | Keep scorecard language candidate-only, forbid rerun/ablation claims without evidence, and update refinement docs/tests accordingly |

## Rollback / fallback

- If implementation risk clusters late, land deterministic ingestion, manifest validation, and no-op/package scaffolding first, then add candidate-generation passes incrementally.
- If refinement integration reveals incompatible evidence expectations, keep optimizer publication self-contained and widen refinement evidence acceptance in a separate, tightly scoped slice within the same change set before enabling any new evidence kind in docs/tests.
