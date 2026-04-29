# `workflow_portfolio_to_operating_system`

`workflow_portfolio_to_operating_system` is an end-to-end governance workflow that turns workflow capability and portfolio run-health evidence into explicit lifecycle recommendations, change candidates, a portfolio operating-system package, and a deterministic publication receipt. It stops at governance publication so later refinement, decomposition, merge, or retirement work remains explicit and inspectable.

## Problem and value

- Problem solved: convert a growing workflow portfolio into explicit keep/refine/decompose/merge/retire/create-next recommendations instead of ad hoc repo review and chat-only guidance.
- Why it matters: once the portfolio can build, retrieve, adapt, evaluate, refine, and diagnose workflows, the missing layer is durable portfolio governance that decides what should happen next across the ecosystem.
- Likely sponsors: workflow maintainers, engineering-productivity owners, AI platform teams, PM or TPM leads, and recursive portfolio operators.
- Classification: end-to-end workflow.
- Why Autoloop fits: the work needs durable evidence capture, verifier-gated rework loops, explicit lifecycle packaging, and a publication boundary another operator or workflow can trust later.
- Why one-shot is insufficient: credible governance requires scoped portfolio evidence, explicit lifecycle criteria, contradiction handling, machine-readable change candidates, and deterministic publication checks.

## Invocation

- Package path: `workflows/workflow_portfolio_to_operating_system/`
- Discovery: `autoloop workflows show workflow_portfolio_to_operating_system`
- Direct run:

```bash
autoloop run workflow_portfolio_to_operating_system <task-id> \
  --message "Recommend how the current workflow portfolio should evolve for the next recursive cycle." \
  -wf task_title "Workflow portfolio operating-system review" \
  -wf sponsor_role "workflow platform" \
  -wf desired_outcome "Publish a governance package with explicit lifecycle recommendations and next actions." \
  -wf decision_drivers "Prioritize recursive leverage and reusable value." \
  -wf decision_drivers "Keep governance explicit instead of runtime-owned automation." \
  -wf constraints "Keep runtime control narrow." \
  -wf constraints "Stop at governance publication." \
  -wf focus_workflows workflow_idea_to_workflow_package \
  -wf focus_workflows task_to_workflow_strategy \
  -wf focus_workflows workflow_run_history_to_failure_modes \
  -wf max_runs_per_workflow 10
```

Parameters:

- `task_title` required
- `sponsor_role` optional
- `desired_outcome` optional
- `decision_drivers` optional and repeatable
- `constraints` optional and repeatable
- `focus_workflows` optional and repeatable
- `max_runs_per_workflow` optional, default `10`

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline and still the greenfield path when the portfolio has a real authoring gap | Already credible in code, docs, and tests, so another builder-first cycle would delay the higher-value governance gap | Deferred |
| `workflow_package_to_composable_building_blocks` | Valuable decomposition layer for extracting reusable units from mature workflows | Strong follow-on, but lower leverage until the portfolio first has an explicit governance package that can justify where decomposition should happen | Deferred |
| `workflow_portfolio_to_operating_system` | Turns the current workflow portfolio into an explicit operating recommendation covering keep/refine/decompose/merge/retire/create-next priorities | Requires a narrow read-only portfolio-health seam plus disciplined publication rules, but it directly fills the next missing recursive layer | Chosen and shipped in this phase |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive read-only portfolio health snapshot seam backed by shared run-summary logic | Gives governance workflows one reusable way to capture cross-portfolio run-health evidence under `ctx.workflow_folder` without widening CLI/runtime contracts or hiding policy in prompts | Adds a focused runtime read model plus an authoring helper, but keeps ranking and lifecycle reasoning visible in workflow code and artifacts | Chosen in the paired framework slice and consumed here |
| Expand `workflow.toml` with governance metadata such as lifecycle state or owner | Could make some governance inputs statically visible to tooling | Widens the manifest contract, forces repo-wide backfill, and pushes dynamic portfolio evidence into static files that will drift | Rejected |
| Runtime-owned governance index, scoring engine, or automatic operating recommendations | Could reduce workflow-local code in the short term | Hides workflow meaning in runtime code, widens persisted behavior, and violates the rule that workflows own the global SOP and terminal boundary | Rejected |

## Meaningful design decisions

