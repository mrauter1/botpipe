# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c10
- Pair: implement
- Phase ID: migrate-direct-fit-publishers
- Phase Directory Key: migrate-direct-fit-publishers
- Phase Title: Migrate Direct-Fit Publishers
- Scope: phase-local producer artifact

## Cycle Mode

- `consolidate`
- Rationale: migrate the direct-fit publish-handler family to the already-shipped typed JSON-artifact seam instead of adding a new workflow or broader publication framework.

## Pre-Change Audit

- Most relevant existing workflows/helpers:
  - `stdlib/json_artifacts.py`
  - `stdlib/validation.py`
  - `workflows/task_to_candidate_workflow_set`
  - `workflows/task_to_workflow_strategy`
  - `workflows/candidate_workflow_to_adapted_execution_plan`
  - `workflows/workflow_to_eval_suite`
- Repeated pattern found:
  - publish handlers in the scoped family started from raw summary or manifest dict reads, then revalidated the same top-level fields by hand.
- Simplification chosen:
  - keep workflow-local typed summary/manifest specs in `contracts.py` and consume them from publish handlers via `JsonArtifactSpec.read(...)`.
- New workflow required:
  - no.
- 10x authoring leverage target:
  - make publish handlers read as typed artifact load, cross-artifact alignment, domain-policy checks, receipt write.
- Cycle action:
  - change and consolidate existing workflow-local contracts and publish handlers.

## Files Changed

- `docs/authoring.md`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_task_to_candidate_workflow_set.py`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `tests/runtime/test_workflow_to_eval_suite.py`
- `workflows/task_to_candidate_workflow_set/contracts.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/task_to_workflow_strategy/contracts.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/contracts.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/workflow_to_eval_suite/contracts.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`
- `.autoloop/tasks/recursive-framework-evolution-20260424t163807-c10/decisions.txt`

## Symbols Touched

- `CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT`
- `StrategySummaryPayload`
- `STRATEGY_SUMMARY_ARTIFACT`
- `ADAPTED_EXECUTION_SUMMARY_ARTIFACT`
- `ValidatedWorkflowParametersPayload`
- `VALIDATED_WORKFLOW_PARAMETERS_ARTIFACT`
- `WorkflowEvalSuiteSummaryPayload`
- `ValidatedEvalCaseManifestPayload`
- `VALIDATED_EVAL_CASE_MANIFEST_ARTIFACT`
- `WORKFLOW_EVAL_SUITE_SUMMARY_ARTIFACT`
- `TaskToCandidateWorkflowSet.on_publish_candidate_workflow_set(...)`
- `TaskToWorkflowStrategy.on_publish_strategy(...)`
- `CandidateWorkflowToAdaptedExecutionPlan.on_publish_adapted_execution_plan(...)`
- `WorkflowToEvalSuite.on_publish_workflow_eval_suite(...)`

## Checklist Mapping

- AC-1 typed publish-handler migration:
  - done in the four scoped publish handlers via `JsonArtifactSpec.read(...)`.
- AC-2 keep cross-artifact and domain-policy checks local:
  - done; builder-baseline policy, posture/route alignment, selected-workflow alignment, state-drift checks, and receipt shaping remain workflow-local.
- AC-3 targeted runtime proof:
  - done with the focused unit/runtime/docs suite listed under Validation Performed.

## Assumptions

- On-disk package summary artifacts intentionally omit verifier-only prose fields such as `summary`, even when the verifier payload model includes them.
- `proposed_workflow_parameters.json` and `eval_case_manifest.json` remain pre-validation workflow-local inputs; the typed seam starts at the validated outputs and durable summary artifacts.

## Preserved Invariants

- No CLI behavior change.
- No runtime-owned publication policy or hidden execution added.
- No `workflow.toml` semantic change.
- No provider contract change.
- No `ctx.invoke_workflow(...)` compatibility change.
- No artifact filename or top-level JSON key rename.

## Intended Behavior Changes

- The scoped publish handlers now start from typed summary or validated-manifest models instead of raw dict parsing.
- Earlier JSON-shape failures now surface at typed artifact load time before workflow-local policy checks run.

## Known Non-Changes

- Proposed pre-validation artifact reads stay raw where the helper seam is not yet authoritative by design.
- Cross-artifact alignment, readiness checks, state-drift checks, hidden-execution checks, and receipt shaping remain workflow-local.
- No generic publication registry or new root authoring primitive was introduced.

## Expected Side Effects

- Publish handlers are shorter to scan because mechanical summary parsing is gone from the direct-fit family.
- The durable JSON contract is now explicit in `contracts.py`, which reduces future drift between on-disk artifacts and publish-step expectations.

## Deduplication / Centralization Decisions

- Reused the existing `JsonArtifactSpec` plus model-file helper seam instead of adding another stdlib publication layer.
- Kept typed artifact specs workflow-local in `contracts.py` so summary/manifest ownership stays with the workflow family.
- Split durable JSON artifact models from verifier payload models when the artifact shape is narrower than the verifier payload contract.

## Validation Performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/test_architecture_baseline_docs.py`
- Result: `192 passed`
