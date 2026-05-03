# `workflow_idea_to_workflow_package`

`workflow_idea_to_workflow_package` is the repository's first explicit workflow-builder package. It turns an ambiguous workflow idea into a concrete Autoloop workflow package plus design, verification, promotion, and rollback evidence.

## Problem and value

- Problem solved: turn a valuable workflow idea or reusable recipe concept into a package another team can discover, inspect, run, and extend.
- Why it matters: the repo previously had only `autoloop init workflow <name>` plus manual discipline, not a credible builder workflow.
- Likely sponsors: framework owners, internal platform teams, engineering productivity groups, or consulting organizations building repeatable delivery playbooks.
- Classification: end-to-end workflow. The trigger is a workflow idea; the terminal result is a workflow package and evidence pack.
- Why Autoloop fits: the work spans candidate analysis, explicit design, repository edits, and verification evidence across multiple durable artifacts.
- Why one-shot is insufficient: the package needs comparison, design, build, evaluation, and a deterministic publish gate with rework versus replan logic.

## Invocation

- Package path: `workflows/workflow_idea_to_workflow_package/`
- Discovery: `autoloop workflows show workflow_idea_to_workflow_package`
- Run:

```bash
autoloop run workflow_idea_to_workflow_package <task-id> \
  --message "We need a workflow for release readiness reviews." \
  -wf package_name release_candidate_to_go_no_go \
  -wf workflow_kind end_to_end \
  -wf aliases release-go-no-go \
  -wf target_test_command "pytest -q"
```

Params:

- `package_name` required
- `package_title` optional
- `workflow_kind` required: `end_to_end` or `building_block`
- `aliases` optional and repeatable
- `target_test_command` optional, default `pytest`

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Creates the missing workflow-builder as real infrastructure | Framework-first, so it must still ship concrete package outputs and tests | Chosen |
| `release_candidate_to_go_no_go` | Concrete release decision workflow for engineering teams | Better once the repo has a strong authoring workflow to build it through | Deferred |
| `incident_to_hardening_program` | High-value incident response and prevention workflow | Also valuable, but less foundational than the builder gap in cycle 1 | Deferred |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Step-owned narrow control contracts | Keeps machine-readable contracts close to steps and visible in compiled workflow metadata | Requires additive validation and engine plumbing | Chosen |
| Prompt front matter for machine-readable contracts | Co-locates metadata near prompts | Mixes runtime-only control data into provider-facing assets and duplicates state | Rejected |
| Runtime-owned side tables or hidden branches | Small initial diff | Hides workflow meaning in runtime logic and violates the authoring doctrine | Rejected |

## Meaningful design decisions

### 1. Package shape

- Alternatives considered:
- ship only a reusable helper or scaffold recipe
- ship a domain workflow first
- ship the workflow-builder itself
- Selected: ship the workflow-builder itself as an end-to-end workflow package
- Why: the repository had no credible builder capability, so shipping the builder is the highest-leverage addition.

### 2. Input capture strategy

- Alternatives considered:
- read workflow parameters from `run.json` in every step
- use an explicit `before(ctx)` hook on the first step
- use a deterministic bootstrap step that writes an invocation artifact and seeds workflow state
- Selected: deterministic bootstrap step
- Why: it creates an authoritative run-local input artifact, opens sessions mechanically, and gives later artifact templates stable `state.package_name` access without hidden runtime behavior.

### 3. Generated package output strategy

- Alternatives considered:
- hidden generator helper or runtime subsystem
- only a directory-level output with no explicit index
- direct repository file creation plus a build report that enumerates concrete generated files
- Selected: direct repository file creation plus explicit build report
- Why: it reuses the current scaffold contract, keeps outputs inspectable, and avoids introducing a new framework layer.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Hidden generator layer | Add a reusable framework generator that writes packages from a spec | Too much new machinery for one cycle | Rejected |
| Direct package creation from accepted design | Use the existing package scaffold contract and write files directly from the workflow | More explicit artifacts to manage, but much easier to inspect | Chosen |
| Child-workflow composition around `autoloop init workflow` | Invoke the scaffold command and patch the results in later steps | Adds command coupling and obscures the actual file contract | Rejected |

