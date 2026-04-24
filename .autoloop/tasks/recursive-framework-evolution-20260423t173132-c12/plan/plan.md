# Cycle 12 Plan

## Scope considered

- Authoritative inputs reviewed: the immutable request snapshot, the current run raw log, the standing recursive-memory files, the live framework/docs/workflow packages, and the empty cycle-12 plan artifacts.
- No clarification entries were appended after run start, so the initial request snapshot remains authoritative for this turn.
- The request snapshot's mandatory inspection paths are stale in this checkout. The current equivalents used for planning are repo-root `docs/architecture.md`, `docs/authoring.md`, `Workflow_Instructions.md`, `core/`, `runtime/`, `stdlib/`, and repo-root `workflows/`.
- The worktree is dirty from earlier package-layout migration work and prior Autoloop tasks. Cycle 12 implementation must stay scoped to the paired company-level workflow, its narrow framework seam, targeted docs/tests, task-local planning artifacts, and the required `.autoloop_recursive/` memory updates.
- Current builder assessment: `workflow_idea_to_workflow_package` remains a credible workflow-builder baseline. Evidence reviewed:
  - `workflows/workflow_idea_to_workflow_package/`
  - `docs/workflows/workflow_idea_to_workflow_package.md`
  - `tests/runtime/test_workflow_builder_package.py`
- Current recursive baseline proof observed during planning:
  - `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py`
  - observed result: `89 passed`
- Current missing framework seam revealed by the existing portfolio:
  - `stdlib` already exposes authoring-only helpers for selected-workflow capability, run-history, refinement, decomposition, and portfolio health snapshots.
  - `runtime/workspace.py` exposes read-only run enumeration, but not a reusable company/task-level operating-history summary seam.
  - There is no authoring-only helper that turns task request history, task message history, workflow run summaries, and source-path pointers into a bounded workflow-local artifact another governance-consumer workflow can inspect safely.

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` major refresh | Mandatory builder baseline and still the greenfield path when the repository lacks a credible builder | The builder is already credible in code, docs, and proof, so another builder-first cycle would delay the stronger company-level learning gap | Deferred |
| `company_operation_to_recursive_improvement_cycle` | Turns company work history plus workflow telemetry into a durable next-cycle improvement package | Requires a new company-operation snapshot seam and disciplined terminal boundary, but it directly fills the clearest deferred recursive layer | Chosen |
| Reusable assessment/remediation building blocks | Still valuable for later domain workflows that share evidence-driven assessment and repair patterns | High leverage, but narrower than the now-missing top-level learner and less aligned with the current recursive roadmap | Deferred |

### Why the chosen addition wins

- Problem solved: convert company work history across tasks plus workflow telemetry into an explicit recursive-improvement cycle package instead of relying on ad hoc repo review and chat-only prioritization.
- Likely sponsors: workflow-platform owners, engineering-productivity teams, AI platform teams, delivery leadership, and recursive portfolio operators.
- Classification: end-to-end workflow.
- Why Autoloop fits: the work needs durable evidence capture, verifier-gated analysis, explicit next-action packaging, and a terminal artifact set other operators or workflows can inspect later.
- Why one-shot is insufficient: a credible company-level learner needs bounded scope, durable evidence artifacts, explicit rework versus replan behavior, machine-readable priorities, and a publication gate that rejects hidden downstream execution.
- Terminal outcome: a published recursive-improvement cycle package that prioritizes workflow-portfolio changes, workflow-package refinements, eval/refinement/decomposition follow-through, composition/escalation policy updates, and organization-level operating-pattern changes.

## Chosen addition contract

- Package path: `workflows/company_operation_to_recursive_improvement_cycle/`
- Discovery target: `autoloop workflows show company_operation_to_recursive_improvement_cycle`
- Direct invocation:

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
  -wf focus_workflows workflow_portfolio_to_operating_system \
  -wf focus_workflows workflow_package_to_composable_building_blocks \
  -wf statuses success \
  -wf statuses paused \
  -wf max_tasks 25 \
  -wf max_runs_per_workflow 10 \
  -wf max_messages_per_task 5
```

- Planned parameters:
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

### Workflow objective

Turn company work history, task/request evolution, and workflow telemetry into a verifier-gated recursive-improvement cycle package that recommends what to improve next without auto-running downstream workflow authoring, refinement, or governance work.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture authoritative workflow-local snapshots of:
  - the workflow capability surface
  - the portfolio run-health surface
  - the company/task-level operating history surface
- Keep company framing, recursive-improvement analysis, and cycle packaging as separate work items.
- Require explicit prioritized improvement candidates instead of hidden downstream execution.
- Publish only after the capability snapshot, portfolio-health snapshot, company-operation snapshot, analysis artifacts, terminal package artifacts, and receipt all exist and agree.

