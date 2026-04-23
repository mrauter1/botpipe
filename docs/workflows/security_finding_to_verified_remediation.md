# `security_finding_to_verified_remediation`

`security_finding_to_verified_remediation` is an end-to-end workflow that turns a concrete security finding into an evidence-backed remediation plan, rollout and rollback guidance, closure-evidence requirements, a stakeholder communication draft, and a deterministic publication receipt.

## Problem and value

- Problem solved: convert a finding such as "Pentest found privilege escalation in admin impersonation" into a durable remediation package with bounded exploit analysis, remediation options, a chosen fix plan, verification expectations, and closure-ready communication artifacts.
- Why it matters: security teams rarely need another free-form analysis; they need a package engineering can execute and AppSec can review without reconstructing the evidence or guesswork around proof of closure.
- Likely sponsors: AppSec, security engineering, platform owners, engineering managers, or incident/vulnerability management leads.
- Classification: end-to-end workflow. The trigger is a concrete security finding and the terminal outcome is a closure-ready remediation package.
- Why Autoloop fits: the work spans child workflow composition, evidence adoption, security-specific assessment, remediation planning, closure packaging, and verifier-gated local rework.
- Why one-shot is insufficient: the workflow needs a durable evidence base, explicit producer/verifier loops, and filesystem artifacts another team can inspect or challenge later.

## Invocation

- Package path: `workflows/security_finding_to_verified_remediation/`
- Discovery: `autoloop workflows show security_finding_to_verified_remediation`
- Direct run:

```bash
autoloop run security_finding_to_verified_remediation <task-id> \
  --message "Pentest found privilege escalation in admin impersonation." \
  -wf finding_title "Admin impersonation privilege escalation" \
  -wf finding_source pentest \
  -wf severity high \
  -wf affected_system "delegated admin impersonation" \
  -wf sponsor_role "security engineering" \
  -wf evidence_paths pentest/findings/admin-impersonation.md \
  -wf deployment_constraints "Preserve emergency admin access during rollout."
```

Parameters:

- `finding_title` required
- `finding_source` required: `pentest`, `bug_bounty`, `scanner`, `internal_review`, `customer_report`, or `other`
- `severity` optional: `critical`, `high`, `medium`, `low`, or `unknown`
- `affected_system` optional
- `sponsor_role` optional
- `evidence_paths` optional and repeatable
- `deployment_constraints` optional and repeatable

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | The cycle brief explicitly required reassessing the workflow-builder before choosing a new addition | The builder is already credible in this repository, so repeating another builder-first package would delay a higher-value operational workflow | Deferred |
| `task_to_workflow_strategy` | A front-door strategy workflow would help choose whether to reuse, adapt, compose, or author a workflow | Valuable, but the immediate portfolio gap was a real consumer workflow that proves reusable building-block composition in production scope | Deferred |
| `security_finding_to_verified_remediation` | Turns a concrete finding into exploit-bounded remediation, rollout guidance, and closure evidence | Only worth shipping if it composes `investigation_request_to_evidence_pack` instead of duplicating evidence framing and assembly locally | Chosen |

Selection rationale:

- The builder was explicitly reconsidered and remains strong enough not to dominate cycle 3 again.
- `task_to_workflow_strategy` remains important, but the stronger immediate move was proving that a domain workflow can consume the evidence-pack building block cleanly.
- `security_finding_to_verified_remediation` is the highest-value next addition because it solves a real software-security job, reuses the new building block, and pressures the framework at the exact seam exposed by real composition: safe child-result consumption.

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Authoring-only child-result contract helper | Lets parent workflows require child success, terminal route, and artifact presence before adoption | Adds one more helper, but keeps sequencing visible in workflow code and preserves the narrow runtime boundary | Chosen |
| Runtime-owned subworkflow step | Could reduce workflow-local code in parent packages | Hides control flow in runtime machinery and widens framework-owned semantics beyond the intended boundary | Rejected |
| Inline child-result validation only inside this workflow | Keeps changes local to this package | Duplicates a reusable authoring pattern and leaves later workflows to re-implement the same safety checks | Rejected |

## Meaningful design decisions

### 1. Child-evidence composition strategy

- Alternatives considered:
- re-implement framing and evidence-pack assembly inside this workflow
- invoke the child workflow and read child artifacts in place without parent-local adoption
- invoke `investigation_request_to_evidence_pack`, validate its result, and adopt a fixed child artifact set into parent-local names
- Selected: explicit child invocation plus validation and parent-local artifact adoption
- Why: it proves the building block is reusable, keeps parent prompts focused on security cognition rather than evidence framing, and avoids coupling downstream steps to child-run paths.

### 2. Evidence-pack orchestration boundary

