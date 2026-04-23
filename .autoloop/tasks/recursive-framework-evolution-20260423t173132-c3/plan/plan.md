# Recursive Framework Evolution Cycle 3 Plan

## Scope Considered

- No authoritative clarification entries exist beyond the initial request snapshot.
- The request snapshot's mandatory inspection paths are stale. Current equivalents are:
  - `docs/autoloop_workflow_framework_prd.md` -> `docs/architecture.md`
  - `docs/autoloop_workflow_framework_adr.md` -> `docs/authoring.md` and `Workflow_Instructions.md`
  - `src/autoloop/framework/workflows.py` / `pairs.py` -> `core/steps.py`, `core/compiler.py`, `core/context.py`, and `core/validation.py`
  - `src/autoloop/framework/store.py` -> `runtime/stores/filesystem.py`
  - `src/autoloop/main.py` -> `runtime/cli.py` and `runtime/runner.py`
  - `src/autoloop/workflows/` -> repo-root `workflows/`
- Current workflow inventory is:
  - `workflows/autoloop_v1/`
  - `workflows/workflow_idea_to_workflow_package/`
  - `workflows/release_candidate_to_go_no_go/`
  - `workflows/incident_to_hardening_program/`
  - `workflows/investigation_request_to_evidence_pack/`
- The workflow-builder is already credible enough that this cycle does not need another builder-first package. Evidence:
  - explicit builder package topology, route contracts, prompts, docs, and proof under `workflows/workflow_idea_to_workflow_package/`, `docs/workflows/workflow_idea_to_workflow_package.md`, and `tests/runtime/test_workflow_builder_package.py`
  - current targeted baseline during planning:
    - `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py tests/runtime/test_workspace_and_context.py tests/unit/test_stdlib_and_extensions.py`
    - observed result: `29 passed`
- The evidence-pack building block is already a stable foundation rather than a speculative idea. Evidence:
  - `workflows/investigation_request_to_evidence_pack/` and `docs/workflows/investigation_request_to_evidence_pack.md`
  - current targeted baseline during planning:
    - `.venv/bin/pytest -q tests/runtime/test_investigation_request_to_evidence_pack.py`
    - observed result: `9 passed`
- The strongest remaining framework seam revealed by real workflow composition is safe child-workflow consumption:
  - `ctx.invoke_workflow(...)` and `stdlib/composition.py` already support explicit child invocation and artifact adoption
  - parent workflows still have to inspect `status`, `last_event`, and `output_artifacts` manually before deciding whether a child run is trustworthy
  - there is no small shared authoring seam for "this child must have succeeded, reached the expected terminal route, and produced these artifacts before the parent continues"
- Known pre-existing residual still present during planning:
  - `.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'recursive_wrapper_targets_the_package_cli_contract or recursive_templates_reference_current_package_repo_layout_only'`
  - observed result: `2 failed`
  - cause: `recursive_autoloop/run_recursive_autoloop.sh` still lacks `require_package_autoloop_cli`, and recursive templates still embed legacy `src/autoloop/...` paths
  - disposition for this cycle: explicit residual, not the paired framework improvement

## Decision Record: Candidate Additions

| Candidate | Why it matters | Why multi-turn / agentic execution helps | Trade-off | Decision |
| --- | --- | --- | --- | --- |
| Strengthen `workflow_idea_to_workflow_package` again | The request explicitly requires reconsidering the workflow-builder before picking anything else | Builder work spans candidate comparison, contract design, file generation, and proof | The builder is already credible in this repo; another builder-first cycle would delay a high-value consumer workflow without addressing the clearest portfolio gap | Deferred |
| `task_to_workflow_strategy` | A front-door workflow router would eventually help decide whether to reuse, adapt, compose, or author a workflow | Routing work benefits from durable candidate sets, fit-gap analysis, and explicit escalation paths | The current portfolio is still small, and the stronger immediate gap is proving that a reusable building block can feed a production domain workflow | Deferred |
| `security_finding_to_verified_remediation` | Turns a concrete security finding into exploit-bounded remediation planning, rollout guidance, and closure evidence | The work spans investigation intake, security assessment, remediation planning, closure packaging, and bounded rework loops | It only pays off cleanly if it reuses the existing evidence-pack building block instead of duplicating framing and evidence assembly | Chosen |