### Provider-owned cognitive responsibilities

- Frame the company-level improvement problem, including sponsor goals, scope limits, and decision criteria.
- Interpret task history, request/message evolution, workflow health, and ecosystem pressure together.
- Decide which improvements belong in the next cycle across workflow portfolio, workflow packages, evaluation/refinement/decomposition follow-through, composition/escalation policy, and organization-level operating patterns.
- Package explicit next actions and follow-through sequencing.

### Work-item boundary doctrine

- `capture_company_operation_context`: deterministic evidence capture only.
- `frame_company_operation`: scope, sponsor pressure, decision criteria, and acceptance surface only.
- `analyze_recursive_improvement_pressures`: pressure mapping, priority ranking, and candidate selection only.
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

### Planned control flow

1. `bootstrap`
2. `capture_company_operation_context`
3. `frame_company_operation`
4. `analyze_recursive_improvement_pressures`
5. `package_recursive_improvement_cycle`
6. `publish_recursive_improvement_cycle`

### Planned route grammar

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
- `recursive_improvement_cycle_published`
- `needs_rework`
- `needs_replan`

### Planned artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_company_operation_context` | request, invocation contract, task/workflow/status filters | `workflow_capability_snapshot.json`, `workflow_portfolio_health_snapshot.json`, `company_operation_snapshot.json` | authoritative company-level evidence bundle |
| `frame_company_operation` | request, invocation contract, three snapshots, framework docs | `company_operation_brief.md`, `recursive_improvement_criteria.md` | authoritative framing and acceptance boundary |
| `analyze_recursive_improvement_pressures` | invocation contract, three snapshots, framing artifacts | `company_pressure_map.md`, `recursive_improvement_priority_matrix.md`, `recursive_improvement_candidates.json` | authoritative pressure map and prioritized machine-readable candidate set |
| `package_recursive_improvement_cycle` | snapshots, framing artifacts, analysis artifacts, checklist asset | `recursive_improvement_cycle.md`, `recursive_improvement_summary.json`, `recursive_improvement_next_actions.md` | authoritative terminal cycle package and next-action surface |
| `publish_recursive_improvement_cycle` | snapshots, analysis artifacts, package artifacts | `recursive_improvement_cycle_receipt.json` | deterministic terminal receipt proving the package is publication-ready |

### Planned runtime-injected control contract

The workflow must continue using only:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `CompanyOperationFramingPayload`
- `RecursiveImprovementAnalysisPayload`
- `RecursiveImprovementCyclePayload`

### Planned step prompt contracts

- `prompts/frame_producer.md`
  - Role: `company-operation framer`
  - Required reads: `request.md`, `invocation_contract.json`, `workflow_capability_snapshot.json`, `workflow_portfolio_health_snapshot.json`, `company_operation_snapshot.json`, `docs/architecture.md`, and `docs/authoring.md`
  - Required writes: `company_operation_brief.md` and `recursive_improvement_criteria.md`
  - Legal routes: `company_operation_framed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
  - Evidence expectation: make the scope, sponsor pressure, decision drivers, and accepted recursive-improvement surface explicit enough for ranking work
  - Forbidden/out of scope: do not rank improvements yet, do not mutate workflow packages, and do not assume runtime-owned prioritization

- `prompts/frame_verifier.md`
  - Role: `company-operation verifier`
  - Required reads: framing inputs plus `company_operation_brief.md` and `recursive_improvement_criteria.md`
  - Required writes: verifier control metadata only through `CompanyOperationFramingPayload`
  - Legal routes: `company_operation_framed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
  - Evidence expectation: confirm the scope, evidence boundary, and decision criteria are coherent and bounded
  - Forbidden/out of scope: do not author priorities, and do not approve vague scope or criteria drift

- `prompts/analyze_producer.md`
  - Role: `recursive-improvement analyst`
  - Required reads: three snapshots plus framing artifacts
  - Required writes: `company_pressure_map.md`, `recursive_improvement_priority_matrix.md`, and `recursive_improvement_candidates.json`
  - Legal routes: `recursive_improvement_pressures_analyzed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
  - Evidence expectation: rank concrete improvement candidates across workflow portfolio, workflow packages, eval/refinement/decomposition follow-through, composition/escalation policy, and organization-level operating patterns
  - Forbidden/out of scope: do not publish the final cycle package yet, and do not auto-run downstream workflows or invent runtime-owned scoring

- `prompts/analyze_verifier.md`
  - Role: `recursive-improvement verifier`
  - Required reads: analysis inputs plus `company_pressure_map.md`, `recursive_improvement_priority_matrix.md`, and `recursive_improvement_candidates.json`
  - Required writes: verifier control metadata only through `RecursiveImprovementAnalysisPayload`
  - Legal routes: `recursive_improvement_pressures_analyzed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
  - Evidence expectation: confirm that each priority is evidence-backed, non-duplicative, and explicitly sequenced
  - Forbidden/out of scope: do not approve unsupported priorities, and do not collapse disagreements into generic "monitor later" prose

