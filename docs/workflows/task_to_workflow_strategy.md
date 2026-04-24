# `task_to_workflow_strategy`

`task_to_workflow_strategy` is the front-door workflow for the current portfolio. It turns an arbitrary software-work request into a durable strategy package that explicitly chooses whether to run an existing workflow as-is, compose several workflows, adapt an existing workflow, or create a new workflow because the current portfolio is materially insufficient. In cycle 5 it was updated to compose `task_to_candidate_workflow_set` so candidate retrieval and fit-gap analysis now land as a reusable child building block rather than front-door-local logic.

## Problem and value

- Problem solved: convert an ambiguous task such as a security finding, release-readiness request, delivery risk, or workflow idea into an inspectable portfolio decision instead of ad hoc workflow selection.
- Why it matters: the repository now has a credible builder, a reusable evidence-building block, and multiple domain workflows, but it still needs a front door that can decide reuse versus rebuild explicitly.
- Likely sponsors: engineering productivity, platform owners, TPM and delivery leads, consulting delivery teams, or recursive portfolio owners.
- Classification: end-to-end workflow. The trigger is an arbitrary task and the terminal outcome is a published strategy package plus a next-action handoff artifact.
- Why Autoloop fits: the work depends on durable portfolio inspection, explicit fit-gap analysis, producer/verifier rework loops, and filesystem artifacts that other workflows or operators can inspect later.
- Why one-shot is insufficient: the strategy must survive handoff, challenge, and later execution, so the durable output has to be more than a transient recommendation in chat.

## Invocation

- Package path: `workflows/task_to_workflow_strategy/`
- Discovery: `autoloop workflows show task_to_workflow_strategy`
- Run:

```bash
autoloop run task_to_workflow_strategy <task-id> \
  --message "Pentest found privilege escalation in admin impersonation." \
  -wf task_title "Admin impersonation privilege escalation response" \
  -wf sponsor_role "security engineering" \
  -wf desired_outcome "Choose the best existing workflow strategy for verified remediation work." \
  -wf constraints "Prefer reuse over authoring when the portfolio fit is credible." \
  -wf evidence_expectations "Need a durable remediation and closure package."
```

Parameters:

- `task_title` required
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable
- `evidence_expectations` optional and repeatable

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline and still the foundation for greenfield workflow authoring | The builder is already credible in this repository, so repeating another builder-first cycle would delay the now higher-value portfolio-routing gap | Deferred |
| `task_to_candidate_workflow_set` | Valuable reusable discovery building block for ranked workflow retrieval and fit-gap analysis | Useful, but too narrow for this cycle because it does not reach the required terminal decision among run, compose, adapt, or create-new | Deferred |
| `task_to_workflow_strategy` | Gives the portfolio a real front door that turns an arbitrary task into an explicit workflow strategy and next-action package | Requires a reusable portfolio snapshot seam and careful packaging so the workflow stops at strategy publication rather than hidden execution | Chosen |

Selection rationale:

- The builder baseline was reconsidered and remains strong enough not to dominate cycle 4 again.
- `task_to_candidate_workflow_set` was the likely next extraction after cycle 4, but cycle 5 has now shipped that extraction and the front door composes it directly.
- `task_to_workflow_strategy` is the strongest current addition because the portfolio now has enough real workflows and building blocks to justify a durable router layer.

Cycle 5 implementation note:

- The previously deferred `task_to_candidate_workflow_set` extraction is now shipped and composed directly inside this workflow.
- The front door still owns final route selection and terminal strategy packaging, but it no longer re-derives candidate retrieval locally.

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Shared workflow-catalog seam plus workflow-local portfolio snapshot helper | Gives strategy-style workflows a reusable, inspectable way to discover the current portfolio and publish a stable snapshot artifact without hiding control flow in runtime code | Adds one small authoring helper and a pure catalog module, but keeps selection policy visible in workflow prompts and docs | Chosen |
| Richer `workflow.toml` strategy metadata | Could improve future machine-readable routing precision | Widens the manifest surface and would force a repo-wide metadata backfill before the strategy problem is proven valuable enough | Deferred |
| Runtime-owned automatic router | Would make front-door runs terse from the CLI | Hides routing policy inside the runtime and violates the doctrine that workflow semantics stay visible in workflow code and prompts | Rejected |