Selection rationale:

- The workflow-builder was explicitly reconsidered and remains strong enough not to dominate the cycle again.
- `task_to_workflow_strategy` is valuable, but right now it would be more meta than operational because the portfolio still needs another credible end-to-end consumer of reusable building blocks.
- `security_finding_to_verified_remediation` is the highest-value next move because it solves a real security-response job, consumes the evidence-pack building block the roadmap already points to, and pressures the framework at the exact seam that is still weak: safe child-workflow consumption.

## Chosen Addition: `security_finding_to_verified_remediation`

### Problem solved

Turn a security finding such as "Pentest found privilege escalation in admin impersonation" into a durable remediation package with exploit bounds, affected-surface analysis, remediation options, a chosen remediation plan, verification evidence requirements, rollout guidance, and a closure-ready package another team can execute.

### Why it matters

- Security organizations rarely need a free-form analysis; they need a bounded remediation package they can assign, review, roll out, and use to demonstrate closure.
- The repository already has a reusable evidence-building block, but it does not yet have a production workflow that consumes it and carries the work forward into security-specific assessment and remediation.
- This workflow is important software work for platform teams, AppSec, and product engineering because it links evidence, code/config reasoning, execution planning, and proof-of-closure.

### Sponsors and users

- Security engineering or AppSec
- Platform or service owners
- Engineering managers responsible for remediation commitments
- Incident-response or vulnerability-management leads

### Classification

This should ship as an end-to-end workflow. The trigger is a concrete security finding; the terminal outcome is an execution-ready remediation and closure package.

### Why Autoloop is a fit

- The work is artifact-heavy and spans repository inspection, durable evidence handling, security-specific analysis, remediation planning, and closure packaging.
- Producer/verifier loops matter because weak exploit bounds, weak remediation reasoning, or weak verification evidence must trigger bounded rework rather than optimistic completion.
- The existing reusable evidence-pack building block is already a natural upstream stage for this workflow.

### Why a one-shot interaction is insufficient

- The finding boundary and evidence surface need an authoritative evidence pack before security-specific judgment is reliable.
- Remediation design and closure planning require explicit artifacts that another team can challenge or execute later.
- The workflow needs bounded `needs_rework` and `needs_replan` behavior so local quality repair is distinct from a materially changed remediation boundary.

### Invocation path and public interface

- Package path: `workflows/security_finding_to_verified_remediation/`
- Discovery:
  - `autoloop workflows show security_finding_to_verified_remediation`
- Example direct run:

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

Planned workflow parameters:

- `finding_title: str` required
- `finding_source: Literal["pentest", "bug_bounty", "scanner", "internal_review", "customer_report", "other"]` required
- `severity: Literal["critical", "high", "medium", "low", "unknown"]` optional with default `unknown`
- `affected_system: str | None` optional
- `sponsor_role: str | None` optional
- `evidence_paths: list[str]` optional repeatable repo-path hints
- `deployment_constraints: list[str]` optional repeatable rollout constraints

### Terminal outcome

An accepted run produces a closure-ready security package containing at least:

- an adopted evidence pack and machine-readable evidence summary
- exploit summary and affected-surface analysis
- remediation options and selected remediation plan
- verification plan and rollout / rollback guidance
- stakeholder communication draft
- a deterministic `remediation_receipt.json`

## Workflow Design Contract For The New Workflow

### Objective

Turn a security finding into an execution-ready remediation and closure package grounded in an authoritative evidence pack and explicit security-specific assessment.

### Global deterministic workflow responsibilities

- Bootstrap the workflow-local invocation contract from the run request and workflow parameters.
- Invoke `investigation_request_to_evidence_pack` explicitly as a child workflow with `investigation_kind=security_remediation`.
- Keep child-workflow pause/block handling explicit in parent workflow code rather than hidden in the runtime.
- Require the child workflow to reach the expected terminal route and produce the expected artifacts before parent-local adoption.
- Hold security assessment, remediation planning, and closure packaging as separate work items with explicit rework versus replan behavior.
- Keep runtime injection narrow: only `expected_output_schema`, `available_routes`, and `route_contracts`.
- Publish a terminal remediation receipt only after the final package artifacts exist.