- `prompts/package_producer.md`
  - Role: `cycle packager`
  - Required reads: snapshots, framing artifacts, analysis artifacts, and checklist asset
  - Required writes: `recursive_improvement_cycle.md`, `recursive_improvement_summary.json`, and `recursive_improvement_next_actions.md`
  - Legal routes: `recursive_improvement_cycle_ready`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
  - Evidence expectation: publish a concrete prioritized cycle package with sequencing, rationale, and explicit downstream handoffs
  - Forbidden/out of scope: do not auto-run any downstream workflow, do not mutate authoritative workflow packages, and do not treat JSON summary prose as a substitute for explicit markdown artifacts

- `prompts/package_verifier.md`
  - Role: `cycle-package verifier`
  - Required reads: packaging inputs plus `recursive_improvement_cycle.md`, `recursive_improvement_summary.json`, and `recursive_improvement_next_actions.md`
  - Required writes: verifier control metadata only through `RecursiveImprovementCyclePayload`
  - Legal routes: `recursive_improvement_cycle_ready`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
  - Evidence expectation: confirm the package is concrete, internally consistent, and still stops at publication rather than hidden downstream execution
  - Forbidden/out of scope: do not approve summary drift, missing priority categories, or next actions that silently imply runtime-owned automation

- `prompts/README.md`
  - Required contents: concise index of the six prompts, the step-to-artifact map, reserved/application route grammar, verifier JSON expectations, and the rule that provider-facing SOP lives in prompts while the runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive company-operation snapshot seam | Gives company-level workflows a reusable, inspectable way to capture task history, task messages, and per-task workflow telemetry under `ctx.workflow_folder` without widening runtime-owned behavior | Adds one focused read-only workspace summary surface plus one stdlib helper, but keeps prioritization policy visible in workflow code and prompts | Chosen |
| Overload `write_workflow_portfolio_health_snapshot(...)` with company/task history | Reuses an existing helper name and may reduce helper count | Blurs portfolio versus company scope, mixes two evidence surfaces into one contract, and makes later workflow pressure harder to reason about | Rejected |
| Runtime-owned company learner or automatic cycle launcher | Could reduce workflow-local code in the short term | Hides workflow meaning in runtime code, widens persisted behavior, and violates the rule that workflows own the global SOP and terminal boundary | Rejected |

## Chosen framework improvement contract

### Files and interfaces

- `runtime/workspace.py`
  - add a read-only `TaskRecord` dataclass mirroring the existing `RunRecord` discipline for task metadata and source paths
  - add `list_task_records(root: Path, *, task_ids: Iterable[str] | None = None) -> tuple[TaskRecord, ...]`
  - add `list_task_operation_summaries(root: Path, *, task_ids: Iterable[str] | None = None, workflow_names: Iterable[str] | None = None, statuses: str | Iterable[str] | None = None, max_tasks: int | None = None, max_runs_per_workflow: int | None = None, max_messages_per_task: int | None = None) -> tuple[dict[str, Any], ...]`
  - behavior requirements:
    - reuse existing task metadata, `request.md`, `messages.jsonl`, and `list_run_records(...)`
    - remain read-only against `.autoloop/`
    - sort deterministically by recent activity
    - publish bounded excerpts plus authoritative source paths instead of raw full-history payloads

- `stdlib/company.py`
  - add `write_company_operation_snapshot(ctx, task_ids=None, workflows=None, statuses=None, max_tasks=None, max_runs_per_workflow=None, max_messages_per_task=None, relative_path="company_operation_snapshot.json") -> Path`
  - behavior requirements:
    - write only under `ctx.workflow_folder`
    - package filters, task summaries, per-task workflow telemetry, recent message excerpts, and source-path pointers
    - keep company-level policy out of the helper

- `stdlib/__init__.py`
  - export `write_company_operation_snapshot`

- `docs/authoring.md`
  - document the new helper boundary as authoring-only, additive, read-only, and non-goal for runtime-owned governance or automatic execution

### Compatibility notes

- No public CLI behavior changes.
- No changes to persisted task/run/session payload contracts beyond additive read-only summary helpers.
- No new `workflow.toml` semantics beyond the new workflow package manifest.
- No changes to provider/session/resume contracts.
- The request snapshot's stale `src/autoloop/...` references should be treated as planning-time mapping only; cycle 12 should not claim recursive wrapper cleanup unless `recursive_autoloop/` is intentionally touched.

