# Cycle 6 Plan

## Scope considered

- Authoritative inputs reviewed: the immutable request snapshot, the current run raw log, the standing recursive memory files, the empty cycle-6 plan artifacts, the current workflow docs/tests, and the current repo-root framework layout.
- No clarifications were appended after run start, so the initial request remains authoritative.
- The request's mandatory inspection paths are stale. The current equivalents are repo-root `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `stdlib/`, and `workflows/`.
- In scope:
- ship one new reusable workflow building block for a real software-work gap
- ship one paired framework improvement that keeps runtime/provider boundaries narrow
- update tests, workflow docs, strategy handoff docs/prompts, and recursive memory in the same change set
- Out of scope:
- `recursive_autoloop/` wrapper/template cleanup
- widening `workflow.toml`
- runtime-owned auto-routing, auto-adaptation, or hidden downstream execution

## Current findings

- `workflow_idea_to_workflow_package` is already a credible workflow-builder baseline. The repo has the package, the decision-record doc, and runtime proof in `tests/runtime/test_workflow_builder_package.py`.
- The portfolio now has a visible front door (`task_to_workflow_strategy`) and reusable candidate retrieval (`task_to_candidate_workflow_set`), but the `adapt` route still stops at prose. There is no reusable building block that turns a chosen workflow plus task context into an execution-ready adapted plan.
- The current reusable seams are strong but incomplete for adaptation work:
- `stdlib/lifecycle.py` covers deterministic bootstrap/publication
- `stdlib/composition.py` covers explicit child invocation and parent-local artifact adoption
- `core/workflow_capabilities.py` plus `stdlib/portfolio.py` cover portfolio-wide workflow inspection
- Missing seam: a small authoring-only way to snapshot one selected workflow's contract and deterministically validate a proposed workflow-parameter mapping without importing runtime plumbing into every adaptation workflow.

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline; still the greenfield path when the portfolio has a real gap | Already credible in code, docs, and tests, so repeating another builder-first cycle would leave the reusable `adapt` route unresolved | Deferred |
| `candidate_workflow_to_adapted_execution_plan` | Fills the missing reuse-over-rebuild layer between candidate selection and execution by turning a chosen workflow plus task context into a validated execution plan | Requires a selected-workflow inspection/validation seam and careful boundary control so it does not auto-run or silently mutate the chosen workflow | Chosen |
| `workflow_to_eval_suite` | Valuable workflow-quality building block for benchmark/eval authoring | Stronger after the portfolio can already produce execution-ready adapted plans and validated task-specific parameter sets | Deferred |

### Why the chosen addition wins

- Problem solved: take a chosen workflow that is close but not plug-and-play, and turn that choice into a durable execution package another operator can run immediately.
- Likely sponsors: platform engineering, delivery leadership, TPM/program delivery, consulting/delivery shops, and recursive portfolio operators.
- Classification: reusable workflow building block.
- Why Autoloop fits: the work is artifact-heavy, benefits from verifier-gated repair loops, depends on inspectable workflow contracts, and must survive handoff instead of disappearing into chat prose.
- Why one-shot is insufficient: the adaptation needs durable artifacts for task framing, fit assessment, task-specific parameterization, expected outputs, risks, and execution next steps.
- Terminal outcome: a published adapted-execution package with validated workflow parameters, execution notes, expected downstream artifacts, and a deterministic receipt.

## Chosen addition contract

- Package path: `workflows/candidate_workflow_to_adapted_execution_plan/`
- Discovery target: `autoloop workflows show candidate_workflow_to_adapted_execution_plan`
- Direct invocation:

```bash
autoloop run candidate_workflow_to_adapted_execution_plan <task-id> \
  --message "Adapt the security remediation workflow for an admin impersonation privilege-escalation finding." \
  -wf selected_workflow security_finding_to_verified_remediation \
  -wf task_title "Admin impersonation privilege escalation response" \
  -wf sponsor_role "security engineering" \
  -wf desired_outcome "Publish an execution-ready adapted remediation plan." \
  -wf constraints "Preserve the existing workflow boundary and prefer validated workflow parameters over workflow edits." \
  -wf evidence_expectations "Need a validated run plan and concrete next action."
```

