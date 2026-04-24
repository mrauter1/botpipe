# Cycle 10 Plan

## Scope considered

- Authoritative inputs reviewed: the immutable request snapshot, the current run raw log, the standing recursive-memory files, the current repo-root framework/docs/workflow packages, and the empty cycle-10 plan artifacts.
- No clarifications were appended after run start, so the initial request snapshot remains authoritative for this turn.
- The request snapshot's mandatory inspection paths are stale in this checkout. The current authoritative equivalents are repo-root `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `stdlib/`, and repo-root `workflows/`.
- The worktree is dirty from the package-layout migration and earlier cycles. Cycle 10 implementation must stay scoped to the paired governance workflow, its narrow framework seam, targeted proof/docs, and the required recursive-memory files; unrelated dirty files remain out of scope.
- In scope:
- ship one new high-value workflow package
- ship one paired framework improvement that keeps runtime/provider boundaries narrow and mechanical
- update workflow docs, authoring docs, targeted tests, architecture-baseline docs, and `.autoloop_recursive/` memory in the same change set
- Out of scope:
- `recursive_autoloop/` wrapper/template cleanup
- public CLI, workspace-layout, provider, session, or manifest-contract changes
- runtime-owned governance scoring, automatic workflow retirement/creation, or hidden downstream execution
- builder replacement work unless implementation uncovers a concrete builder defect severe enough to block the chosen cycle-10 addition

## Current findings

- `workflow_idea_to_workflow_package` remains a credible workflow-builder baseline. The package, decision-record doc, and runtime proof in `tests/runtime/test_workflow_builder_package.py` satisfy the current builder standard, so cycle 10 does not need another builder-first addition.
- The portfolio now has a visible builder, front door, candidate retrieval, adaptation planning, evaluation-suite authoring, refinement publication, and run-history diagnostics. The clearest missing layer is portfolio governance that turns those surfaces into an explicit operating recommendation.
- The roadmap, charter, and candidate ledger already converge on `workflow_portfolio_to_operating_system` as the strongest deferred follow-on after cycle 9.
- Existing reusable seams already cover light portfolio discovery, rich workflow capability inspection, selected-workflow authoring surfaces, and selected-workflow run-history snapshots, but there is no reusable authoring seam for publishing cross-portfolio run-health evidence without ad hoc `.autoloop` scraping in the workflow package.
- `runtime/workspace.py` already exposes read-only run enumeration through `list_run_records(...)`, so the clean framework move is additive portfolio run-health summarization rather than a new runtime-owned governance subsystem.

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline and still the greenfield path when the portfolio has a real authoring gap | Already credible in code, docs, and tests, so another builder-first cycle would delay the higher-value governance gap | Deferred |
| `workflow_package_to_composable_building_blocks` | Valuable decomposition layer for extracting reusable units from monolithic workflows | Strong follow-on, but lower leverage until the portfolio first has an explicit governance package that identifies which workflows should be decomposed, merged, or retired | Deferred |
| `workflow_portfolio_to_operating_system` | Turns the current workflow portfolio into an explicit operating recommendation covering create/keep/refine/decompose/retire priorities | Requires a narrow cross-portfolio health snapshot seam plus a disciplined terminal governance boundary, but it directly fills the next missing recursive layer | Chosen |

### Why the chosen addition wins

- Problem solved: convert the current workflow catalog, compiled step contracts, and historical run-health signals into a durable portfolio-governance package instead of ad hoc repo review and chat recommendations.
- Likely sponsors: workflow maintainers, engineering-productivity owners, AI platform teams, PM/TPM leads, and recursive portfolio operators.
- Classification: end-to-end workflow.
- Why Autoloop fits: the work depends on durable portfolio evidence capture, verifier-gated governance reasoning, explicit next-action packaging, and a terminal artifact set other operators or workflows can inspect later.
- Why one-shot is insufficient: credible governance needs explicit scope framing, cross-workflow evidence capture, lifecycle analysis, prioritization, contradiction handling, and a publication gate with bounded rework versus replan.
- Terminal outcome: a workflow-local governance package that recommends which workflows to keep, create next, refine, decompose, merge, or retire, plus a machine-readable summary, explicit next actions, and a deterministic receipt.

## Chosen addition contract

- Package path: `workflows/workflow_portfolio_to_operating_system/`
- Discovery target: `autoloop workflows show workflow_portfolio_to_operating_system`
- Direct invocation:

