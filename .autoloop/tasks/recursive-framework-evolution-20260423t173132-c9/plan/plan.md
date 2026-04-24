# Cycle 9 Plan

## Scope considered

- Authoritative inputs reviewed: the immutable request snapshot, the current run raw log, the standing recursive-memory files, the current repo-root framework/docs/workflow packages, and the empty cycle-9 plan artifacts.
- No clarifications were appended after run start, so the initial request snapshot remains authoritative for this turn.
- The request snapshot's mandatory inspection paths are stale in this checkout. The current authoritative equivalents are repo-root `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `stdlib/`, and repo-root `workflows/`.
- The worktree is dirty from the larger package-layout migration. Cycle 9 implementation must stay scoped to the paired diagnostic workflow, its narrow framework seam, proof/docs, and the required recursive-memory files; unrelated dirty files remain out of scope.
- In scope:
- ship one new high-value reusable workflow building block
- ship one paired framework improvement that keeps runtime/provider boundaries narrow and mechanical
- update workflow docs, authoring docs, targeted tests, architecture-baseline docs, and `.autoloop_recursive/` memory in the same change set
- Out of scope:
- `recursive_autoloop/` wrapper/template cleanup
- public CLI, workspace-layout, provider, session, or manifest-contract changes
- runtime-owned diagnostics automation, auto-refinement, or auto-promotion
- `workflow_portfolio_to_operating_system` or other broader portfolio-governance workflows this cycle

## Current findings

- `workflow_idea_to_workflow_package` remains a credible workflow-builder baseline. The package, decision-record doc, and runtime proof in `tests/runtime/test_workflow_builder_package.py` satisfy the current builder standard, so cycle 9 does not need another builder-first addition.
- The portfolio now has a visible builder, a front door, candidate retrieval, adaptation planning, evaluation-suite authoring, and refinement publication. The clearest missing layer is the diagnostic building block that turns accumulated run history into reusable failure-mode pressure.
- The roadmap, charter, and candidate ledger already converge on `workflow_run_history_to_failure_modes` as the strongest deferred follow-on after cycle 8.
- Existing reusable seams already cover selected-workflow capability snapshots and selected-workflow authoring surfaces, but there is no equivalent narrow seam for gathering one workflow's historical run evidence into a stable workflow-local artifact.
- `runtime/workspace.py` already provides read-only run enumeration through `list_run_records(...)`, but diagnostic workflows still lack a reusable way to turn `run.json`, `request.md`, `events.jsonl`, and `children.jsonl` into an explicit workflow-local snapshot without ad hoc repo scraping.

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline and still the greenfield path when the portfolio has a real authoring gap | Already credible in code, docs, and tests, so another builder-first cycle would delay the stronger diagnostic gap | Deferred |
| `workflow_portfolio_to_operating_system` | Valuable governance workflow for merging, retiring, and sequencing workflows at the portfolio level | High leverage, but premature until the repo can first cluster workflow run history into explicit failure-mode pressure | Deferred |
| `workflow_run_history_to_failure_modes` | Turns actual workflow run history into a reusable failure-mode package and ranked improvement pressure for later refinement or portfolio governance | Requires a narrow run-history snapshot seam plus disciplined diagnostic boundaries, but it directly fills the next missing layer in the recursive stack | Chosen |

### Why the chosen addition wins

- Problem solved: convert scattered run metadata, request snapshots, event logs, child-run outcomes, pauses, and failures into a durable failure-mode package another workflow or operator can consume.
- Likely sponsors: workflow maintainers, engineering-productivity owners, QA/reliability leads, AI platform teams, and recursive portfolio operators.
- Classification: reusable workflow building block.
- Why Autoloop fits: the work spans deterministic evidence capture, long-horizon diagnosis, verifier-gated clustering, durable filesystem artifacts, and explicit next-action packaging.
- Why one-shot is insufficient: credible diagnostics need bounded history selection, evidence capture, clustering, contradiction handling, severity ranking, and a publication gate with rework versus replan.
- Terminal outcome: a workflow-local run-history evidence snapshot, a failure-mode map, recurring weak-points package, severity-ranked improvement opportunities, explicit next-action recommendations, and a deterministic receipt.

## Chosen addition contract

- Package path: `workflows/workflow_run_history_to_failure_modes/`
- Discovery target: `autoloop workflows show workflow_run_history_to_failure_modes`
- Direct invocation:

```bash
autoloop run workflow_run_history_to_failure_modes <task-id> \
  --message "Diagnose why the release workflow keeps stalling across recent runs." \
  -wf selected_workflow release_candidate_to_go_no_go \
  -wf task_title "Release workflow failure-mode diagnosis" \
  -wf statuses failed \
  -wf statuses blocked \
  -wf statuses paused \
  -wf max_runs 25 \
  -wf sponsor_role "workflow platform" \
  -wf desired_outcome "Publish a reusable failure-mode package and ranked next actions for the selected workflow." \
  -wf constraints "Keep runtime control narrow, keep diagnostic artifacts workflow-local, and stop before refinement or promotion."
```

- Parameters:
- `selected_workflow` required
- `task_title` required
- `statuses` optional and repeatable
- `max_runs` optional, default `25`
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable

### Workflow objective

Turn one selected workflow's historical run evidence into a verifier-gated failure-mode package without widening runtime-owned diagnostics behavior and without auto-running downstream refinement or governance workflows.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture authoritative workflow-local snapshots of one selected workflow's compiled contract and filtered run history.
- Keep diagnostic framing, failure-mode mapping, and improvement packaging as separate work items.
- Require explicit severity-ranked next actions instead of hidden downstream execution.
- Publish only after the selected-workflow snapshot, run-history snapshot, failure-mode package, improvement package, and receipt all exist and agree.

### Provider-owned cognitive responsibilities

- Interpret recurring patterns across run requests, statuses, event traces, child-run outcomes, and workflow-local evidence.
- Decide which failures are distinct modes versus repeated symptoms of the same mode.
- Rank severity, frequency, and leverage of improvement opportunities.
- Produce explicit next actions for later refinement or broader portfolio decisions.

### Work-item boundary doctrine

- `capture_run_history_context`: deterministic evidence capture only.
- `frame_diagnostic_scope`: decide the diagnostic boundary, relevant evidence windows, and acceptance surface only.
- `map_failure_modes`: cluster failures and recurring weak points only.
- `package_improvement_pressure`: rank opportunities and publish next actions only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the selected workflow, diagnostic boundary, or evidence graph changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_run_history_context`
- `workflow diagnostics framer` / `diagnostic-scope verifier`
- `failure-mode analyst` / `failure-mode verifier`
- `improvement strategist` / `diagnostic-package verifier`
- deterministic `publish_failure_mode_package`

### Planned control flow

1. `bootstrap`
2. `capture_run_history_context`
3. `frame_diagnostic_scope`
4. `map_failure_modes`
5. `package_improvement_pressure`
6. `publish_failure_mode_package`

### Planned route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `run_history_context_captured`
- `diagnostic_scope_framed`
- `failure_modes_mapped`
- `improvement_pressure_packaged`
- `failure_mode_diagnostics_published`
- `needs_rework`
- `needs_replan`

### Planned artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_run_history_context` | request, invocation contract, selected workflow reference, filtered status/max-run parameters | `selected_workflow_capability.json`, `selected_workflow_run_history.json` | authoritative selected-workflow diagnostic input bundle |
| `frame_diagnostic_scope` | request, invocation contract, selected workflow snapshot, run-history snapshot, framework docs | `diagnostic_scope_brief.md`, `run_history_scope.md` | authoritative diagnostic framing and evidence boundary |
| `map_failure_modes` | invocation contract, selected workflow snapshot, run-history snapshot, framing artifacts | `failure_mode_map.md`, `failure_mode_manifest.json`, `recurring_weak_points.md` | authoritative failure clustering and weak-point package |
| `package_improvement_pressure` | selected workflow snapshot, run-history snapshot, framing artifacts, failure-mode artifacts | `improvement_opportunities.md`, `improvement_opportunities.json`, `diagnostic_next_actions.md` | authoritative severity-ranked improvement and next-action package |
| `publish_failure_mode_package` | selected workflow snapshot, run-history snapshot, failure-mode package, improvement package | `failure_mode_diagnostic_receipt.json` | deterministic terminal receipt proving the diagnostic package is explicit and publication-ready |

### Planned runtime-injected control contract

The workflow must continue using only:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `DiagnosticScopePayload`
- `FailureModeMapPayload`
- `ImprovementPressurePayload`

### Planned step prompt contracts