- Alternatives considered:
- make evidence-pack composition a provider-owned step
- make evidence-pack composition a deterministic system step with explicit child `question` / `blocked` propagation
- hide child invocation inside a generic runtime-owned composition primitive
- Selected: deterministic system step with explicit propagation
- Why: child invocation, success validation, and artifact adoption are mechanical authoring logic, while the actual security analysis belongs in provider-owned pair steps.

### 3. Publication authority strategy

- Alternatives considered:
- trust the closure package files alone and publish without machine-readable validation
- publish from the remediation summary alone and ignore the adopted evidence summary
- validate both the adopted evidence summary and the remediation summary before writing the deterministic receipt
- Selected: validate both summaries and the terminal package artifacts
- Why: the receipt should prove the workflow closed over both the upstream evidence contract and the downstream remediation contract before publication.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Monolithic security workflow | Frame evidence, assess the finding, plan remediation, and package closure in one large pair step | Faster to author, but it blurs work-item boundaries and defeats explicit reuse of the evidence-pack building block | Rejected |
| Partial consumer workflow | Compose the evidence-pack child workflow and stop after security assessment | Useful as a building block, but it does not meet the end-to-end remediation and closure outcome the cycle asked for | Rejected |
| Explicit end-to-end workflow with deterministic child composition and three pair steps | Compose the evidence-pack child workflow, then separate assessment, remediation planning, and closure packaging | More artifacts and code, but much clearer contracts, rework boundaries, and runtime proof | Selected |

## Workflow contract

### Objective

Turn a security finding into an execution-ready remediation and closure package grounded in an authoritative evidence pack and explicit security-specific assessment.

### Global deterministic workflow responsibilities

- Bootstrap the authoritative invocation contract from workflow parameters and the run request.
- Invoke `investigation_request_to_evidence_pack` explicitly as a child workflow with `investigation_kind=security_remediation`.
- Keep child `question` and `blocked` propagation explicit in workflow code.
- Require the child workflow to succeed, reach `evidence_pack_published`, and produce the expected artifacts before parent-local adoption.
- Hold security assessment, remediation planning, and closure packaging as separate work items.
- Keep runtime control data narrow: `expected_output_schema`, `available_routes`, and `route_contracts`.
- Publish a deterministic remediation receipt only after the terminal package artifacts and machine-readable summaries exist.

### Provider-owned cognitive responsibilities

- Bound the exploit and affected surface from the adopted evidence pack.
- Compare remediation options and choose the strongest credible fix path.
- Define verification, rollout, and rollback-safety expectations.
- Prepare the final closure package and communication draft without overstating proof.

### Work-item boundary doctrine

- `compose_evidence_pack`: child invocation, reserved-route propagation, child-result validation, and parent-local artifact adoption only.
- `assess_security_finding`: exploit summary, affected surface, root-cause reasoning, remediation options, and assessment summary only.
- `plan_verified_remediation`: selected remediation, verification plan, rollout plan, rollback-safety plan, and remediation summary only.
- `prepare_closure_package`: final package, stakeholder communication draft, and closure-evidence requirements only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the evidence boundary, remediation strategy, or acceptance surface changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `compose_evidence_pack`
- `security assessor` / `security verifier`
- `remediation planner` / `remediation verifier`
- `closure packager` / `closure verifier`
- deterministic `publish_remediation`

### Control flow

1. `bootstrap`
2. `compose_evidence_pack`
3. `assess_security_finding`
4. `plan_verified_remediation`
5. `prepare_closure_package`
6. `publish_remediation`

### Route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `evidence_pack_adopted`
- `finding_assessed`
- `remediation_planned`
- `closure_package_ready`
- `needs_rework`
- `needs_replan`
- `remediation_published`

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `compose_evidence_pack` | `request.md`, `invocation_contract.json`, child workflow result | `finding_scope_brief.md`, `security_evidence_pack.md`, `security_evidence_pack_summary.json`, `security_evidence_gap_register.md`, `security_evidence_pack_receipt.json` | authoritative parent-local adopted evidence surface |
| `assess_security_finding` | adopted evidence artifacts and invocation contract | `exploit_summary.md`, `affected_surface.md`, `root_cause_analysis.md`, `remediation_options.md`, `assessment_summary.json` | authoritative exploit and option analysis |
| `plan_verified_remediation` | assessment artifacts, invocation contract, evidence summary | `selected_remediation_plan.md`, `verification_plan.md`, `rollout_plan.md`, `rollback_safety_plan.md`, `remediation_summary.json` | authoritative execution-ready remediation plan |
| `prepare_closure_package` | evidence, assessment, remediation artifacts, checklist | `security_remediation_package.md`, `stakeholder_communication_draft.md`, `closure_evidence_requirements.md` | human-facing terminal package and closure-evidence contract |
| `publish_remediation` | evidence summary, remediation summary, and terminal package artifacts | `remediation_receipt.json` | deterministic terminal receipt |

