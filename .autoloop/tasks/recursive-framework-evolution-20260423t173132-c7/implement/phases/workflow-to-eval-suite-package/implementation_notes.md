# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c7
- Pair: implement
- Phase ID: workflow-to-eval-suite-package
- Phase Directory Key: workflow-to-eval-suite-package
- Phase Title: Workflow To Eval Suite
- Scope: phase-local producer artifact

## Files Changed

- `workflows/workflow_to_eval_suite/__init__.py`
- `workflows/workflow_to_eval_suite/params.py`
- `workflows/workflow_to_eval_suite/contracts.py`
- `workflows/workflow_to_eval_suite/workflow.toml`
- `workflows/workflow_to_eval_suite/workflow.py`
- `workflows/workflow_to_eval_suite/prompts/README.md`
- `workflows/workflow_to_eval_suite/prompts/frame_producer.md`
- `workflows/workflow_to_eval_suite/prompts/frame_verifier.md`
- `workflows/workflow_to_eval_suite/prompts/design_producer.md`
- `workflows/workflow_to_eval_suite/prompts/design_verifier.md`
- `workflows/workflow_to_eval_suite/prompts/package_producer.md`
- `workflows/workflow_to_eval_suite/prompts/package_verifier.md`
- `workflows/workflow_to_eval_suite/assets/eval_suite_checklist.md`
- `docs/workflows/workflow_to_eval_suite.md`
- `tests/runtime/test_workflow_to_eval_suite.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `tests/test_architecture_baseline_docs.py`

## Symbols Touched

- `WorkflowToEvalSuite`
- `workflow_to_eval_suite.Parameters`
- `EvaluationTargetFramingPayload`
- `EvalCaseDesignPayload`
- `WorkflowEvalSuitePayload`
- `FRAME_EVALUATION_TARGET_ROUTE_CONTRACTS`
- `DESIGN_EVAL_CASES_ROUTE_CONTRACTS`
- `PACKAGE_WORKFLOW_EVAL_SUITE_ROUTE_CONTRACTS`
- cycle-7 recursive memory closeout records
- baseline-doc assertions for cycle 7

## Checklist Mapping

- Phase deliverable / add `workflows/workflow_to_eval_suite/`: complete
- Phase deliverable / implement params, contracts, explicit prompts, checklist asset, and workflow logic: complete
- Phase deliverable / add `docs/workflows/workflow_to_eval_suite.md`: complete
- Phase deliverable / add `tests/runtime/test_workflow_to_eval_suite.py`: complete
- Output requirement / update `.autoloop_recursive/` standing memory: complete
- Dependency / rely on the earlier evaluation-helper seam without widening CLI or runtime-owned execution: preserved

## Assumptions

- A published eval suite must include at least one `benchmark`, one `edge`, and one `adversarial` case.
- Publish-time validation should treat the helper-produced `validated_eval_case_manifest.json` as the authoritative canonical manifest.
- The selected workflow remains fixed for the entire suite-authoring run.

## Preserved Invariants

- The runtime/provider boundary stays narrow: pair steps use only `expected_output_schema`, `available_routes`, and `route_contracts`.
- The workflow stops at suite publication and does not execute the selected workflow.
- Selected-workflow inspection and eval-case validation still flow through the shared stdlib seams instead of ad hoc runtime imports.
- No CLI flags, `workflow.toml` contract changes, or runtime-owned evaluation execution were introduced.

## Intended Behavior Changes

- Added the `workflow_to_eval_suite` reusable building block with explicit framing, case-design, packaging, and publication stages.
- Added publish-time validation that canonicalizes the proposed eval manifest and rejects summary drift before receipt publication.
- Recorded cycle-7 closeout state in recursive memory and baseline-doc tests.

## Known Non-Changes

- No auto-running of the selected workflow or evaluation harness.
- No front-door or adaptation-workflow behavior changes.
- No changes to `stdlib/evaluation.py` in this phase-local implementation; the workflow consumes the already-shipped seam.

## Expected Side Effects

- Successful runs now write `selected_workflow_capability.json`, `workflow_eval_suite_summary.json`, `validated_eval_case_manifest.json`, and `workflow_eval_suite_receipt.json` under the workflow workspace.
- Malformed case kinds, duplicate case ids, unsupported case parameters, unknown expected artifacts, and summary drift now fail during publish instead of being deferred to later operators.

## Validation Performed

- `.venv/bin/pytest -q tests/runtime/test_workflow_to_eval_suite.py`
- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workflow_to_eval_suite.py tests/test_architecture_baseline_docs.py`

## Deduplication / Centralization Decisions

- Reused `write_selected_workflow_capability_snapshot(...)` for selected-workflow contract capture instead of adding eval-specific inspection logic.
- Reused `write_validated_eval_case_manifest(...)` for canonical manifest validation instead of duplicating case-kind, artifact-surface, and workflow-parameter checks in the workflow package.