## Meaningful design decisions

### 1. Terminal boundary

- Alternatives considered:
- stop at a reusable candidate-set building block only
- auto-run the selected downstream workflow from the front door
- stop at a published strategy package and next-action artifact
- Selected: stop at a published strategy package and next-action artifact
- Why: the front door should make the portfolio decision explicit and auditable, not bury policy inside hidden downstream execution.

### 2. Portfolio discovery boundary

- Alternatives considered:
- ad hoc repo scraping inside prompts
- immediate `workflow.toml` expansion for richer routing metadata
- reuse the shared workflow-catalog seam plus a workflow-local snapshot artifact
- Selected: shared catalog seam plus workflow-local snapshot artifact
- Why: it keeps the framework improvement additive, reusable, inspectable, and compatible with the metadata-only manifest doctrine.

### 3. Strategy package shape

- Alternatives considered:
- route-specific outputs only
- one monolithic strategy summary only
- a human-facing strategy package plus a machine-readable summary and a concrete next-action artifact
- Selected: human-facing package plus machine-readable summary plus next-action artifact
- Why: it creates one stable terminal contract for both humans and later workflows without inventing route-specific publication behaviors.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Runtime-owned selector | Add automatic workflow routing and invocation to runtime code | Fastest apparent path, but highest doctrine and regression risk | Rejected |
| Workflow-only implementation with ad hoc portfolio scraping | Implement the front door directly and let prompts inspect the repo however they want | Smaller diff, but it duplicates discovery logic and weakens inspectability | Rejected |
| Shared snapshot seam plus explicit front-door workflow package | Reuse the pure catalog seam and package the strategy explicitly in workflow code and artifacts | Slightly broader change set, but reusable and consistent with the framework doctrine | Selected |

## Workflow contract

### Objective

Turn an arbitrary software-work task into an explicit strategy package that chooses one route among `run_existing`, `compose`, `adapt`, or `create_new`, then publish a handoff package without auto-running the selected route.

### Global deterministic workflow responsibilities

- Bootstrap the authoritative invocation contract from workflow parameters and the run request.
- Capture a deterministic snapshot of the current workflow portfolio through the shared catalog seam.
- Hold task framing, strategy selection, and strategy packaging as separate work items.
- Keep runtime control data narrow and mechanical: `expected_output_schema`, `available_routes`, and `route_contracts`.
- Publish a deterministic receipt only after the terminal package, machine-readable summary, and next-action artifact all exist.

### Provider-owned cognitive responsibilities

- Frame the task as a workflow-selection problem.
- Compare current portfolio candidates, explicitly including the workflow-builder baseline.
- Decide whether reuse, composition, adaptation, or new authoring is the right route.
- Package the selected route and handoff artifact without hiding execution behind runtime behavior.

### Work-item boundary doctrine

- `capture_workflow_portfolio`: deterministic snapshot capture only.
- `frame_task`: task framing, sponsor context, and explicit selection criteria only.
- `select_strategy`: candidate comparison, fit-gap analysis, and route choice only.
- `package_strategy`: terminal strategy package, machine-readable summary, and next-action artifact only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the task framing, candidate set, or selected route changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_workflow_portfolio`
- `workflow strategist` / `workflow critic`
- deterministic `build_candidate_workflow_set` child-composition step
- `portfolio strategist` / `strategy verifier`
- `strategy packager` / `strategy package verifier`
- deterministic `publish_strategy`

### Control flow

1. `bootstrap`
2. `capture_workflow_portfolio`
3. `frame_task`
4. `build_candidate_workflow_set`
5. `select_strategy`
6. `package_strategy`
7. `publish_strategy`

### Route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `portfolio_snapshotted`
- `task_framed`
- `candidate_workflow_set_built`
- `strategy_selected`
- `strategy_package_ready`
- `needs_rework`
- `needs_replan`
- `strategy_published`

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_workflow_portfolio` | `request.md`, `invocation_contract.json` | `workflow_portfolio_snapshot.json` | authoritative snapshot of the current portfolio and linked workflow docs/code |
| `frame_task` | request, invocation contract, portfolio snapshot, framework docs | `task_strategy_brief.md`, `workflow_selection_criteria.md` | authoritative framing package for strategy selection |
| `build_candidate_workflow_set` | request, invocation contract, portfolio snapshot, framing artifacts | adopted `workflow_candidate_matrix.md`, `workflow_gap_analysis.md`, `candidate_route_posture.md`, `candidate_workflow_set.md`, `candidate_workflow_set_summary.json`, `candidate_next_action.md` | authoritative child candidate-set package copied into the parent workflow folder |
| `select_strategy` | request, invocation contract, portfolio snapshot, framing artifacts, adopted child candidate artifacts | `strategy_decision.md` | authoritative final route decision surface |
| `package_strategy` | request, invocation contract, portfolio snapshot, checklist, framing artifacts, adopted child candidate artifacts, strategy decision | `workflow_strategy_package.md`, `strategy_summary.json`, `strategy_next_action.md` | terminal handoff package and machine-readable summary |
| `publish_strategy` | portfolio snapshot, decision artifacts, package artifacts | `strategy_receipt.json` | deterministic terminal receipt proving the front-door workflow stopped at packaging |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Step payload models:

