# Standalone Fix Plan: `workflow_run_traces_to_optimization_candidates`

## Intent Contract

Implement the request snapshot as written and keep the patch scoped to optimizer workflow semantics, contracts, prompts, docs, tests, and `report.md`.

Must preserve:
- No runtime git-tracking changes.
- No runtime tracing changes.
- No provider execution or engine execution changes.
- No `commit_after_run` changes.
- No target-workflow reruns, ablation execution, refinement execution, or source mutation.

## Current Repo Findings

- `on_capture_frame_context` currently writes deterministic `workflow_failure_scenarios.json` during frame preparation.
- `on_mine_failures` currently rewrites `workflow_failure_scenarios.json` unconditionally after the pair outcome, which violates LLM artifact ownership.
- Optional skip routes already synthesize empty token, adversarial, and workflow-level artifacts when disabled; those paths need preservation, not redesign.
- `stdlib/optimization.py` already exposes `FAILURE_SCENARIO_SEEDS_SCHEMA` and `extract_failure_scenario_seeds`, but the helper payload currently uses `failure_scenario_seeds` instead of the requested `seeds` publication surface.
- `WorkflowOptimizationScopeArtifactPayload` currently omits `max_candidates_per_pass` even though `workflow.py` writes that field and the request requires it to stay present in `workflow_optimization_scope.json`.
- `workflow_optimization_scorecard.json` validation currently checks candidate counts and ablation promotion state, but it does not require `optimization_depth` or `ablation_executed`.
- Prompt and docs surfaces currently lack explicit ownership language for accepted LLM artifacts, depth semantics, and soft-budget guidance for `max_candidates_per_pass`.
- Existing tests still assert deterministic failure scenarios in the final failure artifact and must be realigned to the new seed/final split.

## Milestones

### 1. Workflow Semantics And Contracts

- Add `workflow_failure_scenario_seeds.json` as the deterministic artifact and keep `workflow_failure_scenarios.json` as the provider-authored final artifact.
- Update contracts for the new seed artifact and require scorecard `optimization_depth` plus `ablation_executed`.
- Make `workflow_optimization_scope.json` a first-class public contract for both `optimization_depth` and `max_candidates_per_pass`, including contract-model alignment so the field is preserved intentionally rather than as an undocumented extra.
- Refactor failure-mining flow so accepted provider output is validated and preserved, `no_failure_scenarios` can synthesize only the minimal empty fallback when absent, and `needs_rework` or `failed` never overwrite the provider artifact.
- Audit candidate-pass handlers so accepted provider-authored candidate artifacts are validated and counted without deterministic regeneration, truncation, or formatting rewrites.
- Keep not-applicable routes limited to writing minimal empty artifacts only when the corresponding artifact is absent.
- Update package/publication logic so scorecard, packet, and receipt record depth semantics, `ablation_executed: false`, and `requires_ablation_before_promotion` derived from validated candidate artifacts.

### 2. Prompt, Docs, And Report Alignment

- Update producer prompts to read `workflow_optimization_scope.json`, apply `optimization_depth`, and treat `max_candidates_per_pass` as soft guidance only.
- Update verifier prompts so over-budget candidate count is a focus concern rather than a hard rejection reason, and so verifier language explicitly rejects hidden execution or invalid ownership behavior.
- Revise prompt README and workflow docs to codify deterministic seed ownership, validation-only handling of accepted LLM artifacts, prompt-only depth semantics, and prompt-only candidate budgets.
- Replace the placeholder `report.md` with a real implementation report that captures scope, preserved boundaries, changed files, and executed test commands.

### 3. Regression Tests And Verification

- Replace tests that assume deterministic final failure-scenario rewrites with coverage for preserved provider-authored artifacts, empty fallback behavior, malformed accepted artifacts failing validation, and separate seed/final artifacts.
- Add runtime coverage for `optimization_depth` recording in scope, scorecard, packet, and receipt without creating reruns or ablation workflow runs.
- Add coverage proving `max_candidates_per_pass` remains prompt guidance only and does not cause schema or publication rejection by count alone.
- Add coverage that `workflow_optimization_scope.json` explicitly retains `max_candidates_per_pass` and that contracts, docs, and prompts stay aligned on that field’s soft-budget meaning.
- Keep package publication validation coverage for selected-workflow alignment, candidate-count accounting, and ablation promotion summary.
- Run the required targeted pytest commands, then run full `pytest` if feasible.

