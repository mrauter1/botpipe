# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c9
- Pair: implement
- Phase ID: workflow-run-history-to-failure-modes
- Phase Directory Key: workflow-run-history-to-failure-modes
- Phase Title: Workflow Run History To Failure Modes
- Scope: phase-local producer artifact

## Files changed

- `workflows/workflow_run_history_to_failure_modes/__init__.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.toml`
- `workflows/workflow_run_history_to_failure_modes/params.py`
- `workflows/workflow_run_history_to_failure_modes/contracts.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/prompts/README.md`
- `workflows/workflow_run_history_to_failure_modes/prompts/frame_producer.md`
- `workflows/workflow_run_history_to_failure_modes/prompts/frame_verifier.md`
- `workflows/workflow_run_history_to_failure_modes/prompts/analyze_producer.md`
- `workflows/workflow_run_history_to_failure_modes/prompts/analyze_verifier.md`
- `workflows/workflow_run_history_to_failure_modes/prompts/package_producer.md`
- `workflows/workflow_run_history_to_failure_modes/prompts/package_verifier.md`
- `workflows/workflow_run_history_to_failure_modes/assets/failure_mode_diagnostic_checklist.md`
- `docs/workflows/workflow_run_history_to_failure_modes.md`
- `tests/runtime/test_workflow_run_history_to_failure_modes.py`

## Symbols touched

- `workflows.workflow_run_history_to_failure_modes.WorkflowRunHistoryToFailureModes`
- `workflows.workflow_run_history_to_failure_modes.Parameters`
- `workflows.workflow_run_history_to_failure_modes.DiagnosticScopePayload`
- `workflows.workflow_run_history_to_failure_modes.FailureModeMapPayload`
- `workflows.workflow_run_history_to_failure_modes.ImprovementPressurePayload`
- `WorkflowRunHistoryToFailureModes.on_publish_failure_mode_package(...)`

## Checklist mapping

- Phase `workflow-run-history-to-failure-modes` deliverables: complete in this phase.
- Phase `cycle-nine-closeout` deliverables: intentionally deferred; out of active phase scope.

## Assumptions

- The paired run-history snapshot seam shipped in the prior phase remains the authoritative framework improvement consumed here.
- Cycle-nine recursive-memory updates and baseline-doc closeout stay in the later closeout phase unless a hard dependency forces them into scope.

## Preserved invariants

- Workflow outputs stay under `ctx.workflow_folder`; no new CLI, runtime-contract, or `workflow.toml` semantics were introduced.
- The diagnostic building block stops at publication and explicit next actions; it does not auto-run refinement, portfolio governance, or selected-workflow execution.
- The selected workflow package remains read-only.

## Intended behavior changes

- Adds `workflow_run_history_to_failure_modes` as a discoverable reusable workflow building block with explicit params, typed control contracts, prompt templates, and deterministic publication.
- Publish-time validation now rejects empty filtered histories, selected-workflow mismatches, missing diagnostic artifacts, and machine-readable packages that violate the explicit diagnostic-publication boundary.

## Known non-changes

- No recursive-memory or architecture-baseline-doc updates were made in this phase.
- No runtime-owned diagnostics automation, child-workflow routing, or selected-workflow mutation was added.

## Expected side effects

- Workflow discovery now includes `workflow_run_history_to_failure_modes`.
- Operators and later workflows can publish reusable failure-mode packages from historical workflow evidence without ad hoc `.autoloop` scraping.

## Validation performed

- `.venv/bin/pytest -q tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py`

## Deduplication / centralization

- The new workflow reuses `write_selected_workflow_capability_snapshot(...)` and `write_selected_workflow_run_history_snapshot(...)` instead of adding another workflow-resolution or run-discovery path.
