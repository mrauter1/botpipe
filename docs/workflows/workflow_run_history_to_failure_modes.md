# `workflow_run_history_to_failure_modes`

`workflow_run_history_to_failure_modes` is a reusable diagnostic workflow building block that turns one selected workflow's historical run evidence into a failure-mode package, recurring weak points, ranked improvement pressure, and a deterministic publication receipt. It stops at diagnostic publication so later refinement, evaluation, or portfolio-governance work remains explicit and inspectable.

## Problem and value

- Problem solved: convert scattered run logs, request snapshots, child-run outcomes, pauses, and failures into a durable failure-mode package instead of ad hoc postmortem prose.
- Why it matters: once the portfolio can build, retrieve, adapt, evaluate, and refine workflows, the missing layer is explicit diagnosis of how workflows fail over time.
- Likely sponsors: workflow maintainers, engineering productivity owners, AI platform teams, QA and reliability leads, and recursive portfolio operators.
- Classification: reusable workflow building block.
- Why Autoloop fits: the work needs durable artifacts, verifier-gated rework loops, deterministic selected-workflow inspection, bounded run-history capture, and publication-time validation.
- Why one-shot is insufficient: credible diagnostics need an explicit evidence window, clustered failure modes, recurring weak points, ranked opportunities, and a receipt another operator or workflow can trust later.

## Invocation

- Package path: `autoloop/workflows/workflow_run_history_to_failure_modes/`
- Discovery: `autoloop workflows show workflow_run_history_to_failure_modes`
- Direct run:

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
  -wf constraints "Keep runtime control narrow and stop at diagnostic publication."