```bash
autoloop run workflow_portfolio_to_operating_system <task-id> \
  --message "Recommend how the current workflow portfolio should evolve for the next recursive cycle." \
  -wf task_title "Workflow portfolio operating-system review" \
  -wf sponsor_role "workflow platform" \
  -wf desired_outcome "Publish a portfolio-governance package with explicit create/refine/decompose/retire priorities." \
  -wf decision_drivers "Prioritize recursive leverage and reusable value." \
  -wf decision_drivers "Prefer explicit governance over hidden runtime automation." \
  -wf constraints "Keep runtime control narrow and stop at governance publication." \
  -wf focus_workflows workflow_idea_to_workflow_package \
  -wf focus_workflows workflow_run_history_to_failure_modes \
  -wf max_runs_per_workflow 10
```

- Parameters:
- `task_title` required
- `sponsor_role` optional
- `desired_outcome` optional
- `decision_drivers` optional and repeatable
- `constraints` optional and repeatable
- `focus_workflows` optional and repeatable
- `max_runs_per_workflow` optional, default `10`

### Workflow objective

Turn the current workflow portfolio into a verifier-gated operating-system package that recommends what should exist, what should change, and what should happen next without auto-running downstream authoring, refinement, or retirement work.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture authoritative workflow-local snapshots of the current workflow capability surface and portfolio run-health summary.
- Keep portfolio framing, governance analysis, and operating-system packaging as separate work items.
- Require explicit create/refine/decompose/merge/retire recommendations instead of hidden downstream execution.
- Publish only after the capability snapshot, health snapshot, governance analysis artifacts, terminal package, and receipt all exist and agree.

### Provider-owned cognitive responsibilities

- Frame the portfolio-governance problem, including scope, sponsor pressure, and decision criteria.
- Interpret cross-workflow fit, overlap, health pressure, and coverage gaps.
- Decide which workflows should be kept stable, refined, decomposed, merged, retired, or prioritized next.
- Package explicit next actions for later workflow authoring, refinement, or governance follow-through.

### Work-item boundary doctrine

- `capture_portfolio_context`: deterministic evidence capture only.
- `frame_portfolio_governance`: decide the governance scope, decision axes, and acceptance surface only.
- `analyze_portfolio_operating_model`: assess coverage, overlap, run-health pressure, and lifecycle recommendations only.
- `package_portfolio_operating_system`: publish the terminal governance package and next actions only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the portfolio scope, evidence boundary, or governance surface changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_portfolio_context`
- `portfolio governance framer` / `governance-scope verifier`
- `portfolio operating analyst` / `portfolio-governance verifier`
- `portfolio operating-system packager` / `operating-system verifier`
- deterministic `publish_portfolio_operating_system`

### Planned control flow

1. `bootstrap`
2. `capture_portfolio_context`
3. `frame_portfolio_governance`
4. `analyze_portfolio_operating_model`
5. `package_portfolio_operating_system`
6. `publish_portfolio_operating_system`

### Planned route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `portfolio_context_captured`
- `portfolio_governance_framed`
- `portfolio_operating_model_analyzed`
- `portfolio_operating_system_ready`
- `portfolio_operating_system_published`
- `needs_rework`
- `needs_replan`

### Planned artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_portfolio_context` | request, invocation contract, focus/max-run parameters | `workflow_capability_snapshot.json`, `workflow_portfolio_health_snapshot.json` | authoritative portfolio capability and run-health evidence bundle |
| `frame_portfolio_governance` | request, invocation contract, capability snapshot, health snapshot, framework docs | `portfolio_scope_brief.md`, `governance_decision_axes.md` | authoritative governance framing and acceptance boundary |
| `analyze_portfolio_operating_model` | invocation contract, capability snapshot, health snapshot, framing artifacts | `workflow_lifecycle_matrix.md`, `portfolio_gap_analysis.md`, `portfolio_change_candidates.json` | authoritative cross-portfolio lifecycle, gap, and change-candidate analysis |
| `package_portfolio_operating_system` | capability snapshot, health snapshot, framing artifacts, analysis artifacts, checklist | `workflow_portfolio_operating_system.md`, `portfolio_operating_summary.json`, `portfolio_next_actions.md` | authoritative terminal governance package and explicit next-action surface |
| `publish_portfolio_operating_system` | capability snapshot, health snapshot, analysis artifacts, package artifacts | `portfolio_operating_system_receipt.json` | deterministic terminal receipt proving the governance package is explicit and publication-ready |

### Planned runtime-injected control contract

The workflow must continue using only:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `PortfolioGovernanceFramingPayload`
- `PortfolioOperatingModelPayload`
- `PortfolioOperatingSystemPayload`

### Planned step prompt contracts