### Parent-child composition contract

`compose_evidence_pack` explicitly:

- calls `run_child_workflow(...)` with `workflow="investigation_request_to_evidence_pack"`
- passes `investigation_title=<finding_title>`, `investigation_kind="security_remediation"`, `sponsor_role=<sponsor_role>`, and forwarded `evidence_paths`
- forwards child `question` and `blocked` outcomes as parent `question` or `blocked`
- validates successful child completion through `require_child_workflow_result(...)`
- requires `ready_for_downstream_assessment=true` in the child summary before any parent-local artifact adoption
- adopts the child artifacts below into parent-local names before any provider-owned security step runs:
- `investigation_scope_brief` -> `finding_scope_brief.md`
- `evidence_pack` -> `security_evidence_pack.md`
- `evidence_pack_summary` -> `security_evidence_pack_summary.json`
- `evidence_gap_register` -> `security_evidence_gap_register.md`
- `evidence_pack_receipt` -> `security_evidence_pack_receipt.json`

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Step payload models:

- `assess_security_finding` -> `SecurityAssessmentPayload`
- `plan_verified_remediation` -> `VerifiedRemediationPayload`
- `prepare_closure_package` -> `SecurityClosurePackagePayload`

### Prompt templates

- `prompts/assessment_producer.md`: role `security assessor`; reads the adopted evidence artifacts and writes `exploit_summary`, `affected_surface`, `root_cause_analysis`, `remediation_options`, and `assessment_summary`; legal application routes are `finding_assessed`, `needs_rework`, and `needs_replan`.
- `prompts/assessment_verifier.md`: role `security verifier`; inspects the assessment artifacts and returns one legal route plus the typed payload.
- `prompts/remediation_producer.md`: role `remediation planner`; reads the assessment artifacts and writes `selected_remediation_plan`, `verification_plan`, `rollout_plan`, `rollback_safety_plan`, and `remediation_summary`; legal application routes are `remediation_planned`, `needs_rework`, and `needs_replan`.
- `prompts/remediation_verifier.md`: role `remediation verifier`; checks that the chosen remediation, verification strategy, and rollout constraints are coherent.
- `prompts/closure_producer.md`: role `closure packager`; reads the evidence, assessment, remediation plan, and checklist, then writes `security_remediation_package`, `stakeholder_communication_draft`, and `closure_evidence_requirements`; legal application routes are `closure_package_ready`, `needs_rework`, and `needs_replan`.
- `prompts/closure_verifier.md`: role `closure verifier`; checks that the package and communication draft do not overclaim closure and align with the remediation plan.

## Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose the typed route contracts for the three pair steps.
- Runtime proof must cover:
- successful end-to-end execution with explicit child-workflow composition
- deterministic parent-local adoption of child evidence artifacts
- refusal to adopt a child evidence pack that publishes with `ready_for_downstream_assessment=false`
- explicit child `question` propagation to the parent run
- publication of `remediation_receipt.json` only after the required terminal artifacts and summaries exist
- Publish validation must reject a missing or invalid `selected_remediation` before the terminal receipt is written.

## Rework / replan / block / fail policy

- `needs_rework`: local repair inside the current assessment, remediation-planning, or closure-packaging boundary.
- `needs_replan`: the evidence boundary, fix strategy, or acceptance surface changed materially enough that the workflow must move back to an earlier step.
- `blocked`: required evidence, repository prerequisites, or deployment constraints prevent safe progress inside the current step.
- `failed`: irreconcilable contradictions make the finding or remediation package non-credible.

## Recursive self-improvement policy

- The workflow follows the builder-era package doctrine and uses the cycle-3 child-result helper seam without widening runtime behavior.
- Candidate improvements to prompts or artifact contracts remain evidence-gated through workflow-local tests and the standing recursive memory ledgers.
- The workflow does not hide portfolio or routing policy inside the runtime; a future `task_to_workflow_strategy` workflow remains the explicit portfolio-level follow-up.

## Evidence

- Package implementation: `workflows/security_finding_to_verified_remediation/`
- Child building block consumed: `workflows/investigation_request_to_evidence_pack/`
- Workflow asset: `workflows/security_finding_to_verified_remediation/assets/security_remediation_package_checklist.md`
- Workflow-specific proof: `tests/runtime/test_security_finding_to_verified_remediation.py`
- The scripted tests prove workflow discovery, compilation, success-path execution, deterministic child-result adoption, publish validation, and child-question propagation.