### Provider-owned cognitive responsibilities

- Interpret the evidence pack and repository context in security terms.
- Bound the exploit, affected surface, and plausible root causes.
- Compare remediation options and select the most credible fix approach.
- Define verification evidence, rollout constraints, rollback safety, and closure communication.

### Work-item boundary doctrine for this workflow

- `compose_evidence_pack` owns child invocation, reserved-route propagation, child-result validation, and parent-local artifact adoption only.
- `assess_security_finding` owns exploit bounds, affected surface, root-cause reasoning, and remediation-option analysis only.
- `plan_verified_remediation` owns chosen remediation, verification strategy, rollout plan, and rollback-safety planning only.
- `prepare_closure_package` owns stakeholder-ready packaging and closure evidence requirements only.
- `needs_rework` means the same work-item contract still holds.
- `needs_replan` means the finding boundary, remediation strategy, or acceptance surface changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `compose_evidence_pack`
- `security assessor` / `security verifier`
- `remediation planner` / `remediation verifier`
- `closure packager` / `closure verifier`
- deterministic `publish_remediation`

### Control flow as explicit procedure

1. `bootstrap`
2. `compose_evidence_pack`
3. `assess_security_finding`
4. `plan_verified_remediation`
5. `prepare_closure_package`
6. `publish_remediation`

### Parent-child composition contract

`compose_evidence_pack` should:

- call `run_child_workflow(...)` with `workflow="investigation_request_to_evidence_pack"`
- pass `investigation_title=<finding_title>`, `investigation_kind="security_remediation"`, `sponsor_role=<sponsor_role>`, and forwarded evidence hints / constraints
- if the child returns `status="paused"` with `last_event.tag=="question"`, surface the same parent `question` route explicitly
- if the child returns `status="paused"` with `last_event.tag=="blocked"`, surface the same parent `blocked` route explicitly
- on success, require:
  - `status=="success"`
  - `last_event.tag=="evidence_pack_published"`
  - child artifacts `investigation_scope_brief`, `evidence_pack`, `evidence_pack_summary`, `evidence_gap_register`, and `evidence_pack_receipt`
- adopt those artifacts into parent-local names before the first security-specific pair step

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
| `compose_evidence_pack` | invocation contract plus child workflow result | `finding_scope_brief.md`, `security_evidence_pack.md`, `security_evidence_pack_summary.json`, `security_evidence_gap_register.md`, `security_evidence_pack_receipt.json` | authoritative parent-local adopted evidence surface |
| `assess_security_finding` | adopted evidence artifacts, request, invocation contract | `exploit_summary.md`, `affected_surface.md`, `root_cause_analysis.md`, `remediation_options.md`, `assessment_summary.json` | authoritative security assessment and option analysis |
| `plan_verified_remediation` | assessment artifacts, evidence summary, constraints | `selected_remediation_plan.md`, `verification_plan.md`, `rollout_plan.md`, `rollback_safety_plan.md`, `remediation_summary.json` | authoritative execution-ready remediation plan |
| `prepare_closure_package` | evidence, assessment, and remediation plan artifacts | `security_remediation_package.md`, `stakeholder_communication_draft.md`, `closure_evidence_requirements.md` | human-facing terminal package and closure evidence contract |
| `publish_remediation` | terminal package artifacts and summaries | `remediation_receipt.json` | deterministic terminal receipt |

Authoritative precedence:

- `security_evidence_pack_summary.json` is the machine-readable authority for downstream security reasoning.
- `assessment_summary.json` and `remediation_summary.json` are the machine-readable authorities for later packaging and receipt validation.
- `security_remediation_package.md` is the primary human-facing terminal deliverable.
- `remediation_receipt.json` is the immutable workflow receipt.

### Runtime-injected control contract

The workflow must rely only on:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `FindingAssessmentPayload`
- `RemediationPlanPayload`
- `RemediationClosurePayload`

Route-contract semantics:

- every application route declares `summary`, `required_artifacts`, and `work_item_effect`
- runtime continues to validate route legality and payload shape mechanically
- prompt templates remain the provider-facing local execution contract