- Parameters:
- `selected_workflow` required
- `task_title` required
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable
- `evidence_expectations` optional and repeatable

### Workflow objective

Turn a chosen existing workflow plus concrete task context into an execution-ready adapted plan without auto-running the workflow or widening runtime-owned control logic.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture an authoritative selected-workflow contract snapshot from the current repository.
- Keep framing, adaptation analysis, and packaging as separate work items.
- Validate the proposed workflow-parameter mapping mechanically before publication.
- Publish only after the plan, summary, next-action artifact, and validated parameter artifact all exist and agree.

### Provider-owned cognitive responsibilities

- Frame the selected workflow against the current task and acceptance surface.
- Decide what stays fixed versus what must be parameterized or explicitly carried forward at run time.
- Explain execution assumptions, expected artifacts, verification expectations, and adaptation risks.
- Package the final execution plan and handoff artifacts.

### Work-item boundary doctrine

- `capture_selected_workflow_contract`: deterministic contract capture only.
- `frame_adaptation_request`: task framing and acceptance criteria only.
- `analyze_adaptation_surface`: fit assessment, parameterization reasoning, and execution-risk analysis only.
- `package_adapted_execution_plan`: terminal plan, machine-readable summary, and proposed parameter artifact only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the task framing, selected workflow, or execution boundary changed materially.

### Planned control flow

1. `bootstrap`
2. `capture_selected_workflow_contract`
3. `frame_adaptation_request`
4. `analyze_adaptation_surface`
5. `package_adapted_execution_plan`
6. `publish_adapted_execution_plan`

### Planned route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `selected_workflow_contract_captured`
- `adaptation_request_framed`
- `adaptation_surface_analyzed`
- `adapted_execution_plan_ready`
- `needs_rework`
- `needs_replan`
- `adapted_execution_plan_published`

### Planned artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_selected_workflow_contract` | request, invocation contract | `selected_workflow_capability.json` | authoritative selected-workflow contract snapshot |
| `frame_adaptation_request` | request, invocation contract, selected-workflow contract, framework docs | `adaptation_request_brief.md`, `adaptation_success_criteria.md` | authoritative adaptation framing package |
| `analyze_adaptation_surface` | request, invocation contract, selected-workflow contract, framing artifacts | `workflow_fit_assessment.md`, `step_adaptation_matrix.md` | authoritative fit/parameterization/risk analysis |
| `package_adapted_execution_plan` | request, invocation contract, selected-workflow contract, checklist, framing and analysis artifacts | `adapted_execution_plan.md`, `proposed_workflow_parameters.json`, `adapted_execution_summary.json`, `adapted_execution_next_action.md` | terminal human-readable and machine-readable adapted-execution package |
| `publish_adapted_execution_plan` | selected-workflow contract, package artifacts | `validated_workflow_parameters.json`, `adapted_execution_plan_receipt.json` | deterministic terminal receipt plus authoritative validated workflow parameters |

### Planned runtime-injected control contract

The workflow must continue using only:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `AdaptationRequestFramingPayload`
- `AdaptationSurfaceAnalysisPayload`
- `AdaptedExecutionPlanPayload`

### Prompt/package expectations

