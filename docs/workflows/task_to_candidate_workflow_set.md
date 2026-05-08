# `task_to_candidate_workflow_set`

`task_to_candidate_workflow_set` is a reusable portfolio building block that turns an arbitrary software-work request into a ranked candidate-workflow set, explicit fit-gap reasoning, a machine-readable portfolio posture, and a deterministic publication receipt. It stops at candidate-set publication so a downstream strategy layer can choose the final `run_existing` / `compose` / `adapt` / `create_new` route explicitly.

## Problem and value

- Problem solved: convert a vague request like "what workflow should handle this security finding?" into a durable candidate-workflow package instead of ad hoc repo inspection and one-off recommendations.
- Why it matters: once the portfolio has a builder, building blocks, and multiple domain workflows, reusable candidate retrieval becomes the missing substrate for strategy selection and later adaptation workflows.
- Likely sponsors: engineering productivity, platform owners, TPM and delivery teams, consulting delivery teams, or recursive portfolio operators who need reusable retrieval before they decide reuse versus rebuild.
- Classification: reusable workflow building block. It is directly runnable, but its main value is composition into portfolio-level workflows such as `task_to_workflow_strategy`.
- Why Botlane fits: the work needs durable artifacts, verifier-gated repair loops, capability inspection, and an inspectable handoff surface for later strategy or adaptation workflows.
- Why one-shot is insufficient: candidate retrieval must survive challenge, handoff, and later composition, so the durable output has to be more than a transient recommendation in chat.

## Invocation

- Package path: `botlane/workflows/task_to_candidate_workflow_set/`
- Discovery: `botlane workflows show task_to_candidate_workflow_set`
- Direct run:

```bash
botlane run task_to_candidate_workflow_set <task-id> \
  --message "Pentest found privilege escalation in admin impersonation." \
  -wf task_title "Admin impersonation privilege escalation response" \
  -wf sponsor_role "security engineering" \
  -wf desired_outcome "Publish a ranked candidate-workflow set for downstream strategy selection." \
  -wf constraints "Prefer reuse over new authoring when the portfolio fit is credible." \
  -wf evidence_expectations "Need a strategy-ready candidate package."
```

Params:

- `task_title` required
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable
- `evidence_expectations` optional and repeatable

Composed usage is explicit in workflow code through the authoring-only composition seam. `task_to_workflow_strategy` now invokes this building block as a child workflow, adopts the child artifacts into its own workflow folder, and keeps final route selection visible in the front door rather than hidden in runtime logic.

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline and still the standing path for greenfield workflow authoring | Already credible; repeating another builder-first cycle would delay the more urgent reuse-over-rebuild extraction now exposed by the shipped front door | Deferred |
| `candidate_workflow_to_adapted_execution_plan` | High-value reuse-over-rebuild building block for turning a chosen workflow into an execution-ready adapted plan | More useful once candidate retrieval and workflow inspection are reusable; otherwise it would either duplicate the front door's comparison logic or depend on a broader framework surface than cycle 5 needed | Deferred |
| `task_to_candidate_workflow_set` | Reusable portfolio building block for ranked candidate retrieval, fit-gap analysis, and downstream strategy/adaptation handoff | Requires richer inspectable workflow inputs and should be reused immediately by the front door to prove value | Chosen and shipped in cycle 5 |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive workflow-capability snapshot seam plus authoring helper | Gives portfolio workflows a reusable, inspectable way to capture workflow parameters and compiled step contracts without changing runtime-owned routing behavior or `workflow.toml` | Requires a new pure inspection seam and additive docs/tests, but keeps policy visible in workflow code and prompts | Chosen in the paired framework slice and consumed here |
| Expand `workflow.toml` with routing/adaptation metadata | Could improve machine-readable routing precision up front | Widens the public manifest surface, forces repo-wide metadata backfill, and hides too much authoring meaning in static metadata | Deferred |
| Runtime-owned candidate scoring or automatic selector | Would reduce workflow-local code for retrieval and ranking | Moves portfolio policy into framework machinery and violates the doctrine that ranking, adaptation, and create-new policy stay visible in workflows | Rejected |

## Meaningful design decisions

### 1. Building-block boundary

