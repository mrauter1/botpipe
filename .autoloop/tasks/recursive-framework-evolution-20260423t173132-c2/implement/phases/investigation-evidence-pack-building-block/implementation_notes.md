# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c2
- Pair: implement
- Phase ID: investigation-evidence-pack-building-block
- Phase Directory Key: investigation-evidence-pack-building-block
- Phase Title: Ship Investigation Evidence-Pack Building Block
- Scope: phase-local producer artifact

## Files changed

- `workflows/investigation_request_to_evidence_pack/__init__.py`
- `workflows/investigation_request_to_evidence_pack/workflow.toml`
- `workflows/investigation_request_to_evidence_pack/params.py`
- `workflows/investigation_request_to_evidence_pack/contracts.py`
- `workflows/investigation_request_to_evidence_pack/workflow.py`
- `workflows/investigation_request_to_evidence_pack/prompts/README.md`
- `workflows/investigation_request_to_evidence_pack/prompts/frame_producer.md`
- `workflows/investigation_request_to_evidence_pack/prompts/frame_verifier.md`
- `workflows/investigation_request_to_evidence_pack/prompts/evidence_producer.md`
- `workflows/investigation_request_to_evidence_pack/prompts/evidence_verifier.md`
- `workflows/investigation_request_to_evidence_pack/assets/evidence_pack_checklist.md`
- `docs/workflows/investigation_request_to_evidence_pack.md`
- `tests/runtime/test_investigation_request_to_evidence_pack.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c2/decisions.txt`

## Symbols touched

- `InvestigationRequestToEvidencePack`
- `Parameters`
- `InvestigationFramingPayload`
- `InvestigationEvidencePackPayload`
- `FRAME_INVESTIGATION_ROUTE_CONTRACTS`
- `ASSEMBLE_EVIDENCE_PACK_ROUTE_CONTRACTS`
- `on_bootstrap`
- `on_publish_evidence_pack`
- `_security_investigation_provider`
- `_release_readiness_provider`
- `_write_parent_investigation_composer_workflow_package`

## Checklist mapping

- Milestone 2: complete
  - added the new reusable workflow package with explicit prompts, contracts, parameters, assets, and deterministic publish logic
  - added workflow-local docs under `docs/workflows/`
  - added workflow-specific runtime coverage for direct execution and helper-based composition
- Milestone 3: partially complete in this phase-local run
  - targeted proof is included
  - recursive memory updates remain intentionally untouched because the active phase contract scopes this run to the workflow package, docs, and runtime proof

## Assumptions

- Repo-root `core/`, `runtime/`, `stdlib/`, and `workflows/` remain the authoritative implementation surface for this cycle.
- The paired composition-helper phase is already authoritative for the framework improvement; this run should exercise that seam rather than add new runtime machinery.

## Preserved invariants

- Runtime-owned control surfaces remain limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- No new runtime/core step type, child-run metadata shape, CLI flag, or persisted run/session field was introduced.
- Existing `release_candidate_to_go_no_go` and `incident_to_hardening_program` packages were not migrated in this phase-local run.

## Intended behavior changes

- Added a discoverable `investigation_request_to_evidence_pack` building block with explicit framing and evidence-pack work items plus deterministic `evidence_pack_receipt.json` publication.
- Added runtime proof that the building block can run directly and can be composed through the authoring-only helper seam with explicit parent-local artifact adoption.

## Known non-changes

- No migration of existing release or incident workflows to consume the new building block.
- No recursive wrapper/template cleanup.
- No recursive memory updates in this phase-local implementation pass.

## Expected side effects

- Parent workflows can now delegate framed evidence-pack assembly to a reusable child workflow and adopt selected artifacts without adding hidden runtime sequencing.
- The workflow portfolio now has a reusable evidence-pack building block instead of only end-to-end workflows.

## Validation performed

- `.venv/bin/pytest -q tests/runtime/test_investigation_request_to_evidence_pack.py` -> `8 passed`
- `.venv/bin/pytest -q tests/runtime/test_workspace_and_context.py tests/unit/test_stdlib_and_extensions.py` -> `24 passed`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py` -> `8 passed`
- `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py` -> `5 passed`

## Deduplication / centralization decisions

- Reused the existing lifecycle-helper pattern for deterministic bootstrap/publication and the existing composition-helper seam for parent/child proof instead of adding new workflow-specific helper layers.