### Step prompt template inventory

| Prompt file | Purpose | Reads | Writes | Legal routes |
| --- | --- | --- | --- | --- |
| `prompts/assessment_producer.md` | bound exploit, affected surface, root cause, and remediation options | adopted evidence artifacts, invocation contract, request | assessment artifacts | `finding_assessed`, reserved routes |
| `prompts/assessment_verifier.md` | verify exploit bounds, option quality, and route choice | assessment inputs plus producer artifacts | verifier feedback only | `finding_assessed`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/remediation_producer.md` | choose remediation strategy and define verification / rollout / rollback plans | assessment artifacts, evidence summary, constraints | remediation-plan artifacts | `remediation_planned`, reserved routes |
| `prompts/remediation_verifier.md` | verify remediation choice, verification rigor, and route choice | remediation inputs plus producer artifacts | verifier feedback only | `remediation_planned`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/closure_producer.md` | assemble the stakeholder-ready closure package and evidence requirements | evidence, assessment, and remediation artifacts | package artifacts | `closure_package_ready`, reserved routes |
| `prompts/closure_verifier.md` | verify package completeness, closure evidence requirements, and route choice | closure inputs plus producer artifacts | verifier feedback only | `closure_package_ready`, `needs_rework`, `needs_replan`, reserved routes |

System-step contract requirements:

- `bootstrap` writes only the authoritative invocation snapshot.
- `compose_evidence_pack` is deterministic workflow code, not a provider-owned prompt.
- `publish_remediation` validates final artifact presence and machine-readable summary consistency before writing `remediation_receipt.json`.

### Verification and evidence contract

- Workflow discovery must find the package by canonical name and any declared aliases.
- Compilation must expose typed route contracts on the three pair steps.
- A scripted-provider runtime test must prove successful end-to-end execution, including child evidence-pack composition and parent-local adopted artifacts.
- A targeted runtime test must prove child `question` propagation from `compose_evidence_pack` to the parent pause surface.
- Unit coverage must prove the child-result contract helper rejects wrong status, wrong terminal route, and missing required child artifacts.
- Workflow docs must include:
  - candidate additions considered
  - framework improvement candidates considered
  - meaningful design decisions
  - implementation candidates considered
  - route grammar
  - runtime-injected control contract
  - proof references

### Rework / replan / block / fail policy

- `compose_evidence_pack` explicitly forwards child `question` and `blocked` routes instead of hiding them.
- `needs_rework` loops locally on `assess_security_finding`, `plan_verified_remediation`, or `prepare_closure_package`.
- `needs_replan` routes from remediation or closure back to the right earlier work item when the remediation boundary changes materially.
- `failed` remains for irrecoverable contradictions or invalid deterministic state.

### Recursive self-improvement policy

- This workflow is built under the existing builder-era package doctrine rather than inventing a new recursive mechanism.
- Recursive closeout for the cycle belongs in docs, tests, and `.autoloop_recursive/` memory updates, not in workflow-specific runtime machinery.

## Decision Record: Framework Improvement Candidates

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Manual child-result validation inside each parent workflow | No new framework surface | Duplicates status / route / artifact checks across every composed parent and makes mistakes likely | Rejected |
| Runtime-owned `SubworkflowStep` with built-in child validation and routing | Could centralize child-run behavior | Hides sequencing in the runtime, widens framework machinery, and violates the explicit-workflow doctrine | Rejected |
| Authoring-only child-result contract helper in `stdlib/composition.py` | Gives parents a reusable, explicit way to require child success, expected terminal route, and required artifacts before adoption | Must stay narrow and must not absorb pause/block routing decisions that belong in workflow code | Chosen |

Selection rationale:

- The chosen security workflow is the first real consumer of the evidence-pack building block, so the highest-value framework improvement is the smallest reusable seam that makes child consumption safe without changing runtime ownership.
- The improvement must remain authoring-only and additive because the current architecture deliberately keeps composition explicit in workflow code.
- Recursive wrapper/template cleanup remains a valid residual, but it is not the paired framework improvement for this cycle because it does not directly improve expression or reliability of the chosen workflow.