- `prompts/frame_producer.md`
- Role: `workflow diagnostics framer`
- Required reads: `request.md`, `invocation_contract.json`, `selected_workflow_capability.json`, `selected_workflow_run_history.json`, `docs/architecture.md`, and `docs/authoring.md`
- Required writes: `diagnostic_scope_brief.md` and `run_history_scope.md`
- Legal routes: `diagnostic_scope_framed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: make the selected workflow's purpose, the run-history window, the meaningful evidence signals, and the acceptance boundary explicit enough for clustering
- Forbidden/out of scope: do not cluster failure modes yet, do not mutate the selected workflow, and do not assume hidden runtime diagnostics support

- `prompts/frame_verifier.md`
- Role: `diagnostic-scope verifier`
- Required reads: the same framing inputs plus `diagnostic_scope_brief.md` and `run_history_scope.md`
- Required writes: verifier control metadata only through `DiagnosticScopePayload`; leave source artifacts untouched unless local repair is requested through `needs_rework`
- Legal routes: `diagnostic_scope_framed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: confirm the diagnostic scope is coherent, evidence-backed, and still local to the same selected workflow unless a real replan is required
- Forbidden/out of scope: do not author failure clusters or next actions, and do not approve framing that leaves evidence selection or acceptance ambiguous

- `prompts/analyze_producer.md`
- Role: `failure-mode analyst`
- Required reads: selected workflow snapshot, run-history snapshot, `diagnostic_scope_brief.md`, and `run_history_scope.md`
- Required writes: `failure_mode_map.md`, `failure_mode_manifest.json`, and `recurring_weak_points.md`
- Legal routes: `failure_modes_mapped`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: cluster distinct modes, cite the concrete run-history evidence behind each mode, and distinguish repeated symptoms from repeated root causes
- Forbidden/out of scope: do not rank implementation next actions yet, do not mutate source run data, and do not hide uncertainty behind generic failure labels

- `prompts/analyze_verifier.md`
- Role: `failure-mode verifier`
- Required reads: the analysis inputs plus `failure_mode_map.md`, `failure_mode_manifest.json`, and `recurring_weak_points.md`
- Required writes: verifier control metadata only through `FailureModeMapPayload`; leave analysis artifacts intact unless local repair is requested through `needs_rework`
- Legal routes: `failure_modes_mapped`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: confirm the clusters are non-duplicative, tied to explicit run-history evidence, and specific enough for ranked improvement pressure
- Forbidden/out of scope: do not approve unsupported causal claims, and do not convert a missing evidence problem into an implicit next-action package

- `prompts/package_producer.md`
- Role: `improvement strategist`
- Required reads: selected workflow snapshot, run-history snapshot, framing artifacts, and failure-mode artifacts
- Required writes: `improvement_opportunities.md`, `improvement_opportunities.json`, and `diagnostic_next_actions.md`
- Legal routes: `improvement_pressure_packaged`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: rank opportunities by severity and leverage, tie each one to explicit failure modes, and recommend whether the next move is refinement, evaluation, adaptation, or later portfolio governance
- Forbidden/out of scope: do not auto-run the next workflow, do not mutate the selected workflow package, and do not treat diagnostic prose as a substitute for explicit artifacts

- `prompts/package_verifier.md`
- Role: `diagnostic-package verifier`
- Required reads: the packaging inputs plus `improvement_opportunities.md`, `improvement_opportunities.json`, and `diagnostic_next_actions.md`
- Required writes: verifier control metadata only through `ImprovementPressurePayload`; leave published artifacts intact unless local repair is requested through `needs_rework`
- Legal routes: `improvement_pressure_packaged`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: confirm the ranked package is concrete, evidence-backed, and still stops at diagnostic publication rather than hidden downstream execution
- Forbidden/out of scope: do not approve vague "improve workflow" guidance, and do not let next actions silently widen into runtime-owned routing or promotion

