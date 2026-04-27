# `company_operation_to_recursive_improvement_cycle`

`company_operation_to_recursive_improvement_cycle` is an end-to-end company-level recursive learner that turns bounded company work history plus workflow telemetry into an explicit next-cycle improvement package, machine-readable summary, next actions, and a deterministic publication receipt. It stops at publication so later evaluation, refinement, decomposition, governance, or operating-pattern follow-through remains explicit and inspectable.

## Problem and value

- Problem solved: convert scattered company task history, workflow telemetry, and recursive pressure into a durable next-cycle package instead of ad hoc repo review and chat-only prioritization.
- Why it matters: once the portfolio can build, retrieve, adapt, evaluate, refine, diagnose, govern, and decompose workflows, the missing layer is a top-level learner that decides what the next recursive cycle should improve across those surfaces.
- Likely sponsors: workflow-platform owners, engineering-productivity teams, AI platform teams, delivery leadership, and recursive portfolio operators.
- Classification: end-to-end workflow.
- Why Autoloop fits: the work needs durable evidence capture, verifier-gated analysis, explicit next-action publication, and a terminal boundary another operator or workflow can trust later.
- Why one-shot is insufficient: credible company-level recursive improvement needs bounded task/workflow scope, evidence-backed priority categories, explicit rework versus replan behavior, and publication checks that reject hidden downstream execution or summary drift.

## Invocation

- Package path: `workflows/company_operation_to_recursive_improvement_cycle/`
- Discovery: `autoloop workflows show company_operation_to_recursive_improvement_cycle`
- Direct run:

```bash
autoloop run company_operation_to_recursive_improvement_cycle <task-id> \
  --message "Recommend the next recursive improvement cycle from current company work history and workflow telemetry." \
  -wf task_title "Company recursive-improvement review" \
  -wf sponsor_role "workflow platform" \
  -wf desired_outcome "Publish a prioritized recursive improvement cycle package." \
  -wf decision_drivers "Prioritize reusable leverage across workflows and operating patterns." \
  -wf decision_drivers "Keep runtime control narrow and stop at publication." \
  -wf constraints "Do not auto-run downstream workflows." \
  -wf focus_tasks recursive-framework-evolution-20260423t173132-c12 \
  -wf focus_workflows company_operation_to_recursive_improvement_cycle \
  -wf focus_workflows workflow_portfolio_to_operating_system \
  -wf focus_workflows workflow_package_to_composable_building_blocks \
  -wf statuses success \
  -wf statuses paused \
  -wf max_tasks 25 \
  -wf max_runs_per_workflow 10 \
  -wf max_messages_per_task 5
```

Parameters:

- `task_title` required
- `sponsor_role` optional
- `desired_outcome` optional
- `decision_drivers` optional and repeatable
- `constraints` optional and repeatable
- `focus_tasks` optional and repeatable
- `focus_workflows` optional and repeatable
- `statuses` optional and repeatable
- `max_tasks` optional, default `25`
- `max_runs_per_workflow` optional, default `10`
- `max_messages_per_task` optional, default `5`

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` major refresh | Mandatory builder baseline and still the greenfield path when the repository lacks a credible builder | Already credible in code, docs, and tests, so another builder-first cycle would delay the clearer top-level company-learning gap | Deferred |
| Reusable assessment/remediation building blocks | Valuable domain-level building blocks for operational follow-through once higher-order recursive prioritization exists | High leverage, but narrower than the missing company-level learner and less aligned with the standing roadmap pressure | Deferred |
| `company_operation_to_recursive_improvement_cycle` | Turns company work history plus workflow telemetry into a published next-cycle recursive-improvement package | Requires a bounded company snapshot seam and disciplined publication rules, but it directly fills the clearest remaining recursive layer | Chosen and shipped in this phase |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive read-only company-operation snapshot seam backed by shared task/run discovery | Gives company-level workflows one reusable way to capture bounded task history, recent messages, and workflow telemetry under `ctx.workflow_folder` without widening CLI/runtime contracts | Adds a focused workspace read model plus an authoring helper, but keeps prioritization and publication policy visible in workflow code and prompts | Chosen in the paired framework slice and consumed here |
| Overload `write_workflow_portfolio_health_snapshot(...)` with task/company semantics | Could avoid one new helper name | Blurs workflow-health evidence with task/company history, weakens scope clarity, and makes the helper harder to reason about or reuse safely | Rejected |
| Runtime-owned company-learning index, scoring engine, or automatic follow-through execution | Could shrink workflow-local code in the short term | Hides workflow meaning in runtime code, widens persisted behavior, and violates the rule that workflows own the global SOP and terminal boundary | Rejected |

## Meaningful design decisions

### 1. Scope boundary

- Alternatives considered:
- always analyze every task under `.autoloop`
- require one upstream artifact as the only legal entry point
- accept optional scoped task and workflow sets plus shared capability, health, and company snapshots
- Selected: optional `focus_tasks` and `focus_workflows` plus shared capability, portfolio-health, and company snapshots
- Why: it keeps the workflow reusable both as a broad company review and as a narrower recursive pass without forcing an upstream router or ad hoc repo scraping.

### 2. Priority model

- Alternatives considered:
- publish only prose recommendations
- publish one flat ranked list without explicit categories
- publish a machine-readable candidate manifest plus explicit priority categories and counts
- Selected: machine-readable candidate manifest plus explicit priority categories and counts
- Why: company-level recursive pressure spans portfolio, package, follow-through, policy, and operating-pattern work; categories keep that breadth explicit and inspectable.

### 3. Terminal boundary

- Alternatives considered:
- auto-run evaluation, refinement, decomposition, or governance follow-through from the package
- auto-mutate workflow packages or `.autoloop` state after publication
- stop at a published cycle package plus explicit next actions and receipt
- Selected: stop at a published cycle package plus explicit next actions and receipt
- Why: it keeps follow-through visible and reviewable while still producing a terminal package another operator or workflow can use immediately.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc `.autoloop` scraping inside the package | Build the cycle package directly against raw task/run paths and JSON parsing inside workflow code | Smallest diff, but duplicates the new company snapshot seam and weakens the authoring boundary | Rejected |
| Shared company-operation snapshot seam plus dedicated workflow package | Reuse the helper seam for authoritative evidence capture while keeping recursive-improvement policy visible in the workflow package, prompts, and docs | Slightly broader change set, but it is the clearest reusable and inspectable design | Selected |
| Runtime-owned company-learning subsystem | Move task aggregation, priority categorization, and next-cycle publication into runtime code | Collapses the workflow/runtime boundary and hides the recursive SOP where operators cannot inspect it easily | Rejected |

## Workflow contract

### Objective

Turn company work history, task/request evolution, and workflow telemetry into a verifier-gated recursive-improvement cycle package that recommends what to improve next without auto-running downstream workflows.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture authoritative workflow-local snapshots of the current workflow capability surface, scoped portfolio-health surface, and bounded company-operation history surface.
- Keep company framing, recursive-improvement analysis, and cycle packaging as separate work items.
- Require explicit ranked improvement candidates instead of hidden downstream execution.
- Publish only after the three snapshots, pressure artifacts, terminal package artifacts, and receipt all exist and agree.

### Provider-owned cognitive responsibilities

- Frame the company-level recursive-improvement problem, including sponsor goals, scope limits, and decision criteria.
- Interpret task history, request/message evolution, workflow health, and operating-pattern pressure together.
- Decide which improvements belong in the next cycle across workflow portfolio, workflow packages, follow-through work, composition/escalation policy, and operating patterns.
- Package explicit next actions and follow-through sequencing.

### Work-item boundary doctrine

- `capture_company_operation_context`: deterministic evidence capture only.
- `frame_company_operation`: scope, sponsor pressure, decision criteria, and acceptance surface only.
- `analyze_recursive_improvement_pressures`: pressure mapping, category-explicit ranking, and candidate selection only.
- `package_recursive_improvement_cycle`: terminal cycle package, machine-readable summary, and next actions only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the scope, evidence boundary, or recursive-improvement objective changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_company_operation_context`
- `company-operation framer` / `company-operation verifier`
- `recursive-improvement analyst` / `recursive-improvement verifier`
- `cycle packager` / `cycle-package verifier`
- deterministic `publish_recursive_improvement_cycle`

### Control flow

1. `bootstrap`
2. `capture_company_operation_context`
3. `frame_company_operation`
4. `analyze_recursive_improvement_pressures`
5. `package_recursive_improvement_cycle`
6. `publish_recursive_improvement_cycle`