- Alternatives considered:
- jump straight to `candidate_workflow_to_adapted_execution_plan`
- let the building block choose and publish the final `run_existing` / `compose` / `adapt` / `create_new` strategy
- stop at a reusable candidate-workflow-set package with fit-gap posture and downstream handoff artifacts
- Selected: stop at a reusable candidate-workflow-set package
- Why: this extracts the repeated retrieval/comparison work cleanly, leaves final route authority visible in the front door, and gives the next adaptation workflow a durable upstream artifact instead of duplicated retrieval logic.

### 2. Inspection boundary

- Alternatives considered:
- widen the existing lightweight catalog discovery function so every discovery call imports and compiles workflows
- add a separate pure capability-inspection seam and authoring helper while preserving the current lightweight catalog seam
- push richer execution metadata into `workflow.toml`
- Selected: add a separate pure capability-inspection seam and authoring helper
- Why: existing discovery behavior is already protected by tests and should remain cheap/non-importing; richer workflow inspection is valuable, but it belongs in an additive portfolio-authoring seam rather than the baseline discovery path or manifest contract.

### 3. Reuse proof path

- Alternatives considered:
- ship `task_to_candidate_workflow_set` as a standalone package only
- add an example workflow that consumes it but leave `task_to_workflow_strategy` untouched
- update `task_to_workflow_strategy` to compose the new building block and adopt its artifacts explicitly
- Selected: update `task_to_workflow_strategy` to compose the new building block
- Why: immediate reuse proves the building block is not speculative, removes duplicated comparison work from the current front door, and exercises the existing composition helpers on a portfolio-level workflow.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Standalone building block with prompt-level repo inspection only | Add `task_to_candidate_workflow_set` but leave capability inspection ad hoc inside prompts and leave the front door unchanged | Smallest diff, but weakest reuse story and highest chance of duplicated analysis contracts | Rejected |
| Adaptation-first package plus ad hoc retrieval | Skip candidate-set extraction and build `candidate_workflow_to_adapted_execution_plan` immediately | More ambitious, but it would either duplicate current front-door comparison work or require a larger framework surface than cycle 5 needed | Rejected |
| Capability snapshot seam plus candidate-set building block plus front-door composition | Add an additive inspection seam, implement the new building block on top of it, and immediately reuse it from `task_to_workflow_strategy` | Broader change set, but the clearest path to reusable value, inspectability, and future adaptation work | Selected |

## Workflow contract

### Objective

Turn an arbitrary software-work task into a reusable candidate-workflow-set package that ranks current portfolio options, explains fit gaps, and publishes a machine-readable downstream handoff artifact without choosing or executing the final front-door route.

### Global deterministic workflow responsibilities

- Bootstrap the authoritative invocation contract from workflow parameters and the run request.
- Capture a deterministic workflow-capability snapshot through the additive capability-inspection seam.
- Hold request framing, candidate analysis, and candidate-set packaging as separate work items.
- Keep runtime-injected control data narrow and mechanical: `expected_output_schema`, `available_routes`, and step-local `Route.to(...)` metadata.
- Publish a deterministic receipt only after the candidate-workflow-set package, machine-readable summary, and next-action artifact all exist and pass validation.

### Provider-owned cognitive responsibilities

- Frame the task as a workflow-candidate retrieval problem.
- Compare current portfolio candidates, explicitly including the workflow-builder baseline.
- Rank the strongest candidates and explain the current portfolio posture.
- Package the ranked candidate set for downstream strategy selection without hiding final route choice behind runtime behavior.

### Work-item boundary doctrine

