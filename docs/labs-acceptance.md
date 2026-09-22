# Labs acceptance audit

This audit maps PRD acceptance A37 to executable evidence. It deliberately
distinguishes a shared helper test from an end-to-end test of each lab's wiring.
All paths are relative to the repository root.

## Evidence legend

- **E2E**: the named lab is discovered and executed through `Botpipe`.
- **Representative**: the behavior is executed end to end only by
  `release_candidate_to_go_no_go`; the other ordinary labs use the same
  `_shared.run_phase` branch, but their checkpoint wiring is not exercised.
- **Unit**: the deterministic validator or publication component is tested in
  isolation.
- **Missing**: no acceptance scenario currently proves the behavior.
- **N/A**: the workflow has no such control path by design.

`tests/test_labs.py::test_all_labs_workflows_complete_staged_fake_provider_runs`
discovers and completes all fifteen labs. It proves typed invocation, phase
ordering on the accepted path, independent producer/verifier calls for the
fourteen ordinary labs, and capture of every artifact currently declared by
each workflow. It does not compare those declarations to the normative output
inventory in PRD section 11.3.1, so deleting a declaration and its consumer
could still leave this smoke test green.

`tests/test_labs_control.py` proves the shared ordinary-lab behavior end to end
with the release lab: local rework, an inner and outer backward replan,
question/blocked suspension and targeted resume, output repair without producer
repetition, and replay without provider repetition. Every ordinary workflow
calls `_shared.run_phase`, and every call has a `replan_target`, but only the
release lab's surrounding checkpoint reset logic is exercised by these tests.

## Per-lab matrix

| ID | Workflow | Success and artifacts | Rework | Replan | Question / blocked | Terminal failure | Publication / handoff evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L01 | `task_to_candidate_workflow_set` | E2E smoke; exact PRD inventory assertion missing | Representative | Representative | Representative | Missing | Captured result only; negative semantic handoff test missing |
| L02 | `candidate_workflow_to_adapted_execution_plan` | E2E smoke; exact inventory missing | Representative | Representative | Representative | Missing | Callable-parameter validator is exercised; per-lab rejection scenario missing |
| L03 | `task_to_workflow_strategy` | E2E smoke; exact inventory missing | Representative | Representative | Representative | Missing | Captured result only; strategy/next-action drift rejection missing |
| L04 | `workflow_idea_to_workflow_package` | E2E smoke; exact inventory and dynamic package inventory missing | Representative | Representative | Representative | Missing | Generated candidate preparation/validation executes; discoverability and failure branches have packaged-workflow coverage, but no A37-labelled lab matrix case |
| L05 | `workflow_package_to_composable_building_blocks` | E2E smoke; exact inventory missing | Representative | Representative | Representative | Missing | Candidate overlay/validation executes; source-drift and handoff primitives have optimizer consumer tests |
| L06 | `workflow_run_history_to_failure_modes` | E2E empty-history smoke; exact inventory missing | Representative | Representative | Representative | Missing | New-journal projection and incompatible-store rejection are covered; bounded nonempty history mapping needs a lab-level assertion |
| L07 | `workflow_to_eval_suite` | E2E smoke; exact inventory and optional handoff missing | Representative | Representative | Representative | Missing | Eval-manifest validation and source/suite identity primitives are tested; accepted optional handoff needs an end-to-end lab case |
| L08 | `workflow_and_eval_to_refined_workflow_package` | E2E smoke; exact inventory missing | Representative | Representative | Representative | Missing | Overlay, paired comparison recovery, invalid record rejection, and no-relaunch behavior are covered in `test_labs_optimizer_consumers.py`; lab-level failed check and no-promotion assertions remain missing |
| L09 | `workflow_portfolio_to_operating_system` | E2E smoke; exact inventory missing | Representative | Representative | Representative | Missing | Cross-document validator success/rejection is covered in `test_lab_publication_validation.py` |
| L10 | `company_operation_to_recursive_improvement_cycle` | E2E smoke; exact inventory missing | Representative | Representative | Representative | Missing | Summary/category/candidate drift rejection is covered in `test_lab_publication_validation.py` |
| L11 | `investigation_request_to_evidence_pack` | E2E smoke; exact inventory missing | Representative | Representative | Representative | Missing | Readiness/count validation is unit-tested; lab-level rejected publication is missing |
| L12 | `security_finding_to_verified_remediation` | E2E smoke plus immutable child-handle/state-dir test; exact inventory missing | Representative | Representative | Representative | Missing | Child readiness and security publication rejection are unit-tested; complete five-artifact child dependency is exercised |
| L13 | `incident_to_hardening_program` | E2E smoke; exact inventory missing | Representative | Representative | Representative | Missing | Incident publication rejection is unit-tested; lab-level gate failure is missing |
| L14 | `release_candidate_to_go_no_go` | E2E with exact artifact count and phase order | E2E | E2E inner and outer targets | E2E for both outcomes | Missing | Release publication rejection is unit-tested and accepted package is exercised end to end |
| L15 | `workflow_run_traces_to_optimization_candidates` | E2E for empty, insufficient, no-failure, and eligible evidence | Rejected-review retry missing | N/A | N/A | Provider/validation terminal failure missing | Comprehensive generation, tamper, concurrency, interrupted publication, loader, and consumer coverage in optimizer/publication suites |

## Required additions to close A37

1. Add a single normative inventory mapping for the fourteen ordinary labs and
   assert equality with each completed `LabWorkflowResult.artifact_names`, plus
   the conditional generated-package/evaluation/handoff files. This detects a
   dropped declaration instead of merely checking that the remaining artifacts
   are nonempty.
2. Parameterize every ordinary lab with its existing staged `Params` fixture.
   For each workflow, force one `needs_rework` response and assert that only the
   rejected phase producer repeats with immutable prior handles and feedback.
3. For each ordinary lab, force `needs_replan` from a phase whose target is an
   earlier checkpoint. Assert the declared target and dependent phases rerun,
   earlier committed phases do not rerun, and stale logical phase evidence is
   absent from the final result. The security lab must separately prove its
   investigation-child checkpoint.
4. For each ordinary lab, parameterize `question` and `blocked`; assert a durable
   pending input, answer its exact operation ID, and verify resume continues the
   same phase with the answer in feedback.
5. Force `failed` for every ordinary lab. Assert `LabPhaseRejected`, no later
   provider turn, no successful final result, and no publication activity. This
   path currently has no direct acceptance test, including for the release lab.
6. Add lab-level negative publication cases for workflows whose deterministic
   gate is currently only unit-tested. Preserve the existing component tests;
   the new cases prove that each workflow invokes the gate before returning.
7. For the optimizer lab, reject the first independent review and accept the
   second. Assert one logical proposal/review cycle per iteration, feedback on
   the second proposal, independent sessions, bounded budget accounting, and a
   receipt selecting only the accepted candidate generation. Add a terminal
   provider/validation failure case that proves no receipt is installed.

Until these additions pass, A37 is **partial**: discovery and every accepted
path are covered, shared control semantics are proven on one representative
ordinary lab, and publication components have strong focused coverage, but the
required per-lab branch matrix is not complete.