## Workflow contract

### Objective

Turn a workflow idea into a concrete Autoloop workflow package with prompts, docs, tests, and promotion/rollback evidence.

### Global deterministic responsibilities

- Bootstrap the run-local invocation contract.
- Compare candidates and explicitly include the workflow-builder.
- Hold package design, build, and evaluation as separate work items with explicit rework/replan routes.
- Keep runtime-injected control contracts narrow and mechanical.
- Require promotion and rollback evidence before publication.

### Provider-owned cognitive responsibilities

- Analyze candidate workflows.
- Author the design artifacts.
- Create package files, prompts, docs, and tests.
- Gather verification evidence and recommend publication.

### Work-item boundary doctrine

- `frame_candidate`: candidate comparison and selection only.
- `design_package`: authoritative package contract only.
- `build_package`: repository file creation and updates only.
- `evaluate_package`: evidence gathering and promotion/rollback recommendation only.
- `needs_rework`: same accepted design or work-item boundary still holds.
- `needs_replan`: the selected addition, topology, artifact graph, or verification surface changed materially.

### Role topology

- `workflow strategist` / `workflow critic`
- `workflow author` / `package verifier`
- `package builder` / `build verifier`
- `evaluator` / `release verifier`
- deterministic `bootstrap` and `publish_package` `python_step`s

### Control flow

1. `bootstrap`
2. `frame_candidate`
3. `design_package`
4. `build_package`
5. `evaluate_package`
6. `publish_package`

### Route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `candidate_selected`
- `design_accepted`
- `package_built`
- `evaluation_passed`
- `needs_rework`
- `needs_replan`
- `package_published`

### Artifact contract

Stable workflow-local artifacts:

- `invocation_contract.json`
- `candidate_comparison.md`
- `selected_workflow_brief.md`
- `workflow_package_spec.md`
- `step_contracts.json`
- `prompt_contract_matrix.md`
- `verification_plan.md`
- `build_report.md`
- `verification_report.md`
- `promotion_record.md`
- `rollback_plan.md`
- `publish_receipt.json`

Generated package roots:

- `workflows/<package_name>/`
- `docs/workflows/<package_name>.md`
- `tests/runtime/test_<package_name>.py`

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `CandidateSelectionPayload`
- `WorkflowDesignPayload`
- `WorkflowBuildPayload`
- `WorkflowEvaluationPayload`

### Prompt templates

The package includes explicit prompt templates for:

- `prompts/frame_producer.md`
- `prompts/frame_verifier.md`
- `prompts/design_producer.md`
- `prompts/design_verifier.md`
- `prompts/build_producer.md`
- `prompts/build_verifier.md`
- `prompts/evaluate_producer.md`
- `prompts/evaluate_verifier.md`

Each prompt names the role, purpose, current work item, required reads, required writes, legal routes, evidence requirements, and forbidden actions.

### Verification and evidence contract

- The package must be discoverable through workflow discovery.
- The compiled workflow must expose step-owned control contracts on the pair steps.
- A scripted-provider test must exercise the workflow end to end and prove it can emit a compilable generated package.

### Rework / replan / block / fail policy

- `needs_rework` loops locally on frame, design, or build, or routes evaluation back to build when the accepted design still stands.
- `needs_replan` returns from design to frame, from build to design, or from evaluation to design when the contract changed materially.
- `blocked` is for missing prerequisites.
- `failed` is for irrecoverable contradictions.

### Recursive self-improvement policy

- The package can generate candidate workflow packages, including self-improvement candidates.
- Promotion remains evidence-gated through `verification_report`, `promotion_record`, `rollback_plan`, and `publish_receipt`.

## Evidence

- Package implementation: `workflows/workflow_idea_to_workflow_package/`
- Workflow-specific test: `tests/runtime/test_workflow_builder_package.py`
- Scripted exercise proves discovery, compilation, execution, artifact generation, and a compilable generated package.