### 1. Scope boundary

- Alternatives considered:
- always analyze the entire discovered portfolio
- require one upstream routing artifact as the only legal entry point
- accept an optional scoped workflow set plus shared capability and health snapshots
- Selected: optional `focus_workflows` plus shared capability and portfolio-health snapshots
- Why: it keeps the workflow reusable both as a full-portfolio review and as a narrower governance pass without forcing redundant upstream composition.

### 2. Recommendation model

- Alternatives considered:
- publish only prose recommendations
- publish one machine-readable score per workflow
- publish a lifecycle matrix for current workflows plus a separate change-candidate manifest for create-next pressure
- Selected: explicit lifecycle matrix plus separate change-candidate manifest
- Why: current-workflow lifecycle posture and create-next pressure are related but not identical; separating them keeps governance semantics explicit and inspectable.

### 3. Terminal boundary

- Alternatives considered:
- auto-run refinement, builder, or decomposition workflows from the package
- auto-mutate workflow packages after publication
- stop at a published governance package plus explicit next actions and receipt
- Selected: stop at a published governance package plus explicit next actions and receipt
- Why: it keeps later execution explicit, visible, and reviewable while still producing a terminal package another operator or workflow can use immediately.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc `.autoloop` scraping inside the package | Build the package directly against raw workspace paths and JSON parsing inside workflow code | Smallest diff, but duplicates the portfolio-health seam and weakens the authoring boundary | Rejected |
| Shared portfolio-health seam plus dedicated governance workflow package | Reuse the helper seam for authoritative evidence capture while keeping lifecycle policy visible in the workflow package, prompts, and docs | Slightly broader change set, but it is the clearest reusable and inspectable design | Selected |
| Runtime-owned governance subsystem | Move portfolio scoring and lifecycle recommendation logic into runtime code | Collapses the workflow/runtime boundary and hides the governance SOP where operators cannot inspect it easily | Rejected |

## Workflow contract

### Objective

Turn workflow capability and portfolio run-health evidence into a verifier-gated governance package that recommends what should stay stable, what should change, and what should happen next without auto-running downstream workflows.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture authoritative workflow-local snapshots of the current workflow capability surface and scoped portfolio run-health summary.
- Keep governance framing, lifecycle analysis, and governance packaging as separate work items.
- Require explicit lifecycle and create-next recommendations instead of hidden downstream execution.
- Publish only after the capability snapshot, health snapshot, lifecycle matrix, gap analysis, change-candidate manifest, governance package, summary, next actions, and receipt all exist and agree.

### Provider-owned cognitive responsibilities

- Frame the governance problem, including sponsor pressure, scope, and decision criteria.
- Interpret cross-workflow overlap, run-health pressure, fragility, and missing-capability signals.
- Decide which current workflows should be kept stable, refined, decomposed, merged, or retired.
- Decide which create-next candidates deserve explicit follow-through next.

### Work-item boundary doctrine