- `prompts/frame_producer.md`
- Role: `portfolio governance framer`
- Required reads: `request.md`, `invocation_contract.json`, `workflow_capability_snapshot.json`, `workflow_portfolio_health_snapshot.json`, `docs/architecture.md`, and `docs/authoring.md`
- Required writes: `portfolio_scope_brief.md` and `governance_decision_axes.md`
- Legal routes: `portfolio_governance_framed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: make the portfolio scope, sponsor goals, decision drivers, and acceptable operating recommendations explicit enough for cross-workflow analysis
- Forbidden/out of scope: do not rank workflows yet, do not mutate workflow packages, and do not assume hidden runtime governance or lifecycle metadata

- `prompts/frame_verifier.md`
- Role: `governance-scope verifier`
- Required reads: the same framing inputs plus `portfolio_scope_brief.md` and `governance_decision_axes.md`
- Required writes: verifier control metadata only through `PortfolioGovernanceFramingPayload`; leave source artifacts untouched unless local repair is requested through `needs_rework`
- Legal routes: `portfolio_governance_framed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: confirm the governance scope is coherent, evidence-backed, and still local to the same portfolio boundary unless a real replan is required
- Forbidden/out of scope: do not author lifecycle recommendations, and do not approve framing that leaves coverage, overlap, or health criteria ambiguous

- `prompts/analyze_producer.md`
- Role: `portfolio operating analyst`
- Required reads: capability snapshot, health snapshot, `portfolio_scope_brief.md`, and `governance_decision_axes.md`
- Required writes: `workflow_lifecycle_matrix.md`, `portfolio_gap_analysis.md`, and `portfolio_change_candidates.json`
- Legal routes: `portfolio_operating_model_analyzed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: assess coverage, overlap, recursive leverage, and run-health pressure per workflow; recommend keep/refine/decompose/merge/retire/create-next postures with explicit evidence
- Forbidden/out of scope: do not write the final governance package yet, do not auto-run diagnostics or refinement workflows, and do not invent runtime-owned scoring systems

- `prompts/analyze_verifier.md`
- Role: `portfolio-governance verifier`
- Required reads: the analysis inputs plus `workflow_lifecycle_matrix.md`, `portfolio_gap_analysis.md`, and `portfolio_change_candidates.json`
- Required writes: verifier control metadata only through `PortfolioOperatingModelPayload`; leave analysis artifacts intact unless local repair is requested through `needs_rework`
- Legal routes: `portfolio_operating_model_analyzed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: confirm the lifecycle matrix and gap analysis are non-duplicative, portfolio-wide, and tied to explicit capability or run-health evidence
- Forbidden/out of scope: do not approve unsupported merge/retire/decompose claims, and do not collapse disagreement into vague "monitor later" prose

- `prompts/package_producer.md`
- Role: `portfolio operating-system packager`
- Required reads: capability snapshot, health snapshot, framing artifacts, analysis artifacts, and checklist asset
- Required writes: `workflow_portfolio_operating_system.md`, `portfolio_operating_summary.json`, and `portfolio_next_actions.md`
- Legal routes: `portfolio_operating_system_ready`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: publish the terminal governance package with explicit create/refine/decompose/merge/retire priorities, rationale, ordering, and handoff guidance
- Forbidden/out of scope: do not auto-run any child workflow, do not mutate the authoritative workflow packages, and do not treat machine-readable summary prose as a substitute for explicit markdown artifacts

- `prompts/package_verifier.md`
- Role: `operating-system verifier`
- Required reads: the packaging inputs plus `workflow_portfolio_operating_system.md`, `portfolio_operating_summary.json`, and `portfolio_next_actions.md`
- Required writes: verifier control metadata only through `PortfolioOperatingSystemPayload`; leave published artifacts intact unless local repair is requested through `needs_rework`
- Legal routes: `portfolio_operating_system_ready`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: confirm the package is concrete, evidence-backed, internally consistent, and still stops at governance publication rather than hidden downstream execution
- Forbidden/out of scope: do not approve summary drift, missing lifecycle postures, or next actions that silently imply runtime-owned automation