```

Params:

- `selected_workflow` required
- `task_title` required
- `statuses` optional and repeatable
- `max_runs` optional, default `25`
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline and still the greenfield path when the portfolio has a real authoring gap | Already credible in code, docs, and proof, so another builder-first cycle would delay the stronger diagnostic gap | Deferred |
| `workflow_portfolio_to_operating_system` | Valuable governance workflow for merging, retiring, and sequencing workflows at the portfolio level | High leverage, but premature until the repo can first cluster workflow run history into explicit failure-mode pressure | Deferred |
| `workflow_run_history_to_failure_modes` | Turns actual workflow run history into a reusable failure-mode package and ranked improvement pressure | Requires a narrow run-history snapshot seam plus disciplined diagnostic publication, but it directly fills the next missing recursive layer | Chosen and shipped in this phase |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive authoring-only run-history snapshot seam | Lets workflows capture one selected workflow's historical evidence under `ctx.workflow_folder` without ad hoc `.autoloop` scraping or runtime-owned diagnostics policy | Adds one focused stdlib seam plus docs/tests, but keeps diagnostic meaning visible in workflow code, prompt templates, and artifacts | Chosen in the paired framework slice and consumed here |
| Expand `workflow.toml` with diagnostic history metadata | Could expose some diagnostic metadata statically to tooling | Widens the manifest contract, pushes dynamic run evidence into static metadata, and hides workflow meaning outside the durable artifact package | Rejected |
| Runtime-owned diagnostic runner and automatic failure clustering | Could reduce workflow code in the short term | Hides policy in runtime code, blurs the runtime/provider boundary, and violates the rule that workflows own the global SOP and terminal outcome | Rejected |

## Meaningful design decisions

### 1. Input boundary

- Alternatives considered:
- force this workflow to compose the front door or retrieval layer every time
- require an upstream strategy artifact as the only legal entry point
- accept one explicit `selected_workflow` plus focused history-selection parameters
- Selected: explicit `selected_workflow` plus `statuses`, `max_runs`, and the standard task-context fields
- Why: it keeps the building block reusable both standalone and downstream of later orchestration layers without forcing redundant retrieval work.

### 2. Validation boundary

- Alternatives considered:
- let the provider write the final authoritative diagnostic package directly
- validate the run-history snapshot only and trust the provider-owned failure package afterward
- let the provider author the failure and improvement artifacts, then validate the selected-workflow match, filtered history, manifest structure, publication boundary, and receipt deterministically in the publish step
- Selected: provider-authored diagnostic package plus deterministic publish-step validation
- Why: publication becomes the guard against empty filtered histories, selected-workflow mismatches, missing artifacts, malformed machine-readable manifests, and hidden downstream execution.

### 3. Terminal boundary

- Alternatives considered:
- auto-run `workflow_and_eval_to_refined_workflow_package`
- auto-route into portfolio governance
- stop at a published diagnostic package plus explicit next actions and receipt
- Selected: stop at a published diagnostic package plus explicit next actions and receipt
- Why: it keeps later refinement or governance work explicit and inspectable while still producing a terminal artifact package that another team or workflow can use immediately.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc `.autoloop` scraping inside the workflow package | Build the package directly against raw workspace paths and JSONL parsing inside workflow code | Smallest diff, but duplicates logic already needed elsewhere and weakens the authoring boundary | Rejected |
| Shared diagnostic helper seam plus dedicated workflow package | Reuse the helper seam for authoritative history capture while keeping diagnostic policy visible in the workflow package, prompts, and docs | Slightly broader change set, but it is the clearest reusable and inspectable design | Selected |
| Absorb run-history diagnosis into the refinement or portfolio workflow packages | Reduce package count by folding diagnostics into a later workflow | Collapses boundaries and leaves no reusable diagnostic building block for later composition | Rejected |

## Workflow contract

### Objective

Turn one selected workflow's historical run evidence into a verifier-gated failure-mode package without auto-running refinement or widening runtime-owned diagnostic behavior.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture authoritative workflow-local snapshots of one selected workflow's compiled contract and filtered run history.
- Keep diagnostic framing, failure-mode mapping, and improvement packaging as separate work items.
- Require explicit ranked next actions instead of hidden downstream execution.
- Publish only after the selected-workflow snapshot, filtered history snapshot, failure-mode package, improvement package, and receipt all exist and agree.

### Provider-owned cognitive responsibilities

- Interpret recurring patterns across run requests, statuses, event traces, child-run outcomes, and parent-run context.
- Decide which failures are distinct modes versus repeated symptoms of the same mode.
- Rank improvement opportunities by severity and leverage.
- Recommend explicit next actions for later refinement, evaluation, or portfolio work.

### Work-item boundary doctrine

- `capture_run_history_context`: deterministic evidence capture only.
- `frame_diagnostic_scope`: decide the diagnostic boundary, filtered evidence window, and acceptance surface only.
- `map_failure_modes`: cluster failures and recurring weak points only.
- `package_improvement_pressure`: rank opportunities and publish next actions only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the selected workflow, evidence window, or diagnostic surface changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_run_history_context`
- `workflow diagnostics framer` / `diagnostic-scope verifier`
- `failure-mode analyst` / `failure-mode verifier`
- `improvement strategist` / `diagnostic-package verifier`
- deterministic `publish_failure_mode_package`

### Control flow

1. `bootstrap`
2. `capture_run_history_context`
3. `frame_diagnostic_scope`
4. `map_failure_modes`
5. `package_improvement_pressure`
6. `publish_failure_mode_package`

### Route grammar

Helper routes:

- `question` when provider questions are allowed by the interaction policy
- question routes use `outcome.route_fields.questions`; blocked and failed routes use nullable `outcome.route_fields.reason`

Application routes:

- `inputs_prepared`
- `run_history_context_captured`
- `diagnostic_scope_framed`
- `failure_modes_mapped`
- `improvement_pressure_packaged`
- `needs_rework`
- `needs_replan`
- `failure_mode_diagnostics_published`

Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_run_history_context` | request, invocation contract, selected-workflow reference, status filters, `max_runs` | `selected_workflow_capability.json`, `selected_workflow_run_history.json` | authoritative selected-workflow diagnostic input bundle |
| `frame_diagnostic_scope` | request, invocation contract, selected-workflow snapshot, run-history snapshot, framework docs | `diagnostic_scope_brief.md`, `run_history_scope.md` | authoritative diagnostic framing and evidence boundary |
| `map_failure_modes` | request, invocation contract, selected-workflow snapshot, run-history snapshot, framing artifacts | `failure_mode_map.md`, `failure_mode_manifest.json`, `recurring_weak_points.md` | authoritative failure clustering and weak-point package |
| `package_improvement_pressure` | request, invocation contract, selected-workflow snapshot, run-history snapshot, checklist, framing artifacts, failure package | `improvement_opportunities.md`, `improvement_opportunities.json`, `diagnostic_next_actions.md` | authoritative ranked improvement and next-action package |
| `publish_failure_mode_package` | selected-workflow snapshot, run-history snapshot, framing artifacts, failure package, improvement package | `failure_mode_diagnostic_receipt.json` | deterministic terminal receipt proving the diagnostic package is explicit and publication-ready |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `DiagnosticScopePayload`
- `FailureModeMapPayload`
- `ImprovementPressurePayload`

### Prompt templates

- `prompts/frame_producer.md`: role `workflow diagnostics framer`; frames the selected workflow, filtered run window, and diagnostic boundary without clustering yet.
- `prompts/frame_verifier.md`: role `diagnostic-scope verifier`; checks that the framing package is explicit enough for failure-mode clustering.
- `prompts/analyze_producer.md`: role `failure-mode analyst`; clusters distinct failure modes, writes the machine-readable manifest, and surfaces recurring weak points.
- `prompts/analyze_verifier.md`: role `failure-mode verifier`; checks that the clusters and weak points are evidence-backed and packaging-ready.
- `prompts/package_producer.md`: role `improvement strategist`; ranks improvement opportunities and writes the terminal diagnostic package.
- `prompts/package_verifier.md`: role `diagnostic-package verifier`; confirms the terminal package is publication-ready and still stops at diagnostic publication rather than hidden downstream execution.

## Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose typed route metadata and payload schemas for the three pair steps.
- Runtime proof must cover:
- successful publication of `selected_workflow_run_history.json`, `failure_mode_map.md`, `failure_mode_manifest.json`, `recurring_weak_points.md`, `improvement_opportunities.md`, `improvement_opportunities.json`, `diagnostic_next_actions.md`, and `failure_mode_diagnostic_receipt.json`
- deterministic capture of filtered run-history evidence, including request text, parsed events, parsed child-run records, and parsed parent-run metadata when present
- proof that the workflow stops at diagnostic publication and does not auto-run refinement or mutate the selected workflow package
- publish-side rejection of empty filtered histories, selected-workflow mismatches, missing diagnostic artifacts, and outputs that imply hidden downstream execution

## Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, mapping, or packaging boundary.
- `needs_replan`: the selected workflow, filtered history boundary, or diagnostic surface changed materially enough that earlier work must be revisited.
- When the workflow explicitly authors `blocked`, use it when a missing prerequisite or repository fact prevents a credible diagnostic package.
- When the workflow explicitly authors `failed`, use it when irreconcilable contradictions make the current failure-mode package non-credible.

## Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring baseline and was reconsidered before shipping this narrower diagnostic layer.
- The package relies on the cycle-9 `stdlib/diagnostics.py` seam instead of inventing runtime-owned diagnostics automation or widening `workflow.toml`.
- Later cycles can now layer `workflow_and_eval_to_refined_workflow_package` or broader portfolio operating workflows on top of an explicit failure-mode package instead of inferring failure pressure from raw run logs.

## Evidence

- Package implementation: `autoloop/workflows/workflow_run_history_to_failure_modes/`
- Shared diagnostic seam consumed: `stdlib/diagnostics.py`
- Workflow asset: `autoloop/workflows/workflow_run_history_to_failure_modes/assets/failure_mode_diagnostic_checklist.md`
- Workflow-specific proof: `tests/runtime/test_workflow_run_history_to_failure_modes.py`
- The scripted tests prove workflow discovery, compilation, terminal diagnostic publication, and publish-side rejection of empty filtered histories, selected-workflow mismatches, missing artifacts, and hidden downstream execution signals.