- `capture_portfolio_context`: deterministic evidence capture only.
- `frame_portfolio_governance`: define the governance scope, sponsor pressure, and lifecycle decision criteria only.
- `analyze_portfolio_operating_model`: assign lifecycle postures and create-next candidates only.
- `package_portfolio_operating_system`: publish the terminal governance package and explicit next actions only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the scope, evidence boundary, or governance objective changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_portfolio_context`
- `portfolio-governance framer` / `portfolio-governance verifier`
- `portfolio operating-model analyst` / `portfolio operating-model verifier`
- `portfolio operating-system packager` / `operating-system package verifier`
- deterministic `publish_portfolio_operating_system`

### Control flow

1. `bootstrap`
2. `capture_portfolio_context`
3. `frame_portfolio_governance`
4. `analyze_portfolio_operating_model`
5. `package_portfolio_operating_system`
6. `publish_portfolio_operating_system`

### Route grammar

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
- `needs_rework`
- `needs_replan`
- `portfolio_operating_system_published`

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local invocation snapshot |
| `capture_portfolio_context` | request, invocation contract, optional focus-workflow references, `max_runs_per_workflow` | `workflow_capability_snapshot.json`, `workflow_portfolio_health_snapshot.json` | authoritative scoped portfolio evidence bundle |
| `frame_portfolio_governance` | request, invocation contract, capability snapshot, health snapshot, framework docs | `portfolio_governance_brief.md`, `portfolio_decision_criteria.md` | authoritative governance scope and lifecycle criteria |
| `analyze_portfolio_operating_model` | request, invocation contract, capability snapshot, health snapshot, framing artifacts | `workflow_lifecycle_matrix.md`, `portfolio_gap_analysis.md`, `portfolio_change_candidates.json` | authoritative lifecycle recommendations and create-next candidates |
| `package_portfolio_operating_system` | request, invocation contract, capability snapshot, health snapshot, checklist, framing artifacts, lifecycle analysis artifacts | `workflow_portfolio_operating_system.md`, `portfolio_operating_summary.json`, `portfolio_next_actions.md` | authoritative terminal governance package |
| `publish_portfolio_operating_system` | capability snapshot, health snapshot, lifecycle analysis artifacts, terminal governance package | `portfolio_operating_system_receipt.json` | deterministic terminal receipt proving the governance package is explicit and publication-ready |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `PortfolioGovernanceFramingPayload`
- `PortfolioOperatingModelPayload`
- `PortfolioOperatingSystemPayload`

### Prompt templates

- `prompts/frame_producer.md`: role `portfolio-governance framer`; frames the scoped workflow set, sponsor pressure, and lifecycle decision criteria.
- `prompts/frame_verifier.md`: role `portfolio-governance verifier`; checks that the governance scope and decision criteria are explicit enough for lifecycle analysis.
- `prompts/analyze_producer.md`: role `portfolio operating-model analyst`; writes the lifecycle matrix, gap analysis, and machine-readable change candidates.
- `prompts/analyze_verifier.md`: role `portfolio operating-model verifier`; checks that the lifecycle recommendations and change candidates are evidence-backed and portfolio-wide.
- `prompts/package_producer.md`: role `portfolio operating-system packager`; publishes the governance package, summary, and explicit next actions.
- `prompts/package_verifier.md`: role `operating-system package verifier`; confirms the package is publication-ready and still stops at governance publication rather than hidden downstream execution.

## Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose typed route metadata and payload schemas for the three pair steps.
- Runtime proof must cover:
- successful publication of `workflow_capability_snapshot.json`, `workflow_portfolio_health_snapshot.json`, `workflow_lifecycle_matrix.md`, `portfolio_gap_analysis.md`, `portfolio_change_candidates.json`, `workflow_portfolio_operating_system.md`, `portfolio_operating_summary.json`, `portfolio_next_actions.md`, and `portfolio_operating_system_receipt.json`
- deterministic capture of grouped portfolio run-health evidence from the current `.autoloop` run records without mutating run state or workflow packages
- proof that the workflow stops at governance publication and does not auto-run builder, refinement, decomposition, merge, or retirement work
- publish-side rejection of missing capability or health artifacts, unknown focus-workflow references, summary drift, invalid lifecycle postures, and outputs that imply hidden downstream execution

## Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, lifecycle-analysis, or packaging boundary.
- `needs_replan`: the scoped workflow set, evidence boundary, or governance objective changed materially enough that earlier work must be revisited.
- `blocked`: a missing prerequisite or repository fact prevents a credible governance package.
- `failed`: irreconcilable contradictions make the current governance package non-credible.

## Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring baseline and was reconsidered before shipping this governance layer.
- The package consumes the cycle-10 portfolio-health seam rather than inventing runtime-owned governance scoring or widening `workflow.toml`.
- `workflow_package_to_composable_building_blocks` is now the clearest follow-on because this workflow can make decomposition pressure explicit without auto-running that downstream work.

## Evidence

- Package implementation: `workflows/workflow_portfolio_to_operating_system/`
- Shared seam consumed: `runtime/workspace.py` and `stdlib/portfolio.py`
- Workflow asset: `workflows/workflow_portfolio_to_operating_system/assets/portfolio_operating_system_checklist.md`
- Workflow-specific proof: `tests/runtime/test_workflow_portfolio_to_operating_system.py`
- The scripted tests prove workflow discovery, compilation, terminal governance publication, and publish-side rejection of missing scoped-evidence artifacts, unknown focus workflows, summary drift, invalid lifecycle postures, and hidden downstream execution signals.