- `capture_workflow_capabilities`: deterministic capability snapshot capture only.
- `frame_candidate_request`: task framing, sponsor context, and explicit candidate-selection criteria only.
- `analyze_candidate_workflows`: candidate comparison, fit-gap analysis, and portfolio-posture reasoning only.
- `package_candidate_workflow_set`: terminal candidate-workflow-set package, machine-readable summary, and next-action artifact only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the task framing, candidate boundary, or portfolio posture changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_workflow_capabilities`
- `workflow candidate framer` / `workflow candidate critic`
- `workflow portfolio analyst` / `candidate-analysis verifier`
- `candidate-set packager` / `candidate-set package verifier`
- deterministic `publish_candidate_workflow_set`

### Control flow

1. `bootstrap`
2. `capture_workflow_capabilities`
3. `frame_candidate_request`
4. `analyze_candidate_workflows`
5. `package_candidate_workflow_set`
6. `publish_candidate_workflow_set`

### Route grammar

Helper routes:

- `question` when provider questions are allowed by the interaction policy
- question routes use `outcome.route_fields.questions`; blocked and failed routes use nullable `outcome.route_fields.reason`

Application routes:

- `inputs_prepared`
- `workflow_capabilities_captured`
- `candidate_request_framed`
- `candidate_workflows_analyzed`
- `candidate_workflow_set_ready`
- `needs_rework`
- `needs_replan`
- `candidate_workflow_set_published`

Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_workflow_capabilities` | request, invocation contract | `workflow_capability_snapshot.json` | authoritative imported capability snapshot of the current portfolio |
| `frame_candidate_request` | request, invocation contract, capability snapshot, framework docs | `candidate_request_brief.md`, `candidate_selection_criteria.md` | authoritative framing package for workflow retrieval |
| `analyze_candidate_workflows` | request, invocation contract, capability snapshot, framing artifacts | `workflow_candidate_matrix.md`, `workflow_gap_analysis.md`, `candidate_route_posture.md` | authoritative ranked candidate set and fit-gap posture |
| `package_candidate_workflow_set` | request, invocation contract, capability snapshot, checklist, framing and analysis artifacts | `candidate_workflow_set.md`, `candidate_workflow_set_summary.json`, `candidate_next_action.md` | terminal handoff package and machine-readable summary |
| `publish_candidate_workflow_set` | capability snapshot, analysis artifacts, package artifacts | `candidate_workflow_set_receipt.json` | deterministic terminal receipt proving the building block stopped at candidate-set publication |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `CandidateRequestFramingPayload`
- `CandidateWorkflowAnalysisPayload`
- `CandidateWorkflowSetPayload`

### Prompt templates

- `prompts/frame_producer.md`: role `workflow candidate-framer`; frames the task, sponsor, terminal outcome, and candidate-selection criteria without choosing the final route.
- `prompts/frame_verifier.md`: role `workflow candidate critic`; checks that the framing package is explicit enough to support capability-backed comparison.
- `prompts/analyze_producer.md`: role `workflow portfolio analyst`; compares at least three candidates when the portfolio size permits, includes the builder baseline, ranks the candidates, and declares the portfolio posture.
- `prompts/analyze_verifier.md`: role `candidate-analysis verifier`; checks that the comparison and posture are explicit, legal, and justified.
- `prompts/package_producer.md`: role `candidate-set packager`; writes the terminal candidate package, machine-readable summary, and next-action artifact.
- `prompts/package_verifier.md`: role `candidate-set package verifier`; confirms the package is ready for deterministic publication and still stops at candidate-set publication rather than hidden strategy execution.

## Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose the typed route metadata for the three pair steps.
- Runtime proof must cover:
- successful end-to-end publication of the candidate-workflow-set package and receipt
- stable publication of `workflow_capability_snapshot.json`, `candidate_workflow_set_summary.json`, and `candidate_next_action.md`
- proof that the workflow ends at candidate-set publication rather than final route execution
- publication validation that rejects a summary that omits the builder baseline from the compared candidates when the builder exists

## Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, analysis, or packaging boundary.
- `needs_replan`: the task framing, candidate boundary, or portfolio posture changed materially enough that the workflow must move backward.
- When the workflow explicitly authors `blocked`, use it when a missing prerequisite or repository fact prevents a credible candidate-workflow-set package.
- When the workflow explicitly authors `failed`, use it when irreconcilable contradictions make the current candidate set non-credible.

## Recursive self-improvement policy

- The workflow-builder remains the standing greenfield authoring path and is explicitly considered as the builder baseline during candidate comparison.
- The package relies on the cycle-5 workflow-capability snapshot seam instead of inventing runtime-owned routing or hidden prompt metadata.
- Future cycles may build `candidate_workflow_to_adapted_execution_plan` and other portfolio workflows on top of this package rather than re-deriving candidate retrieval locally.

## Evidence

- Package implementation: `botlane/workflows/task_to_candidate_workflow_set/`
- Shared capability seam consumed: `core/workflow_capabilities.py` and `stdlib/portfolio.py`
- Immediate reuse proof: `botlane/workflows/task_to_workflow_strategy/`
- Workflow asset: `botlane/workflows/task_to_candidate_workflow_set/assets/candidate_workflow_set_checklist.md`
- Workflow-specific proof: `tests/runtime/test_task_to_candidate_workflow_set.py`
- The scripted tests prove workflow discovery, compilation, terminal publication, and publication-side validation that the builder baseline stays part of the compared-candidate set.