### Route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `company_operation_context_captured`
- `company_operation_framed`
- `recursive_improvement_pressures_analyzed`
- `recursive_improvement_cycle_ready`
- `needs_rework`
- `needs_replan`
- `recursive_improvement_cycle_published`

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local invocation snapshot |
| `capture_company_operation_context` | request, invocation contract, optional task/workflow filters, status filters | `workflow_capability_snapshot.json`, `workflow_portfolio_health_snapshot.json`, `company_operation_snapshot.json` | authoritative company-level evidence bundle |
| `frame_company_operation` | request, invocation contract, three snapshots, framework docs | `company_operation_brief.md`, `recursive_improvement_criteria.md` | authoritative company framing and recursive-improvement criteria |
| `analyze_recursive_improvement_pressures` | request, invocation contract, three snapshots, framing artifacts | `company_pressure_map.md`, `recursive_improvement_priority_matrix.md`, `recursive_improvement_candidates.json` | authoritative pressure map and ranked candidate set |
| `package_recursive_improvement_cycle` | request, invocation contract, snapshots, checklist, framing artifacts, pressure artifacts | `recursive_improvement_cycle.md`, `recursive_improvement_summary.json`, `recursive_improvement_next_actions.md` | authoritative terminal cycle package |
| `publish_recursive_improvement_cycle` | snapshots, pressure artifacts, terminal cycle package | `recursive_improvement_cycle_receipt.json` | deterministic terminal receipt proving the package is explicit and publication-ready |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- `route_infos`

Payload models used by the package:

- `CompanyOperationFramingPayload`
- `RecursiveImprovementAnalysisPayload`
- `RecursiveImprovementCyclePayload`

### Prompt templates

- `prompts/frame_producer.md`: role `company-operation framer`; frames the scoped task/workflow slice, sponsor pressure, and recursive-improvement criteria.
- `prompts/frame_verifier.md`: role `company-operation verifier`; checks that the company scope and criteria are explicit enough for recursive-improvement analysis.
- `prompts/analyze_producer.md`: role `recursive-improvement analyst`; writes the pressure map, priority matrix, and machine-readable candidate manifest.
- `prompts/analyze_verifier.md`: role `recursive-improvement verifier`; checks that the ranked candidate set is evidence-backed, scope-safe, and category-explicit.
- `prompts/package_producer.md`: role `cycle packager`; publishes the cycle package, summary, and explicit next actions.
- `prompts/package_verifier.md`: role `cycle-package verifier`; confirms the package is publication-ready and still stops at publication rather than hidden downstream execution.

## Verification and evidence contract

- Workflow discovery must find the package by canonical name and aliases.
- Compilation must expose typed route metadata and payload schemas for the three pair steps.
- Runtime proof must cover:
- successful publication of `workflow_capability_snapshot.json`, `workflow_portfolio_health_snapshot.json`, `company_operation_snapshot.json`, `company_pressure_map.md`, `recursive_improvement_priority_matrix.md`, `recursive_improvement_candidates.json`, `recursive_improvement_cycle.md`, `recursive_improvement_summary.json`, `recursive_improvement_next_actions.md`, and `recursive_improvement_cycle_receipt.json`
- deterministic capture of bounded task history, recent messages, and scoped workflow telemetry from the current `.autoloop` task/run records without mutating task or run state
- proof that the workflow stops at publication and does not auto-run evaluation, refinement, decomposition, governance, or remediation work
- publish-side rejection of missing snapshot artifacts, unknown focus-task or focus-workflow references, summary drift, invalid priority categories, and outputs that imply hidden downstream execution

## Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, recursive-improvement analysis, or packaging boundary.
- `needs_replan`: the scoped task slice, workflow slice, evidence boundary, or recursive-improvement objective changed materially enough that earlier work must be revisited.
- `blocked`: a missing prerequisite or repository fact prevents a credible recursive-improvement package.
- `failed`: irreconcilable contradictions make the current package non-credible.

## Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring baseline and was reconsidered before shipping this company-level learner.
- The package consumes the cycle-12 company snapshot seam plus the existing capability and portfolio-health seams rather than inventing runtime-owned company scoring or automatic follow-through.
- The package intentionally stops at publication so downstream evaluation, refinement, decomposition, governance, and operating-pattern work stay explicit and evidence-gated.

## Evidence

- Package implementation: `workflows/company_operation_to_recursive_improvement_cycle/`
- Shared seams consumed: `runtime/workspace.py`, `stdlib/company.py`, and `stdlib/portfolio.py`
- Workflow asset: `workflows/company_operation_to_recursive_improvement_cycle/assets/recursive_improvement_cycle_checklist.md`
- Workflow-specific proof: `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- The scripted tests prove workflow discovery, compilation, terminal publication, filter handling, and publish-side rejection of missing snapshots, unknown focus references, summary drift, invalid priority categories, and hidden downstream execution signals.
