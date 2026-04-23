# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t134234-c1
- Pair: implement
- Phase ID: workflow-builder-package
- Phase Directory Key: workflow-builder-package
- Phase Title: Ship Workflow Builder
- Scope: phase-local producer artifact

## Files changed

- `workflows/workflow_idea_to_workflow_package/__init__.py`
- `workflows/workflow_idea_to_workflow_package/params.py`
- `workflows/workflow_idea_to_workflow_package/contracts.py`
- `workflows/workflow_idea_to_workflow_package/workflow.py`
- `workflows/workflow_idea_to_workflow_package/workflow.toml`
- `workflows/workflow_idea_to_workflow_package/prompts/README.md`
- `workflows/workflow_idea_to_workflow_package/prompts/frame_producer.md`
- `workflows/workflow_idea_to_workflow_package/prompts/frame_verifier.md`
- `workflows/workflow_idea_to_workflow_package/prompts/design_producer.md`
- `workflows/workflow_idea_to_workflow_package/prompts/design_verifier.md`
- `workflows/workflow_idea_to_workflow_package/prompts/build_producer.md`
- `workflows/workflow_idea_to_workflow_package/prompts/build_verifier.md`
- `workflows/workflow_idea_to_workflow_package/prompts/evaluate_producer.md`
- `workflows/workflow_idea_to_workflow_package/prompts/evaluate_verifier.md`
- `workflows/workflow_idea_to_workflow_package/assets/workflow_package_checklist.md`
- `docs/workflows/workflow_idea_to_workflow_package.md`
- `tests/runtime/test_workflow_builder_package.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t134234-c1/decisions.txt`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`

## Symbols touched

- `Parameters`
- `CandidateSelectionPayload`
- `WorkflowDesignPayload`
- `WorkflowBuildPayload`
- `WorkflowEvaluationPayload`
- `FRAME_CANDIDATE_ROUTE_CONTRACTS`
- `DESIGN_PACKAGE_ROUTE_CONTRACTS`
- `BUILD_PACKAGE_ROUTE_CONTRACTS`
- `EVALUATE_PACKAGE_ROUTE_CONTRACTS`
- `WorkflowIdeaToWorkflowPackage`
- `WorkflowIdeaToWorkflowPackage.State`
- `WorkflowIdeaToWorkflowPackage.on_bootstrap`
- `WorkflowIdeaToWorkflowPackage.on_frame_candidate`
- `WorkflowIdeaToWorkflowPackage.on_design_package`
- `WorkflowIdeaToWorkflowPackage.on_build_package`
- `WorkflowIdeaToWorkflowPackage.on_evaluate_package`
- `WorkflowIdeaToWorkflowPackage.on_publish_package`
- `test_repo_workflows_namespace_discovers_workflow_builder_package`
- `test_workflow_builder_package_compiles_with_explicit_control_contracts`
- `test_workflow_builder_package_docs_capture_decision_records`
- `test_workflow_builder_package_runs_and_generates_a_compilable_package`

## Checklist mapping

- `AC-1`: added discoverable package files under `workflows/workflow_idea_to_workflow_package/` with explicit producer/verifier prompts and route grammar.
- `AC-2`: workflow design, prompt files, and workflow-local route contracts make deterministic responsibilities, provider-owned work, artifact paths, and rework versus replan behavior explicit.
- `AC-3`: added targeted package tests and a CLI discovery check proving discovery, compilation, scripted execution, and generated-package output.

## Assumptions

- A deterministic bootstrap step may seed workflow state from validated workflow parameters and write a run-local invocation artifact without adding new runtime features.
- Generated prompt file inventories can vary per authored package, so the stable contract is explicit top-level package artifacts plus authoritative prompt/build indexes in `prompt_contract_matrix.md` and `build_report.md`.

## Preserved invariants

- No new runtime subsystem, generator layer, or provider-facing packet abstraction was introduced.
- Prompt files remain the provider-facing SOP; the runtime continues to inject only narrow machine-readable control surfaces.
- Existing workflow packages and framework code paths were left untouched in this phase.

## Intended behavior changes

- The repository now exposes `workflow_idea_to_workflow_package` as a first-class workflow-builder package.
- `autoloop workflows show workflow_idea_to_workflow_package` now reports workflow-specific parameters and aliases for the new package.
- The repository now includes a workflow-specific design doc and a targeted scripted-provider exercise for the builder package.

## Known non-changes

- No additional domain workflow was shipped in this phase.
- No generic promotion or rollback runtime subsystem was added.
- No unrelated recursive wrapper/template cleanup was absorbed into this phase.

## Expected side effects

- Future cycles can discover and run the workflow-builder package directly from the package CLI.
- The standing recursive memory now treats the workflow-builder and step control-contract work as shipped cycle-1 baseline, not planned work.

## Validation performed

- `.venv/bin/python -m pytest -q tests/runtime/test_workflow_builder_package.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_workflow_integration_parity.py tests/test_architecture_baseline_docs.py`
- `PYTHONPATH=.. .venv/bin/python -m autoloop_v3.runtime.cli workflows show workflow_idea_to_workflow_package --root .`

## Deduplication / centralization decisions

- Kept payload schemas and route contracts package-local in `contracts.py` so the narrow machine-readable control contract stays near the workflow that owns it.
- Used deterministic `bootstrap` and `publish_package` system steps to handle state seeding and final publish receipt instead of inventing new runtime plumbing.

## Cross-phase / task-level justification

- Updated `.autoloop_recursive/` standing memory files in this phase because the cycle request requires those files to ship in the same change set as the workflow-builder package.
