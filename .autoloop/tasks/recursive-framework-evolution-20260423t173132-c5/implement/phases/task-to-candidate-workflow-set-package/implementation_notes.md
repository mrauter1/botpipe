# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c5
- Pair: implement
- Phase ID: task-to-candidate-workflow-set-package
- Phase Directory Key: task-to-candidate-workflow-set-package
- Phase Title: Task To Candidate Workflow Set Package
- Scope: phase-local producer artifact

## Files changed

- `workflows/task_to_candidate_workflow_set/__init__.py`
- `workflows/task_to_candidate_workflow_set/workflow.toml`
- `workflows/task_to_candidate_workflow_set/params.py`
- `workflows/task_to_candidate_workflow_set/contracts.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/task_to_candidate_workflow_set/prompts/README.md`
- `workflows/task_to_candidate_workflow_set/prompts/frame_producer.md`
- `workflows/task_to_candidate_workflow_set/prompts/frame_verifier.md`
- `workflows/task_to_candidate_workflow_set/prompts/analyze_producer.md`
- `workflows/task_to_candidate_workflow_set/prompts/analyze_verifier.md`
- `workflows/task_to_candidate_workflow_set/prompts/package_producer.md`
- `workflows/task_to_candidate_workflow_set/prompts/package_verifier.md`
- `workflows/task_to_candidate_workflow_set/assets/candidate_workflow_set_checklist.md`
- `docs/workflows/task_to_candidate_workflow_set.md`
- `workflows/task_to_workflow_strategy/contracts.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/task_to_workflow_strategy/prompts/select_producer.md`
- `workflows/task_to_workflow_strategy/prompts/select_verifier.md`
- `workflows/task_to_workflow_strategy/prompts/package_producer.md`
- `workflows/task_to_workflow_strategy/prompts/package_verifier.md`
- `docs/workflows/task_to_workflow_strategy.md`
- `tests/runtime/test_task_to_candidate_workflow_set.py`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c5/decisions.txt`

## Symbols touched

- `workflows.task_to_candidate_workflow_set.TaskToCandidateWorkflowSet`
- `workflows.task_to_candidate_workflow_set.Parameters`
- `workflows.task_to_candidate_workflow_set.CandidateRequestFramingPayload`
- `workflows.task_to_candidate_workflow_set.CandidateWorkflowAnalysisPayload`
- `workflows.task_to_candidate_workflow_set.CandidateWorkflowSetPayload`
- `workflows.task_to_workflow_strategy.TaskToWorkflowStrategy.on_build_candidate_workflow_set`
- `workflows.task_to_workflow_strategy.TaskToWorkflowStrategy.on_publish_strategy`
- `workflows.task_to_workflow_strategy.SELECT_STRATEGY_ROUTE_CONTRACTS`

## Checklist mapping

- AC-1: shipped `task_to_candidate_workflow_set` with explicit framing, capability capture, candidate analysis, candidate-set packaging, direct docs, and runtime proof that the builder baseline remains part of the durable candidate package.
- AC-2: made the deterministic/provider-owned boundary explicit in the new workflow package, prompts, contracts, and docs while keeping runtime-owned control surfaces limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- AC-3: added publication-side validation for the machine-readable readiness contract and updated `task_to_workflow_strategy` to consume the new building block through explicit child composition while preserving the parent-local strategy artifact contract.

## Assumptions

- The phase scope includes the immediate reuse proof path inside `task_to_workflow_strategy`, because the accepted plan and shared decisions explicitly require the front door to consume the new building block in the same change set.
- The previously shipped capability-snapshot seam remains authoritative for richer portfolio inspection; this phase builds on it instead of widening `workflow.toml` or runtime-owned routing.

## Preserved invariants

- `task_to_workflow_strategy` still publishes the same parent-local strategy artifacts and keeps `workflow_portfolio_snapshot.json` as a first-class parent artifact.
- `strategy_summary.json` and `strategy_receipt.json` keep their existing required fields and path references.
- Runtime/provider control metadata remains limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- Candidate retrieval, ranking, and route choice remain visible in workflow prompts and artifacts rather than hidden in runtime code.

## Intended behavior changes

- Added `task_to_candidate_workflow_set` as a reusable candidate-retrieval building block with deterministic capability capture, ranked candidate publication, machine-readable posture, and deterministic receipt validation.
- Updated `task_to_workflow_strategy` so candidate retrieval is now handled through explicit child composition rather than front-door-local prompt logic.
- Advanced recursive memory from “candidate retrieval is deferred” to “candidate retrieval shipped; adaptation planning is the next deferred layer.”

## Known non-changes

- No workflow auto-executes downstream domain workflows after candidate publication or final strategy publication.
- `candidate_workflow_to_adapted_execution_plan` remains deferred.
- `recursive_autoloop/` wrapper/template cleanup remains out of scope for this phase.

## Expected side effects

- Portfolio-facing runs now create child workflow state for `task_to_candidate_workflow_set` when `task_to_workflow_strategy` composes it.
- The repo workflow count in portfolio snapshots increases because `task_to_candidate_workflow_set` is now a discoverable package.
- Recursive-memory baseline tests now expect cycle-5 state rather than leaving candidate retrieval in the deferred set.

## Validation performed

- `.venv/bin/python -m py_compile workflows/task_to_candidate_workflow_set/__init__.py workflows/task_to_candidate_workflow_set/params.py workflows/task_to_candidate_workflow_set/contracts.py workflows/task_to_candidate_workflow_set/workflow.py workflows/task_to_workflow_strategy/contracts.py workflows/task_to_workflow_strategy/workflow.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/test_architecture_baseline_docs.py`
- `.venv/bin/pytest -q tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_compatibility_runtime.py tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_security_finding_to_verified_remediation.py tests/test_architecture_baseline_docs.py` (`102 passed`)

## Deduplication / centralization decisions

- Kept reusable candidate retrieval inside the new workflow package instead of adding runtime-owned ranking or selector machinery.
- Reused the existing composition helpers for child invocation, child-result validation, and parent-local artifact adoption so the new reuse proof stays explicit in workflow code.