- `frame_task` -> `TaskFramingPayload`
- `select_strategy` -> `StrategySelectionPayload`
- `package_strategy` -> `StrategyPackagePayload`

### Prompt templates

- `prompts/frame_producer.md`: role `workflow strategist`; frames the task, sponsor, terminal outcome, and explicit selection criteria without choosing the route.
- `prompts/frame_verifier.md`: role `workflow critic`; checks that the framing package is explicit enough to support portfolio comparison.
- `prompts/select_producer.md`: role `workflow portfolio strategist`; consumes the published child candidate-workflow-set package and chooses one final route without executing it.
- `prompts/select_verifier.md`: role `strategy verifier`; checks that the child package was consumed explicitly and the final route decision is legal and justified.
- `prompts/package_producer.md`: role `strategy packager`; writes the terminal strategy package, machine-readable summary, and next-action artifact while staying consistent with the adopted child candidate package.
- `prompts/package_verifier.md`: role `strategy package verifier`; confirms the package is ready for deterministic publication and still stops at packaging rather than hidden execution.

## Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose the typed route contracts for the three pair steps.
- Runtime proof must cover:
- successful end-to-end publication of the strategy package and receipt
- stable publication of `workflow_portfolio_snapshot.json`, `strategy_summary.json`, and `strategy_next_action.md`
- explicit child publication of `task_to_candidate_workflow_set` plus parent-local adoption of the child candidate artifacts
- proof that the workflow ends at strategy packaging rather than auto-running the selected downstream workflow
- publication validation that rejects a strategy summary that omits the builder baseline from the compared candidates

## Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, selection, or packaging boundary.
- `needs_replan`: the task framing, candidate set, or selected route changed materially enough that the workflow must move backward.
- `blocked`: a missing prerequisite or repository fact prevents a credible strategy package.
- `failed`: irreconcilable contradictions make the current strategy package non-credible.

## Recursive self-improvement policy

- The workflow-builder remains the standing greenfield authoring path and is explicitly considered as the `create_new` baseline during strategy selection.
- The workflow relies on the cycle-4 workflow-catalog seam instead of inventing runtime-owned routing or hidden prompt metadata.
- `task_to_candidate_workflow_set` now handles reusable candidate retrieval and fit-gap analysis, but this workflow remains the explicit front door until a stronger portfolio architecture supersedes it.

## Evidence

- Package implementation: `workflows/task_to_workflow_strategy/`
- Shared portfolio seams consumed: `core/workflow_catalog.py`, `core/workflow_capabilities.py`, and `stdlib/portfolio.py`
- Child building block consumed: `workflows/task_to_candidate_workflow_set/`
- Workflow asset: `workflows/task_to_workflow_strategy/assets/strategy_package_checklist.md`
- Workflow-specific proof: `tests/runtime/test_task_to_workflow_strategy.py`
- The scripted tests prove workflow discovery, explicit child composition, terminal strategy publication, and publication-side validation that the builder baseline stays part of the compared-candidate set.