## Chosen Framework Improvement: Explicit Child-Result Contract Helper

Planned interface:

```python
def require_child_workflow_result(
    result: ChildWorkflowResult,
    *,
    status: str = "success",
    last_event: str | None = None,
    required_artifacts: Sequence[str] = (),
) -> ChildWorkflowResult:
    ...
```

Behavior contract:

- validate the child result on the authoring side only
- require the expected parent-facing success contract before artifact adoption
- raise a clear exception when the child status, terminal route, or required artifact set is wrong
- do not mutate `ChildWorkflowResult`
- do not change `ctx.invoke_workflow(...)` semantics
- do not make routing decisions for child `question` or `blocked`; parent workflow code still owns those explicit route mappings

Planned touch points:

- `stdlib/composition.py`
- `stdlib/__init__.py`
- `docs/authoring.md`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_workspace_and_context.py` only if a small runtime proof is needed for unchanged metadata shape

Compatibility expectation:

- additive only
- no CLI changes
- no persisted session or run-metadata shape changes
- no widening of runtime-injected control contracts

## Meaningful Design Decisions

### 1. Choose the first production consumer instead of another builder-first cycle

- Alternatives considered:
  - strengthen `workflow_idea_to_workflow_package` again
  - author `task_to_workflow_strategy`
  - author `security_finding_to_verified_remediation`
- Selected: `security_finding_to_verified_remediation`
- Why: the builder is already credible, and the portfolio now needs a real consumer of the evidence-pack building block more than another meta-workflow.

### 2. Compose the existing evidence-pack building block instead of repeating evidence assembly locally

- Alternatives considered:
  - repeat framing and evidence assembly inside the security workflow
  - compose `investigation_request_to_evidence_pack`
  - migrate existing release / incident workflows first
- Selected: compose `investigation_request_to_evidence_pack`
- Why: this is the cleanest way to prove reusable value, keep the security workflow focused on security-specific cognition, and avoid a third copy of the same evidence discipline.

### 3. Keep child-consumption safety in `stdlib`, not in the runtime

- Alternatives considered:
  - manual per-workflow validation
  - runtime-owned `SubworkflowStep`
  - authoring-only child-result contract helper
- Selected: authoring-only helper
- Why: it reduces duplication while keeping sequencing, reserved-route handling, and artifact adoption visible in workflow code.

### 4. Keep existing workflows and recursive wrapper cleanup out of implementation scope

- Alternatives considered:
  - migrate `release_candidate_to_go_no_go` and `incident_to_hardening_program` in the same cycle
  - fix `recursive_autoloop/` as part of the paired framework work
  - keep scope on the new workflow, the new helper seam, targeted docs/tests, and recursive-memory updates
- Selected: keep scope tight
- Why: this bounds regression risk and keeps the cycle centered on one new high-value workflow plus one reusable framework improvement.

## Implementation Candidates Considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Monolithic security workflow | Implement finding framing, evidence assembly, assessment, remediation, and packaging all inside one package | Fastest to author, but reintroduces duplicated evidence logic and weakens the value of the existing building block | Rejected |
| Composed security workflow with manual child validation | Invoke the evidence-pack building block, then check status and artifacts inline in workflow code | Explicit, but duplicates fragile child-result checks every time another parent wants to compose a child workflow | Rejected |
| Composed security workflow plus explicit `stdlib` child-result helper | Compose the evidence-pack building block, validate its result via a shared helper, then adopt artifacts into parent-local names | Slightly broader diff, but reusable and keeps runtime ownership clean | Selected |

## Milestones

### Milestone 1: Add the child-result contract helper

Planned files:

- `stdlib/composition.py`
- `stdlib/__init__.py`
- `docs/authoring.md`
- `tests/unit/test_stdlib_and_extensions.py`

Implementation notes:

- add a validation-only helper for expected child status, terminal route, and required artifacts
- keep pause/block propagation explicit in workflow code
- do not change `ChildWorkflowResult`, `ctx.invoke_workflow(...)`, or run metadata

Validation:

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workspace_and_context.py`

### Milestone 2: Implement `security_finding_to_verified_remediation`

Planned files:

- `workflows/security_finding_to_verified_remediation/__init__.py`
- `workflows/security_finding_to_verified_remediation/workflow.toml`
- `workflows/security_finding_to_verified_remediation/workflow.py`
- `workflows/security_finding_to_verified_remediation/params.py`
- `workflows/security_finding_to_verified_remediation/contracts.py`
- `workflows/security_finding_to_verified_remediation/prompts/*`
- `workflows/security_finding_to_verified_remediation/assets/*`
- `docs/workflows/security_finding_to_verified_remediation.md`
- `tests/runtime/test_security_finding_to_verified_remediation.py`

Implementation notes:

- use a deterministic system step for child evidence-pack composition
- adopt child artifacts into parent-local names before provider-owned security steps
- keep provider prompts focused on security assessment, remediation planning, and closure packaging

Validation:

- `.venv/bin/pytest -q tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_investigation_request_to_evidence_pack.py`

### Milestone 3: Close with proof, docs, and recursive memory

Planned files:

- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- task-local feedback and decision artifacts

Implementation notes:

- record that the builder remains credible
- mark `security_finding_to_verified_remediation` as shipped and `task_to_workflow_strategy` still deferred
- record the child-result contract helper as the chosen framework improvement
- keep recursive wrapper/template drift explicitly deferred unless the scoped work intentionally changes `recursive_autoloop/`

Validation:

- `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workspace_and_context.py tests/test_architecture_baseline_docs.py`
- only if `recursive_autoloop/` changes: `.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'recursive_wrapper_targets_the_package_cli_contract or recursive_templates_reference_current_package_repo_layout_only'`

## Compatibility And Regression Notes

- This cycle should be additive only. No public CLI syntax, provider config, persisted session payloads, or child-run metadata shapes should change.
- The new helper must remain authoring-only. It must not widen runtime-owned control surfaces or introduce hidden sequencing.
- Existing workflows should remain untouched except for documentation or recursive-memory references. Do not migrate `release_candidate_to_go_no_go` or `incident_to_hardening_program` in this cycle.
- The child composition step in the new workflow must explicitly preserve reserved-route behavior by forwarding child `question` / `blocked` outcomes instead of collapsing them into fatal errors or hidden retries.
- The known recursive wrapper/template package-CLI failures are pre-existing residuals. Do not claim they are fixed unless `recursive_autoloop/` is intentionally changed and the targeted tests pass.

## Risk Register

| ID | Risk | Surface | Mitigation | Rollback |
| --- | --- | --- | --- | --- |
| R1 | The helper grows into hidden control flow instead of staying a validation seam | `stdlib/composition.py`, `docs/authoring.md` | Keep the helper limited to success-contract validation; leave pause/block mapping in workflow code; add focused unit tests | Revert the helper and inline the checks inside the new workflow if the seam cannot stay narrow |
| R2 | The parent security workflow trusts a child run too loosely and advances with incomplete evidence | `workflows/security_finding_to_verified_remediation/workflow.py` | Require explicit child status, expected last event, and required artifacts before adoption; add runtime proof | Revert the new workflow package if the child-consumption contract cannot be made safe |
| R3 | Child reserved routes are mishandled and parent runs fail instead of pausing / blocking cleanly | composition system step and workflow-specific runtime tests | Explicitly inspect child `status` / `last_event` before success validation and add a runtime pause-propagation test | Fix before merge; do not ship a version that collapses child pauses into fatal errors |
| R4 | Scope expands into unrelated migrations or recursive wrapper cleanup | existing workflows, `recursive_autoloop/`, package-cli tests | Keep those areas explicitly out of scope unless a touched file requires a narrow compatibility update | Revert off-scope edits and keep residuals documented only |

## Open Residuals To Preserve

- `recursive_autoloop/run_recursive_autoloop.sh` and the recursive templates still need a dedicated package-CLI cleanup pass.
- `task_to_workflow_strategy` remains a good future candidate once the workflow portfolio and adaptation surfaces are broader.
- `release_candidate_to_go_no_go` and `incident_to_hardening_program` still embed their own evidence stages; a later cycle can decide whether migration to the building block is worth the regression surface after this first production consumer lands.
