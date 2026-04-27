# Implementation Notes

- Task ID: recursive-framework-evolution-20260426t220607-c1
- Pair: implement
- Phase ID: remaining-typed-bootstrap-convergence
- Phase Directory Key: remaining-typed-bootstrap-convergence
- Phase Title: Finish Typed Bootstrap Convergence
- Scope: phase-local producer artifact

## Files Changed

- Workflows:
  - `workflows/release_candidate_to_go_no_go/workflow.py`
  - `workflows/investigation_request_to_evidence_pack/workflow.py`
  - `workflows/security_finding_to_verified_remediation/workflow.py`
  - `workflows/incident_to_hardening_program/workflow.py`
  - `workflows/workflow_idea_to_workflow_package/workflow.py`
- Targeted proof:
  - `tests/runtime/test_release_candidate_to_go_no_go.py`
  - `tests/runtime/test_investigation_request_to_evidence_pack.py`
  - `tests/runtime/test_security_finding_to_verified_remediation.py`
  - `tests/runtime/test_incident_to_hardening_program.py`
  - `tests/runtime/test_workflow_builder_package.py`
  - `tests/test_architecture_baseline_docs.py`
- Recursive memory:
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`

## Symbols Touched

- Workflow bootstraps:
  - `ReleaseCandidateToGoNoGo.on_bootstrap`
  - `InvestigationRequestToEvidencePack.on_bootstrap`
  - `SecurityFindingToVerifiedRemediation.on_bootstrap`
  - `IncidentToHardeningProgram.on_bootstrap`
  - `WorkflowIdeaToWorkflowPackage.on_bootstrap`
- Removed dead helper:
  - `workflows/investigation_request_to_evidence_pack/workflow.py::_normalize_investigation_kind`
- Added targeted typed-bootstrap proof tests for the five remaining workflows.

## Checklist Mapping

- AC-1:
  - Replaced the five remaining `dict(ctx.workflow_params)` bootstrap normalizers with typed `ctx.params` projection.
- AC-2:
  - Preserved invocation-contract payload keys, artifact names, route names, receipt filenames, and child-composition behavior.
- AC-3:
  - Updated recursive memory and baseline assertions.
  - Validation passed via `.venv/bin/pytest -q tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_incident_to_hardening_program.py tests/runtime/test_workflow_builder_package.py tests/test_architecture_baseline_docs.py` (`136 passed`).

## Assumptions

- `Context.params` remains authoritative when a workflow declares `Parameters`.
- `write_invocation_contract(...)` continues to add shared runtime metadata fields beyond the workflow-specific payload.

## Preserved Invariants

- No CLI syntax change.
- No runtime parameter coercion change.
- No `workflow.toml` semantic change.
- No `ctx.invoke_workflow(...)` change.
- No artifact-name, route-name, or receipt-filename change in the affected workflows.

## Intended Behavior Changes

- Bootstrap handlers in the five scoped workflows now ignore stale or contradictory raw `workflow_params` values when typed `ctx.params` is present.

## Known Non-Changes

- Publish handlers remain workflow-local.
- `Context.workflow_params` remains available as the compatibility/raw dict surface.
- Domain-specific parameter validation remains in each workflow’s `params.py`.

## Expected Side Effects

- Top-level bootstrap flows are shorter and mechanically uniform.
- Recursive memory now records that the earlier bootstrap closeout was partial and that this cycle finished the remaining five workflows.

## Dedup / Centralization Decisions

- Reused the existing `Context.params` seam rather than adding another bootstrap helper.
- Kept `open_workflow_sessions(...)` and `write_invocation_contract(...)` explicit in workflow code.