- `prompts/README.md`
- Required contents: one concise index of the six prompts, the step-to-artifact map, reserved/application route grammar, verifier JSON expectations, and the rule that prompt templates carry provider-facing guidance while the runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`

### Prompt/package expectations

- Prompt files: `prompts/frame_producer.md`, `prompts/frame_verifier.md`, `prompts/analyze_producer.md`, `prompts/analyze_verifier.md`, `prompts/package_producer.md`, `prompts/package_verifier.md`, and `prompts/README.md`
- Asset: `assets/portfolio_operating_system_checklist.md`
- Decision/evidence doc: `docs/workflows/workflow_portfolio_to_operating_system.md`
- Runtime proof: `tests/runtime/test_workflow_portfolio_to_operating_system.py`

### Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose typed route contracts for the three pair steps.
- Runtime proof must cover:
- successful terminal publication of `workflow_capability_snapshot.json`, `workflow_portfolio_health_snapshot.json`, `workflow_lifecycle_matrix.md`, `portfolio_gap_analysis.md`, `portfolio_change_candidates.json`, `workflow_portfolio_operating_system.md`, `portfolio_operating_summary.json`, `portfolio_next_actions.md`, and `portfolio_operating_system_receipt.json`
- deterministic capture of portfolio health evidence from the current `.autoloop` run records without mutating run state or workflow packages
- proof that the workflow stops at governance publication and does not auto-run workflow builder, refinement, diagnostics, or retirement work
- publish-step rejection of missing capability/health artifacts, unknown focus-workflow references, summary drift, invalid lifecycle postures, and next actions that imply hidden downstream execution

### Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, analysis, or packaging boundary.
- `needs_replan`: the portfolio scope, evidence boundary, or governance surface changed materially enough that earlier work must be revisited.
- `blocked`: a missing prerequisite or repository fact prevents a credible governance package.
- `failed`: irreconcilable contradictions make the current operating-system package non-credible.

### Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring path and was reconsidered before choosing this narrower governance layer.
- `workflow_run_history_to_failure_modes` remains the standing per-workflow diagnostic building block; this workflow may recommend it explicitly in next actions but must not auto-run it.
- `workflow_package_to_composable_building_blocks` remains a strong follow-on, but cycle 10 should first ship the reusable governance package that can prioritize where decomposition is worth doing.
- Promotion remains evidence-gated by workflow-local artifacts, deterministic publish-step validation, runtime tests, and recursive-memory closeout updates.

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive read-only portfolio health snapshot seam backed by shared run-summary logic | Gives governance workflows one reusable way to capture cross-portfolio run-health evidence under `ctx.workflow_folder` without widening CLI/runtime contracts or hiding governance policy in prompts | Adds a focused runtime read-model plus an authoring helper, but keeps ranking and lifecycle reasoning visible in workflow code and artifacts | Chosen |
| Expand `workflow.toml` or workflow docs with governance metadata such as lifecycle state, owner, or merge hints | Could make some governance inputs statically visible to tooling | Widens the metadata contract, forces repo-wide backfill, and pushes dynamic portfolio evidence into static files that will drift | Rejected |
| Runtime-owned governance index, scoring engine, or automatic operating recommendations | Could reduce workflow-local code in the short term | Hides workflow meaning in runtime code, widens persisted/runtime behavior, and violates the doctrine that workflows own the global SOP and terminal boundary | Rejected |

### Chosen framework slice

- Add a read-only summary helper in `runtime/workspace.py` for grouped portfolio run health, reusing `list_run_records(...)` and the existing workspace contract instead of inventing new persisted indexes.
- Extend `stdlib/portfolio.py` and `stdlib/__init__.py` with `write_workflow_portfolio_health_snapshot(...)`, which writes only under `ctx.workflow_folder` and publishes grouped per-workflow run-health evidence for the current repo.
- Keep capability inspection on the existing `write_workflow_capability_snapshot(...)` path; the new seam should complement it rather than replace or broaden it.
- Update `docs/authoring.md` to freeze the helper boundary and its non-goals.
- Add unit/runtime proof around the new read-only summary and helper behavior; do not change CLI behavior, workspace layout, or manifest semantics.

### Planned helper boundary

- Helper name: `write_workflow_portfolio_health_snapshot(...)`
- Inputs:
- workflow context `ctx`
- optional `focus_workflows`
- optional `max_runs_per_workflow`
- optional relative output path under `ctx.workflow_folder`
- Output artifact: `workflow_portfolio_health_snapshot.json`
- Required payload shape:
- repo/task/run/workflow metadata
- portfolio-level workflow count and filtered workflow count
- per-workflow grouped run counts by status
- recent run excerpts per workflow with `run_id`, `task_id`, `status`, `created_at`, `updated_at`, `pending_question`, and source-path references
- explicit `focus_workflows` and `max_runs_per_workflow` echo for inspectability
- Non-goals:
- no ranking, scoring, lifecycle decisions, or next-action text
- no mutation of `.autoloop` run state
- no new `workflow.toml` fields
- no automatic child-workflow execution

## Meaningful design decisions

### 1. Builder boundary

- Alternatives considered:
- revisit the builder as the cycle-10 addition
- pick the already-deferred governance layer because the builder is credible
- Selected: keep the existing builder baseline and ship the governance layer
- Why: the repo already has a documented and tested builder, while the missing leverage is now portfolio-level prioritization on top of the shipped recursive stack.

### 2. Evidence boundary

- Alternatives considered:
- auto-run `workflow_run_history_to_failure_modes` across multiple workflows
- add static governance metadata to manifests and docs
- combine the existing capability snapshot with a new read-only portfolio health snapshot seam
- Selected: capability snapshot plus new read-only portfolio health snapshot seam
- Why: it captures cross-portfolio evidence cleanly without hidden fanout, static-metadata drift, or runtime-owned governance policy.

### 3. Terminal boundary

- Alternatives considered:
- auto-run workflow creation, refinement, or retirement actions from the governance workflow
- stop at ad hoc governance prose only
- stop at a published operating-system package, machine-readable summary, explicit next actions, and receipt
- Selected: stop at governance publication
- Why: the workflow should make portfolio priorities explicit and auditable, not bury them inside hidden downstream execution.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc repo and `.autoloop` scraping inside the new package | Smallest diff, but duplicates portfolio/run parsing logic and weakens the authoring boundary | Rejected |
| Child-workflow fanout that runs diagnostics or strategy workflows across the portfolio before packaging | Could reuse existing workflows directly, but introduces hidden breadth, longer runtimes, and noisier failure modes for a first governance layer | Rejected |
| Shared portfolio health snapshot seam plus dedicated governance workflow package | Reuses existing capability inspection, adds one narrow run-health seam, and keeps governance meaning visible in package code, prompts, docs, and tests | Selected |

## Milestones

1. Add the portfolio health snapshot seam in runtime/stdlib/docs/tests without changing CLI, workspace layout, or manifest contracts.
2. Ship `workflow_portfolio_to_operating_system` with explicit prompts, contracts, docs, and runtime proof.
3. Update recursive memory, architecture-baseline docs/tests, and targeted regression proof so cycle 10 becomes the new explicit baseline.

## Compatibility and regression notes

- No public CLI, provider, session, workspace-layout, or `workflow.toml` contract changes are planned.
- The new helper must write only under `ctx.workflow_folder` and must not mutate workflow packages or `.autoloop` runtime state.
- The new workflow package is additive; existing workflows remain authoritative and unchanged.
- Shared regression surfaces to protect:
- `stdlib/portfolio.py` helper behavior
- `runtime/workspace.py` read-only run summary behavior
- workflow discovery/compilation for existing portfolio workflows
- exact-string recursive-memory and architecture-baseline expectations
- `recursive_autoloop/` wrapper/template drift remains known and intentionally out of scope.

## Validation plan

- Parse `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c10/plan/phase_plan.yaml` with `yaml.safe_load` after editing.
- Targeted proof should cover the new helper seam, the new governance workflow, shared workspace/helper regression surfaces, and recursive-memory baseline docs.
- Expected targeted pytest command:

```bash
.venv/bin/pytest -q \
  tests/unit/test_stdlib_and_extensions.py \
  tests/runtime/test_workspace_and_context.py \
  tests/runtime/test_workflow_portfolio_to_operating_system.py \
  tests/runtime/test_workflow_builder_package.py \
  tests/runtime/test_workflow_run_history_to_failure_modes.py \
  tests/test_architecture_baseline_docs.py
```

## Risk register

- Risk: the new helper grows into portfolio policy instead of a narrow read-only evidence seam.
- Mitigation: keep the payload mechanical, grouped by workflow and run metadata only; keep ranking, lifecycle postures, and prioritization in the workflow prompts/artifacts.
- Rollback: revert the additive run-summary helper, the new stdlib export/helper, the authoring doc update, and helper-specific tests together.

- Risk: governance analysis drifts into hidden downstream execution or mutates authoritative workflow packages.
- Mitigation: freeze the terminal boundary at package publication plus explicit next actions and add publish-time validation against hidden execution language and missing authoritative artifacts.
- Rollback: remove the new workflow package, workflow doc, and runtime test together if terminal publication proof does not hold.

- Risk: recursive-memory updates or baseline tests claim behavior that the implementation does not actually ship.
- Mitigation: update `.autoloop_recursive/*.md`, `docs/authoring.md`, and `tests/test_architecture_baseline_docs.py` in the same change set and run targeted pytest proof before closeout.
- Rollback: revert cycle-10 memory and baseline-test updates if they drift from the shipped helper/workflow behavior.
