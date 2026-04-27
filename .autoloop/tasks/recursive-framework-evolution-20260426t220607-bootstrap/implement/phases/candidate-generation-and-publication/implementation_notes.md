# Implementation Notes

- Task ID: recursive-framework-evolution-20260426t220607-bootstrap
- Pair: implement
- Phase ID: candidate-generation-and-publication
- Phase Directory Key: candidate-generation-and-publication
- Phase Title: Candidate Generation And Publication
- Scope: phase-local producer artifact

## Files changed

- `workflows/workflow_run_traces_to_optimization_candidates/contracts.py`
- `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`
- `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
- `.autoloop/tasks/recursive-framework-evolution-20260426t220607-bootstrap/decisions.txt`
- `.autoloop/tasks/recursive-framework-evolution-20260426t220607-bootstrap/implement/phases/candidate-generation-and-publication/implementation_notes.md`

## Symbols touched

- `WorkflowRunTracesToOptimizationCandidates`
- `WorkflowRunTracesToOptimizationCandidates.on_route_optimize_tokens`
- `WorkflowRunTracesToOptimizationCandidates.on_route_adversarial_cases`
- `WorkflowRunTracesToOptimizationCandidates.on_route_workflow_level`
- `WorkflowRunTracesToOptimizationCandidates.on_publish_optimization_packet`
- `ProducerPromptOptimizationCandidatesArtifactPayload`
- `VerifierRubricOptimizationCandidatesArtifactPayload`
- `TokenOptimizationCandidatesArtifactPayload`
- `AdversarialCaseCandidatesArtifactPayload`
- `WorkflowLevelOptimizationCandidatesArtifactPayload`
- `PRODUCER_PROMPT_OPTIMIZATION_CANDIDATES_ARTIFACT`
- `VERIFIER_RUBRIC_OPTIMIZATION_CANDIDATES_ARTIFACT`
- `TOKEN_OPTIMIZATION_CANDIDATES_ARTIFACT`
- `ADVERSARIAL_CASE_CANDIDATES_ARTIFACT`
- `WORKFLOW_LEVEL_OPTIMIZATION_CANDIDATES_ARTIFACT`
- `_validate_candidate_artifact_publication_surface`
- `_read_candidate_publication_surface`

## Checklist mapping

- Item 10-14: enforced optional-pass short-circuit behavior with explicit gated routes for token, adversarial, and workflow-level passes.
- Item 15: hardened package publication with candidate-artifact schema validation plus scorecard/candidate consistency checks.
- Item 19: added runtime coverage for ordered-prefix pair topology, skip semantics, malformed candidate rejection, package publication, source-drift failure, scorecard mismatch rejection, and ablation-depth non-execution.
- Item 22: reran the scoped optimizer helper/runtime/refinement/docs proof set.

## Assumptions

- Existing frame, ranking, failure-mining, and refinement-evidence behavior from earlier phases remains authoritative unless directly constrained by reviewer findings.
- The package-time publication gate is the correct place to enforce scorecard-to-candidate consistency because all candidate artifacts are available there.

## Preserved invariants

- The optimizer remains candidate-only and does not rerun target workflows, execute ablations, mutate selected-workflow source, or invoke refinement automatically.
- Pair-step order remains the ordered prefix from the request snapshot: `frame`, `rank_targets`, `mine_failures`, `optimize_producer`, `optimize_verifier_rubric`, `optimize_tokens`, `adversarial_cases`, `workflow_level`, `package`.
- Disabled optional passes now short-circuit deterministically without changing enabled-pass behavior.

## Intended behavior changes

- Optional pass flags now route through explicit system gates that publish canonical empty candidate artifacts and emit `token_pass_not_applicable`, `adversarial_generation_skipped`, or `workflow_level_pass_not_applicable` without relying on provider output.
- Candidate JSON artifacts are now schema-validated both when produced and again at package publication, and package publication rejects scorecards that contradict the validated candidate surface.
- Source-drift publication failure now raises the contract-aligned authoritative message expected by the phase tests.

## Known non-changes

- No runtime, runner, or engine semantics were modified.
- No ablation workflow was added or executed.
- Existing Pydantic `schema` field warnings were not addressed in this phase because they are warning-only and outside the reviewer findings.

## Expected side effects

- Package publication fails earlier and more explicitly when candidate files are malformed, counts drift from the scorecard, or priority IDs do not resolve to validated candidate artifacts.
- Runtime coverage now locks the phase contract around skip routing, source-drift rejection, and ablation-depth non-execution.

## Validation performed

- `.venv/bin/pytest -q tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
- `.venv/bin/pytest -q tests/unit/test_optimization_helpers.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/test_architecture_baseline_docs.py`
- `.venv/bin/pytest -q tests/unit/test_optimization_helpers.py tests/runtime/test_workflow_run_traces_to_optimization_candidates.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/test_architecture_baseline_docs.py`
  Result: `100 passed` with existing Pydantic `schema` field warnings.

## Deduplication / centralization

- Centralized publication-surface validation in `_validate_candidate_artifact_publication_surface()` and `_read_candidate_publication_surface()` instead of scattering count/ID checks across individual package handlers or tests.
- Reused the workflow artifact schema specs for both runtime artifact declaration and package-time rereads to avoid duplicating JSON-shape validation logic.