- Prompt files: `prompts/frame_producer.md`, `prompts/frame_verifier.md`, `prompts/analyze_producer.md`, `prompts/analyze_verifier.md`, `prompts/package_producer.md`, `prompts/package_verifier.md`, and `prompts/README.md`
- Asset: `assets/adapted_execution_plan_checklist.md`
- Decision/evidence doc: `docs/workflows/candidate_workflow_to_adapted_execution_plan.md`
- Runtime proof: `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive authoring-only adaptation helper seam | Lets workflows snapshot one selected workflow's contract and validate proposed workflow parameters using existing loader rules without widening runtime control or `workflow.toml` | Requires one new stdlib module plus docs/tests, but keeps policy visible in workflow code and artifacts | Chosen |
| Expand `workflow.toml` with adaptation metadata and parameter defaults | Could make adaptation artifacts more static and machine-readable | Widens the manifest contract, forces repo-wide metadata backfill, and hides important workflow meaning in static metadata | Rejected |
| Runtime-owned adaptation planner or auto-runner | Could produce terse CLI-driven adaptation behavior | Hides routing/adaptation policy in runtime code and breaks the doctrine that workflows own the global SOP and terminal handoff | Rejected |

### Chosen framework slice

- Add `stdlib/adaptation.py` as a narrow authoring seam.
- Export the seam from `stdlib/__init__.py`.
- Update `docs/authoring.md` and `tests/unit/test_stdlib_and_extensions.py`.
- Planned helper surface:
- `write_selected_workflow_capability_snapshot(ctx, workflow, relative_path=\"selected_workflow_capability.json\")`
- `write_validated_workflow_parameters(ctx, workflow, payload, relative_path=\"validated_workflow_parameters.json\")`
- Implementation rule: these helpers must delegate to the existing inspected workflow contract / parameter coercion machinery instead of re-implementing discovery or validation rules.

## Meaningful design decisions

### 1. Input boundary

- Alternatives considered:
- force the workflow to compose `task_to_candidate_workflow_set` every time
- require upstream strategy artifacts as the only legal entry point
- accept an explicit `selected_workflow` plus the same task-context fields already used by the front door
- Selected: explicit `selected_workflow` plus standard task-context fields
- Why: it keeps the building block reusable both standalone and downstream of `task_to_workflow_strategy`, without forcing redundant candidate retrieval.

### 2. Terminal boundary

- Alternatives considered:
- auto-run the selected workflow after adaptation planning
- stop at a prose-only adaptation memo
- stop at a published execution plan plus validated workflow-parameter artifact
- Selected: published execution plan plus validated workflow-parameter artifact
- Why: it keeps execution visible and inspectable while still producing an artifact another operator or workflow can use immediately.

### 3. Validation boundary

- Alternatives considered:
- let the provider write the final parameter artifact without deterministic validation
- validate parameters during analysis and trust them implicitly afterward
- let the provider propose parameters, then validate/canonicalize them in the publish step
- Selected: provider proposal plus deterministic publish-step validation/canonicalization
- Why: the publish step becomes the authoritative guard against parameter drift, unknown fields, bad types, and summary/plan mismatches.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc imports | Build the new package directly on `core.workflow_capabilities` and `runtime.loader` calls inside workflow code | Smallest diff, but duplicates repo-root resolution and weakens the authoring boundary | Rejected |
| New adaptation helper seam plus dedicated workflow package plus front-door handoff updates | Add one reusable helper module, implement the new package on top of it, and tighten adapt-route handoff wording/docs/tests | Broader than a one-file workflow, but the clearest reusable and inspectable design | Selected |
| Absorb adaptation planning into `task_to_workflow_strategy` | Let the front door produce the full adapted execution plan itself | Reduces package count, but collapses the front-door boundary and leaves no reusable adaptation building block | Rejected |

## Milestones

### Phase 1: Selected-workflow adaptation seam

- Add `stdlib/adaptation.py` and exports.
- Implement a selected-workflow contract snapshot helper and a validated-parameter artifact helper.
- Document the seam in `docs/authoring.md`.
- Extend unit coverage in `tests/unit/test_stdlib_and_extensions.py`.
- Acceptance:
- helpers stay under `ctx.workflow_folder`
- parameter validation reuses the existing workflow parameter coercion path
- no CLI, runtime, or manifest contract changes

### Phase 2: `candidate_workflow_to_adapted_execution_plan`

- Add the new workflow package under `workflows/candidate_workflow_to_adapted_execution_plan/`.
- Implement params, contracts, prompts, asset checklist, workflow logic, publication validation, docs, and runtime tests.
- Publication validation must reject invalid selected workflows, invalid proposed parameter payloads, missing authoritative artifacts, or mismatches between the summary and the validated parameter artifact.
- Acceptance:
- workflow discovery and compilation work from the repo root
- scripted runtime proof publishes the terminal plan, summary, next action, validated parameters, and receipt
- workflow stops at plan publication and does not auto-run the selected workflow

### Phase 3: Portfolio handoff, docs, and recursive closeout

- Update `task_to_workflow_strategy` prompts/docs/tests so the `adapt` route points to the new building block instead of a generic prose handoff.
- Keep the existing strategy-summary schema stable unless an additive machine-readable handoff field is required to keep the new contract unambiguous.
- Update `docs/workflows/task_to_workflow_strategy.md`, recursive memory files, and `tests/test_architecture_baseline_docs.py`.
- Record cycle-6 closeout proof and set the next deferred portfolio gap explicitly.
- Acceptance:
- no hidden execution is introduced into the front door
- recursive memory records the shipped adaptation layer and its helper seam
- doc baseline tests describe cycle 6 accurately

## Interface definitions

### New stdlib surface

- `stdlib/adaptation.py`
- `write_selected_workflow_capability_snapshot(...)`
- `write_validated_workflow_parameters(...)`

### New workflow package surface

- `workflows/candidate_workflow_to_adapted_execution_plan/__init__.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/params.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/contracts.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.toml`
- `workflows/candidate_workflow_to_adapted_execution_plan/prompts/*`
- `workflows/candidate_workflow_to_adapted_execution_plan/assets/adapted_execution_plan_checklist.md`

### New and updated workflow-local artifacts

- New workflow artifacts:
- `selected_workflow_capability.json`
- `adaptation_request_brief.md`
- `adaptation_success_criteria.md`
- `workflow_fit_assessment.md`
- `step_adaptation_matrix.md`
- `adapted_execution_plan.md`
- `proposed_workflow_parameters.json`
- `adapted_execution_summary.json`
- `adapted_execution_next_action.md`
- `validated_workflow_parameters.json`
- `adapted_execution_plan_receipt.json`
- Updated front-door expectation:
- adapt-route handoff text should explicitly reference `candidate_workflow_to_adapted_execution_plan`

## Compatibility and regression notes

- Keep the public CLI unchanged.
- Keep `workflow.toml` metadata-only.
- Keep runtime-owned control surfaces limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- Do not add runtime-owned auto-adaptation or auto-execution.
- Do not mutate the selected workflow package at run time; adaptation lives entirely in workflow-local artifacts and validated parameters.
- Keep existing strategy and candidate-set workflows discoverable and behaviorally stable except for a more concrete adapt-route handoff.

## Validation plan

- Targeted unit/runtime/doc verification after implementation:

```bash
.venv/bin/pytest -q \
  tests/unit/test_stdlib_and_extensions.py \
  tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py \
  tests/runtime/test_task_to_workflow_strategy.py \
  tests/test_architecture_baseline_docs.py
```

- If the new workflow reuses existing portfolio fixtures heavily, include `tests/runtime/test_task_to_candidate_workflow_set.py` only if updates there are required by actual interface drift.

## Risk register

- Risk: the new helper seam could diverge from CLI/runtime workflow-parameter coercion.
- Mitigation: implement `write_validated_workflow_parameters(...)` on top of `runtime.loader.coerce_workflow_parameter_mapping(...)`, not a new validator.
- Rollback: revert the helper module/export/doc updates and keep the workflow unshipped rather than publishing a second parameter-validation path.

- Risk: the adaptation workflow could silently broaden into auto-execution or workflow mutation.
- Mitigation: stop the workflow at publication of the plan, next action, and validated parameters; keep all execution in downstream manual or workflow-driven invocation.
- Rollback: remove any auto-run logic and restore the terminal boundary to publication-only.

- Risk: selected-workflow contract capture could leak writes outside `ctx.workflow_folder` or become a new runtime-owned inspection path.
- Mitigation: use the same relative-path guardrails as existing stdlib JSON helpers and keep the helper authoring-only.
- Rollback: revert the new helper and let the workflow remain unshipped rather than entrenching a broader framework contract.

- Risk: front-door adapt-route handoff and recursive memory could drift from the shipped package.
- Mitigation: update the front-door docs/prompts/tests and cycle-6 recursive memory in the same change set; keep `tests/test_architecture_baseline_docs.py` green.
- Rollback: revert handoff wording/schema changes together with the new workflow package if the closeout proof cannot stay coherent.
