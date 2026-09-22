# Labs acceptance evidence

This audit maps PRD acceptance A37 to executable evidence. All paths are
relative to the repository root.

## Common evidence

`tests/test_labs.py::test_all_labs_workflows_complete_staged_fake_provider_runs`
discovers and completes all fifteen labs. For the fourteen ordinary labs it
asserts typed invocation, accepted phase order, immutable artifact capture, and
exact equality with an independent output inventory pinned to PRD section
11.3.1. The expected inventory is test data rather than data derived from the
workflow declarations, so dropping a declaration and its consumer fails the
acceptance test. Generated-package discovery and conditional handoff files have
focused consumer tests in `tests/test_labs_optimizer_consumers.py`.

`tests/test_labs_acceptance.py` parameterizes all fourteen ordinary labs and
proves each lab's surrounding checkpoint wiring, rather than relying only on a
shared-helper unit test:

- `needs_rework` repeats only the rejected producer/verifier phase and supplies
  immutable prior artifacts plus verifier feedback;
- `needs_replan` is injected at a non-framing phase and returns to that lab's
  declared earlier checkpoint, leaving one logical copy of the replanned phase;
- both `question` and `blocked` create a targeted durable human request and
  resume the same phase with the exact answer in feedback;
- `failed` terminates after the rejecting verifier, without later provider
  turns or a successful result;
- domain publication summaries are corrupted after capture for the six labs
  with deterministic cross-document gates, and each workflow rejects them.

`tests/test_labs_control.py` adds detailed release-lab assertions for inner and
outer replans, operation history/replay, output repair, and terminal failure.

## Per-lab matrix

| ID | Workflow | Success / artifacts | Rework | Replan | Question / blocked | Terminal failure | Publication / handoff evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L01 | `task_to_candidate_workflow_set` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Immutable final result and candidate IDs |
| L02 | `candidate_workflow_to_adapted_execution_plan` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Callable-parameter validation executes; validator rejection covered in optimizer tests |
| L03 | `task_to_workflow_strategy` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Immutable strategy/next-action result |
| L04 | `workflow_idea_to_workflow_package` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Candidate package materialization, validation, discovery, and authoritative-file protection |
| L05 | `workflow_package_to_composable_building_blocks` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Isolated overlay checks, source-drift rejection, and handoff identity tests |
| L06 | `workflow_run_history_to_failure_modes` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Bounded new-Journal projection and incompatible-store rejection; old history excluded |
| L07 | `workflow_to_eval_suite` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Eval-manifest validation, source/suite identity, and accepted handoff consumer coverage |
| L08 | `workflow_and_eval_to_refined_workflow_package` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Overlay/paired comparison, invalid-record rejection, interruption recovery, and no-relaunch proof |
| L09 | `workflow_portfolio_to_operating_system` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Workflow-level corrupted-summary rejection plus focused drift validator tests |
| L10 | `company_operation_to_recursive_improvement_cycle` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Workflow-level corrupted-summary rejection plus category/candidate drift tests |
| L11 | `investigation_request_to_evidence_pack` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Workflow-level corrupted-summary rejection plus readiness/count validation |
| L12 | `security_finding_to_verified_remediation` | E2E + exact inventory and external-state child handles | E2E | E2E across investigation child checkpoint | E2E both | E2E | Complete five-artifact child dependency, child readiness, and workflow-level corrupted closure rejection |
| L13 | `incident_to_hardening_program` | E2E + exact inventory | E2E | E2E | E2E both | E2E | Workflow-level corrupted-summary rejection plus incident publication validator tests |
| L14 | `release_candidate_to_go_no_go` | E2E + exact inventory and detailed phase order | E2E | E2E inner/outer | E2E both | E2E | Workflow-level corrupted-summary rejection plus decision consistency tests |
| L15 | `workflow_run_traces_to_optimization_candidates` | E2E for empty, insufficient, no-failure, and eligible evidence | Rejected review causes bounded proposal/review retry with feedback | N/A | N/A | Invalid review exhausts repairs and installs no receipt | Publication generation, tamper, concurrency, interruption, loader, and consumer suites |

## Optimizer-specific controls

`tests/test_optimizer.py::test_v2_eligible_evidence_review_loop_and_terminal_failure`
proves the three model-review outcomes: immediate acceptance, one rejection then
acceptance, and invalid review exhaustion. It asserts independent review turns,
feedback on the replacement proposal, provider-budget accounting, and absence
of any publication receipt after terminal failure.

The optimizer generation and handoff suites additionally cover incomplete or
tampered generations, source/suite identity drift, oversized evidence,
concurrent publication, interrupted paired evaluation, and the rule that an
attempted pair is never relaunched without reconciliation.

Together these scenarios cover A37's success and applicable
rework/replan/question/failure/publication paths for L01-L15.