## Interfaces And Contract Changes

- New deterministic artifact: `workflow_failure_scenario_seeds.json`.
- Seed schema contract: top-level `schema`, `selected_workflow`, and `seeds`; per-seed fields remain permissive to avoid locking helper evolution too tightly.
- Scope contract change: `workflow_optimization_scope.json` must explicitly model and preserve `max_candidates_per_pass` as a published field, while still treating it as soft authoring guidance rather than a validation cap.
- Final failure artifact remains `workflow_failure_scenarios.json`; accepted routes validate file existence, JSON object shape, schema value, selected workflow, and `failure_scenarios` list without requiring evidence-reference minima.
- Scorecard contract change: `optimization_depth` is required with values `cheap|standard|ablation`; `ablation_executed` is required and must be `false`.
- Candidate contracts remain intentionally uncapped by schema; no max-length validation tied to `max_candidates_per_pass`.
- Packet contract change: include deterministic Optimization Depth section, and append it in package logic if the producer packet omits it.

## Compatibility Notes

- Persisted optimizer outputs gain one additive deterministic artifact, two required scorecard fields, and an explicitly modeled scope field for `max_candidates_per_pass`; tests and any in-repo consumers must be updated in the same patch.
- Final failure artifact filename and candidate artifact filenames stay unchanged, so downstream workflow handoff paths remain stable.
- No migration is required for historical runtime bundles because the change is isolated to optimizer-owned artifacts generated in new runs.

## Regression Controls

- Preserve all selected-workflow alignment checks and source-manifest immutability checks already enforced by package publication.
- Keep deterministic ranking inputs authoritative: `workflow_optimization_trace_corpus.json`, `step_trace_metrics.json`, and `step_optimization_priority_report.json` stay deterministic.
- Keep `workflow_optimization_scope.json` internally and publicly consistent with prompt behavior by modeling `max_candidates_per_pass` in the contract instead of relying on unmodeled extras.
- Treat invalid accepted provider artifacts the same way as other invalid output artifacts: fail validation rather than silently replacing content.
- Preserve no-op publication behavior when no eligible Plan-1 observability bundles exist.
- Avoid new generic helpers unless they clearly centralize repeated artifact validation or empty-fallback behavior already duplicated across handlers.

## Validation Plan

- `pytest tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
- `pytest tests/unit/test_optimization_helpers.py`
- `pytest tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `pytest tests/test_architecture_baseline_docs.py`
- `pytest`

## Risk Register

- Risk: changing helper payload shape in `stdlib/optimization.py` could break unit tests or any optimizer code that still expects `failure_scenario_seeds`.
  Control: prefer adapting the workflow-local write surface or updating the helper plus all local tests in one patch, with no broader runtime behavior changes.
- Risk: leaving `max_candidates_per_pass` out of the scope contract would create a prompt/docs/tests mismatch around a persisted public artifact.
  Control: update the scope model, scope-writing logic if needed, and scope assertions together so the field is explicit and intentionally soft-budget only.
- Risk: package validation could start rejecting existing fixtures if scorecard required fields are added incompletely.
  Control: update every scorecard fixture/helper in runtime tests together with the contract change.
- Risk: prompt/doc edits could drift from implemented semantics.
  Control: align prompt README, step prompts, workflow docs, and `report.md` to the same ownership/depth/budget language in the same phase.
- Risk: deterministic empty-artifact synthesis could accidentally overwrite provider-authored artifacts on skip routes.
  Control: gate every fallback write on artifact absence and validate existing artifacts in place.

## Rollback

- Revert only optimizer workflow, optimizer contracts, optimizer prompts/docs/tests, and `report.md` changes from this patch if regression appears.
- Do not roll back runtime observability, git tracking, or `commit_after_run` code because they are explicitly out of scope.