- `prompts/README.md`
- Required contents: one concise index of the six prompts, the step-to-artifact map, reserved/application route grammar, verifier JSON expectations, and the rule that prompt templates carry provider-facing guidance while the runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`

### Prompt/package expectations

- Prompt files: `prompts/frame_producer.md`, `prompts/frame_verifier.md`, `prompts/analyze_producer.md`, `prompts/analyze_verifier.md`, `prompts/package_producer.md`, `prompts/package_verifier.md`, and `prompts/README.md`
- Asset: `assets/failure_mode_diagnostic_checklist.md`
- Decision/evidence doc: `docs/workflows/workflow_run_history_to_failure_modes.md`
- Runtime proof: `tests/runtime/test_workflow_run_history_to_failure_modes.py`

### Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose typed route contracts for the three pair steps.
- Runtime proof must cover:
- successful terminal publication of `selected_workflow_run_history.json`, `failure_mode_map.md`, `failure_mode_manifest.json`, `improvement_opportunities.md`, `improvement_opportunities.json`, `diagnostic_next_actions.md`, and `failure_mode_diagnostic_receipt.json`
- deterministic capture of filtered run-history evidence, including request text, parsed events, and parsed child-run records for the selected workflow
- proof that the workflow stops at diagnostic publication and does not mutate the selected workflow package or auto-run refinement
- publish-step rejection of empty filtered histories, selected-workflow mismatches between the capability snapshot and run-history snapshot, missing failure-mode or improvement artifacts, and outputs that leave workflow-local scope

### Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, analysis, or packaging boundary.
- `needs_replan`: the selected workflow, evidence boundary, or diagnostic surface changed materially enough that earlier work must be revisited.
- `blocked`: a missing prerequisite or repository fact prevents a credible diagnostic package.
- `failed`: irreconcilable contradictions make the current failure-mode package non-credible.

### Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring path and was reconsidered before choosing this narrower diagnostic layer.
- `workflow_and_eval_to_refined_workflow_package` remains the standing refinement consumer; this workflow must stop at diagnostics and explicit next-action packaging rather than auto-refining.
- `workflow_portfolio_to_operating_system` remains a strong follow-on, but cycle 9 should first ship the reusable diagnostic package it can consume later.
- Promotion remains evidence-gated by workflow-local artifacts, deterministic publish-step validation, runtime tests, and recursive-memory closeout updates.

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Authoring-only run-history snapshot seam backed by additive read-only run-record exposure | Gives diagnostic workflows one reusable way to snapshot a selected workflow's run history without widening runtime routing or mutating `.autoloop` state | Adds one focused stdlib seam plus small runtime-workspace path exposure, but keeps filtering, clustering, and improvement policy visible in workflow code and artifacts | Chosen |
| Persist richer diagnostic summaries in `run.json` or runtime-owned indexes | Could make future diagnostics faster and more centralized | Moves workflow meaning into runtime-owned state, widens persisted contracts, and adds migration/regression pressure for a problem that is still workflow-level | Rejected |
| No new seam; let workflows scrape `.autoloop/tasks/**` directly | Smallest initial diff | Duplicates parsing logic, hard-codes workspace layout into prompts/workflow code, and weakens inspectability and repeatability | Rejected |

### Chosen framework slice

- Extend `runtime/workspace.py` read-only run records with the source paths a diagnostic workflow needs for request, child-run, and parent metadata without changing public CLI or workspace layout semantics.
- Add `stdlib/diagnostics.py` and export it from `stdlib/__init__.py`.
- Reuse `resolve_workflow_reference(...)` and `list_run_records(...)`; do not duplicate workflow resolution or add manifest metadata.
- Planned helper surface:
- `write_selected_workflow_run_history_snapshot(ctx, workflow, *, statuses=None, max_runs=None, relative_path="selected_workflow_run_history.json")`
- Helper rules:
- write only workflow-local JSON under `ctx.workflow_folder`
- resolve the selected workflow through the shared loader
- enumerate existing run records for that workflow with deterministic filtering and sorting
- capture normalized run metadata plus request text, parsed `events.jsonl` entries, parsed `children.jsonl` entries when present, and authoritative source paths
- do not mutate `.autoloop` state, auto-rank failure modes, auto-run downstream workflows, or widen the runtime-injected control contract

## Meaningful design decisions

### 1. Workflow boundary

- Alternatives considered:
- ship `workflow_portfolio_to_operating_system` first
- repeat another builder-first workflow cycle
- ship `workflow_run_history_to_failure_modes` as the next reusable diagnostic building block
- Selected: ship `workflow_run_history_to_failure_modes`
- Why: the builder is already credible and the strongest leverage now is the missing diagnostic layer that later refinement and governance workflows can consume.

### 2. Evidence capture boundary

- Alternatives considered:
- let the provider scrape `.autoloop/tasks/**` directly during analysis
- persist richer runtime-owned diagnostic summaries or indexes during every run
- capture a deterministic workflow-local run-history snapshot through a narrow helper seam
- Selected: deterministic workflow-local run-history snapshot
- Why: it keeps evidence capture reusable and inspectable without widening runtime-owned behavior or forcing later workflows to rediscover raw run files ad hoc.

### 3. Terminal outcome boundary

- Alternatives considered:
- auto-run `workflow_and_eval_to_refined_workflow_package` when strong failure modes are found
- publish only a prose diagnostic memo
- publish a failure-mode package plus explicit next-action recommendations and stop there
- Selected: publish a failure-mode package plus explicit next-action recommendations
- Why: it preserves explicit workflow boundaries, keeps downstream execution deterministic and opt-in, and produces reusable artifacts for later refinement or governance workflows.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with direct filesystem scraping | Build the diagnostic workflow directly and let prompts/workflow code parse `.autoloop` files ad hoc | Smallest initial diff, but duplicates parsing logic and couples workflow semantics tightly to workspace layout | Rejected |
| Additive run-record path exposure plus stdlib diagnostics helper plus dedicated workflow package and runtime proof/docs | Add the narrow seam, build the workflow on top of it, and prove end-to-end diagnostic publication in temp repo runs | Slightly broader change set, but the clearest reusable and inspectable design | Selected |
| Runtime-owned diagnostics subsystem or automatic failure-mode indexing | Centralize diagnostics in runtime state and possibly auto-trigger downstream workflows | Hides workflow meaning in runtime machinery, expands persisted contracts, and exceeds this cycle's narrow framework-improvement scope | Rejected |

## Milestones

1. Add the read-only diagnostic snapshot seam in `runtime/workspace.py` and `stdlib/diagnostics.py`, export it, document the boundary in `docs/authoring.md`, and extend unit coverage.
2. Ship `workflow_run_history_to_failure_modes` with params, contracts, prompts, checklist asset, publish-side validation, workflow doc, and runtime proof.
3. Update `.autoloop_recursive/` memory, closeout/baseline tests, and targeted pytest proof so cycle 9 becomes the new explicit recursive baseline.

## Compatibility / regression controls

- No public CLI, provider, session, workspace, or manifest-contract changes are allowed in cycle 9.
- The runtime/provider boundary must remain the same narrow contract: `expected_output_schema`, `available_routes`, and `route_contracts`.
- The new helper seam must stay read-only and workflow-local; it must not mutate `.autoloop` state, selected workflow files, or add runtime-owned diagnostic policy.
- The diagnostic workflow must stop at package publication and explicit next-action recommendations; it must not auto-run refinement, portfolio governance, or workflow promotion.
- Filtered run-history snapshots must keep authoritative source paths and reject empty or mismatched selected-workflow evidence rather than silently fabricating diagnostic coverage.
- Architecture-baseline and recursive-memory tests are exact-string sensitive; updates to `docs/authoring.md` and `.autoloop_recursive/*.md` must land in lockstep with the new helper/workflow implementation.

## Risk register

1. Risk: the new helper seam grows into runtime-owned diagnostic policy instead of staying a narrow snapshot helper.
   - Control: freeze the helper boundary in `docs/authoring.md` and `tests/unit/test_stdlib_and_extensions.py`; keep ranking, clustering, and next-action policy in workflow code and prompts.
2. Risk: the failure-mode workflow overfits to only failed runs or duplicates repeated retries as distinct modes.
   - Control: support explicit status filters plus deterministic `max_runs`, require a separate `run_history_scope.md`, and demand evidence-backed clustering that distinguishes symptoms from modes.
3. Risk: large or noisy histories make snapshots expensive or unstable.
   - Control: bound snapshots through `max_runs`, deterministic sorting, and workflow-local publication of the exact selected history set so later steps do not infer hidden scope.
4. Risk: exact-string recursive-memory and baseline-doc tests drift from the actual shipped cycle-9 behavior.
   - Control: update `.autoloop_recursive/*.md`, `docs/authoring.md`, and `tests/test_architecture_baseline_docs.py` in the same phase and record the targeted pytest proof in the cycle-9 closeout updates.

## Validation / rollback

- Targeted proof command:

```bash
.venv/bin/pytest -q \
  tests/unit/test_stdlib_and_extensions.py \
  tests/runtime/test_workspace_and_context.py \
  tests/runtime/test_workflow_builder_package.py \
  tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py \
  tests/runtime/test_workflow_run_history_to_failure_modes.py \
  tests/test_architecture_baseline_docs.py
```

- Rollback plan:
- revert the additive run-record exposure, `stdlib/diagnostics.py`, its export, and the authoring-doc/unit-test updates together
- revert the new workflow package, workflow doc, and runtime test together
- revert cycle-9 recursive-memory and baseline-test updates if they claim behavior or proof the implementation does not actually ship