### Regression surfaces to guard

- `runtime/workspace.py` read-only listing logic must stay compatible with existing task/run metadata and sorting behavior.
- The new helper must not mutate `task.json`, `messages.jsonl`, run metadata, or workflow packages.
- The new workflow must stop at published cycle packaging and must not auto-run builder, diagnostics, governance, refinement, or decomposition workflows.
- Prompt contracts must keep provider-facing SOP in the prompt files and keep runtime control limited to `expected_output_schema`, `available_routes`, and `route_contracts`.

## Meaningful design decisions

### 1. Evidence-capture boundary

- Alternatives considered:
  - workflow-only ad hoc `.autoloop` scraping inside the new package
  - one new company-operation helper plus reuse of existing capability and portfolio-health helpers
  - one mega-helper that collapses capability, portfolio health, and company history into one artifact
- Selected: add one focused company-operation helper and reuse the existing capability and portfolio-health helpers
- Why: it keeps the framework change narrow, preserves existing helper meanings, and makes the company-level workflow composition explicit instead of hiding it in a single broad snapshot.

### 2. Company snapshot granularity

- Alternatives considered:
  - embed full raw request, message, and event histories for every task
  - publish only aggregate counts with no message/request context
  - publish bounded task summaries with request excerpts, recent message excerpts, per-task workflow run summaries, and authoritative source paths
- Selected: bounded summaries plus source paths
- Why: the top-level learner needs enough context to spot operating pressure without exploding artifact size or duplicating the lower-level run-history diagnostic seam.

### 3. Terminal boundary

- Alternatives considered:
  - auto-run downstream authoring, governance, refinement, or decomposition workflows from the package
  - stop after raw analysis artifacts only
  - stop at a published recursive-improvement cycle package plus explicit next actions and receipt
- Selected: stop at a published cycle package plus explicit next actions and receipt
- Why: it keeps later execution explicit and inspectable while still producing a concrete terminal package another operator or workflow can consume immediately.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc `.autoloop` scraping | Build the new workflow directly against raw task/run files and keep all capture logic inside `workflow.py` | Smallest initial diff, but duplicates workspace logic and weakens inspectability and reuse | Rejected |
| Shared company snapshot seam plus dedicated workflow package | Reuse existing capability/portfolio-health helpers, add one focused task/company summary seam, and keep recursive-learning policy visible in the new workflow package | Slightly broader change set, but it is the clearest reusable and inspectable design | Selected |
| Runtime-owned company learner subsystem | Move task/workflow analysis and recursive-priority logic into runtime code | Hides workflow meaning in framework code and widens runtime semantics prematurely | Rejected |

## Milestones

1. Add the additive company-operation snapshot seam in `runtime/workspace.py`, `stdlib/company.py`, `stdlib/__init__.py`, and `docs/authoring.md`, with focused unit/runtime coverage.
2. Ship `workflows/company_operation_to_recursive_improvement_cycle/`, its prompts/assets/contracts/params/docs, and workflow-specific runtime proof.
3. Update `.autoloop_recursive/` memory and `tests/test_architecture_baseline_docs.py`, then run the targeted closeout suite and record any unchanged out-of-scope residuals explicitly.

## Validation plan

- Framework seam:
  - `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workspace_and_context.py`
- New workflow:
  - `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- Recursive baseline closeout:
  - `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/test_architecture_baseline_docs.py`

## Risk register

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Company snapshot seam absorbs policy | A helper that ranks or interprets company pressure would violate the workflow/runtime boundary | Keep the helper read-only and summary-only; enforce that prioritization stays in workflow prompts and artifacts |
| Snapshot payload grows too large or noisy | Full raw histories would make artifacts hard to inspect and tests brittle | Bound `max_tasks`, `max_runs_per_workflow`, and `max_messages_per_task`; publish excerpts and source paths instead of full raw logs |
| New workflow duplicates existing governance/diagnostic logic | Cycle 12 would add technical debt instead of a top-level consumer layer | Reuse existing capability and portfolio-health helpers explicitly, and treat company snapshot as the only new capture seam |
| Hidden downstream execution leaks into the package | The workflow would stop being a clear terminal artifact boundary | Add prompt/package verifier checks and publish-side validation that reject auto-run wording or implicit execution |
| Recursive-memory baseline drifts from shipped behavior | Later cycles would inherit stale guidance and tests would become misleading | Update `.autoloop_recursive/` and `tests/test_architecture_baseline_docs.py` in the same slice as code and proof |
