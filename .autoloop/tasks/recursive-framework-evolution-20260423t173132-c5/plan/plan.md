# Cycle 5 Implementation Plan

## Scope considered

- Authoritative request snapshot plus the current raw phase log. No clarifications have been appended for this run beyond the initial runtime state.
- The live repo-root architecture, not the retired `src/autoloop/...` layout still referenced in older recursive templates.
- Mandatory/current-equivalent inspection completed across:
  - `docs/architecture.md`
  - `docs/authoring.md`
  - `core/workflow_catalog.py`
  - `core/compiler.py`
  - `core/steps.py`
  - `runtime/loader.py`
  - `runtime/runner.py`
  - `runtime/cli.py`
  - `stdlib/composition.py`
  - `stdlib/portfolio.py`
  - current workflow packages under `workflows/`
  - standing recursive memory under `.autoloop_recursive/`

## Repository findings

- `workflow_idea_to_workflow_package` is already a credible workflow-builder with explicit package doctrine, docs, and runtime proof in `tests/runtime/test_workflow_builder_package.py`.
- `task_to_workflow_strategy` now provides the portfolio front door, but reusable candidate retrieval and fit-gap analysis are still bundled inside that workflow instead of being reusable workflow infrastructure.
- The current portfolio snapshot seam is intentionally narrow: it publishes discoverable workflow metadata plus linked code/doc paths, but it does not publish normalized workflow parameters or compiled step contracts for later reuse/adaptation work.
- Existing authoring helpers already support explicit child-workflow invocation, result validation, and parent-local artifact adoption, so the next portfolio building block can ship with immediate composition proof instead of remaining a standalone package.
- Current unit/runtime tests pin both the lightweight discovery contract and the front-door workflow behavior, so any cycle-5 framework change must remain additive and preserve the current non-importing catalog discovery seam.

## Part 1 decision: new workflow addition

### Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline and still the standing path for greenfield workflow authoring | Already credible; repeating another builder-first cycle would delay the more urgent reuse-over-rebuild extraction now exposed by the shipped front door | Deferred |
| `candidate_workflow_to_adapted_execution_plan` | High-value reuse-over-rebuild building block for turning a chosen workflow into an execution-ready adapted plan | More useful once candidate retrieval and workflow-inspection inputs are reusable; otherwise it would either duplicate the front door's comparison logic or depend on a broader framework seam than cycle 5 needs | Deferred |
| `task_to_candidate_workflow_set` | Reusable portfolio building block for ranked candidate retrieval, fit-gap analysis, and downstream strategy/adaptation handoff | Requires richer inspectable workflow inputs and should be reused immediately by the front door to prove value | Chosen |

### Chosen addition

- Addition: `task_to_candidate_workflow_set`
- Classification: reusable workflow building block
- Problem solved: convert an arbitrary software-work task into a durable ranked workflow candidate set, explicit fit-gap analysis, and a machine-readable portfolio posture another workflow can consume.
- Why it matters: the portfolio now has enough real workflows that reusable candidate retrieval is more valuable than another greenfield authoring cycle, and the current front door is still re-deriving that work locally.
- Likely sponsors: engineering productivity, platform owners, TPM/delivery teams, consulting delivery teams, or recursive portfolio operators managing reuse versus rebuild decisions.
- Why Autoloop fits: the job needs durable artifacts, explicit producer/verifier challenge loops, portfolio inspection, and an inspectable handoff surface for later strategy or adaptation workflows.
- Why one-shot is insufficient: candidate retrieval has to survive challenge, handoff, and later composition; it needs authoritative filesystem artifacts and a normalized machine-readable summary rather than ephemeral chat output.
- Terminal outcome: a published candidate-workflow-set package containing ranked candidates, fit-gap analysis, a portfolio-posture summary, and a next-step handoff artifact that another workflow can use directly.

## Part 2 decision: framework improvement

### Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive workflow-capability snapshot seam plus authoring helper | Gives portfolio workflows a reusable, inspectable way to capture workflow parameters and compiled step contracts without changing runtime-owned routing behavior or `workflow.toml` | Requires a new pure inspection seam and additive docs/tests, but keeps policy visible in workflow code and prompts | Chosen |
| Expand `workflow.toml` with routing/adaptation metadata | Could improve machine-readable routing precision up front | Widens the public manifest surface, forces repo-wide metadata backfill, and hides too much authoring meaning in static metadata | Deferred |
| Runtime-owned candidate scoring or automatic selector | Would reduce workflow-local code for retrieval and ranking | Moves portfolio policy into framework machinery and violates the doctrine that ranking, adaptation, and create-new policy stay visible in workflows | Rejected |

### Chosen framework improvement

- Improvement: add a pure workflow-capability inspection seam and an additive authoring helper that writes a workflow-local capability snapshot artifact for portfolio workflows.
- Why this is the best fit:
  - it directly supports `task_to_candidate_workflow_set`
  - it generalizes to later candidates such as `candidate_workflow_to_adapted_execution_plan` and `workflow_portfolio_to_operating_system`
  - it preserves the current lightweight non-importing workflow catalog discovery seam for CLI/runtime listing
  - it keeps workflow parameters, step contracts, and artifact surfaces inspectable without moving selection or adaptation policy into the runtime

## Meaningful design decisions

### 1. Building-block boundary

- Alternatives considered:
  - jump straight to `candidate_workflow_to_adapted_execution_plan`
  - let the building block choose and publish the final `run_existing` / `compose` / `adapt` / `create_new` strategy
  - stop at a reusable candidate-workflow-set package with fit-gap posture and downstream handoff artifacts
- Selected: stop at a reusable candidate-workflow-set package
- Why: this extracts the repeated retrieval/comparison work cleanly, leaves final route authority visible in the front door, and gives the next adaptation workflow a durable upstream artifact instead of duplicated retrieval logic.

### 2. Workflow inspection boundary

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
| Adaptation-first package plus ad hoc retrieval | Skip candidate-set extraction and build `candidate_workflow_to_adapted_execution_plan` immediately | More ambitious, but it would either duplicate current front-door comparison work or require a larger framework surface than cycle 5 needs | Rejected |
| Capability snapshot seam + candidate-set building block + front-door composition | Add an additive inspection seam, implement the new building block on top of it, and immediately reuse it from `task_to_workflow_strategy` | Broader change set, but the clearest path to reusable value, inspectability, and future adaptation work | Selected |

## Planned implementation shape

### Phase 1: workflow-capability snapshot seam

Target files:

- `core/workflow_catalog.py`
- new pure workflow-inspection module under `core/` if needed
- `runtime/loader.py`
- `stdlib/portfolio.py`
- `stdlib/__init__.py`
- `docs/authoring.md`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/unit/test_stdlib_and_extensions.py`

Planned interfaces:

- Preserve `discover_workflow_catalog(...)` as the lightweight metadata-only, non-importing discovery seam.
- Add a pure capability-inspection surface that can resolve a discovered workflow package and emit at least:
  - canonical workflow/package metadata
  - normalized workflow parameter fields
  - compiled step summaries including step name, kind, produced/required artifacts, available routes, and whether typed output contracts exist
  - enough route-contract/artifact metadata for portfolio workflows to reason about fit without inventing new runtime-owned policy
- Add an additive authoring helper such as `write_workflow_capability_snapshot(...) -> Path` that writes a workflow-local JSON artifact without importing runtime-owned routing behavior into workflow packages.

Constraints:

- Do not change CLI syntax.
- Do not add new `workflow.toml` fields.
- Do not change the behavior or test contract of the lightweight catalog discovery seam beyond additive reuse.
- Keep ranking, selection, adaptation, and create-new policy out of the helper; it only writes inspectable input artifacts.

### Phase 2: `task_to_candidate_workflow_set` building block

Target files:

- `workflows/task_to_candidate_workflow_set/__init__.py`
- `workflows/task_to_candidate_workflow_set/workflow.toml`
- `workflows/task_to_candidate_workflow_set/params.py`
- `workflows/task_to_candidate_workflow_set/contracts.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/task_to_candidate_workflow_set/prompts/*.md`
- `workflows/task_to_candidate_workflow_set/assets/*`
- `docs/workflows/task_to_candidate_workflow_set.md`
- `tests/runtime/test_task_to_candidate_workflow_set.py`

Planned workflow shape:

- system step `bootstrap`
  - writes `invocation_contract.json`
- system step `capture_workflow_capabilities`
  - writes `workflow_capability_snapshot.json`
- pair step `frame_candidate_request`
  - writes `candidate_request_brief.md` and `candidate_selection_criteria.md`
- pair step `analyze_candidate_workflows`
  - writes `workflow_candidate_matrix.md`, `workflow_gap_analysis.md`, and a route/posture rationale artifact
- pair step `package_candidate_workflow_set`
  - writes `candidate_workflow_set.md`, `candidate_workflow_set_summary.json`, and `candidate_next_action.md`
- system step `publish_candidate_workflow_set`
  - validates the summary/package and writes `candidate_workflow_set_receipt.json`

Planned route grammar:

- Reserved:
  - `question`
  - `blocked`
  - `failed`
- Application:
  - `inputs_prepared`
  - `workflow_capabilities_captured`
  - `candidate_request_framed`
  - `candidate_workflows_analyzed`
  - `candidate_workflow_set_ready`
  - `candidate_workflow_set_published`
  - `needs_rework`
  - `needs_replan`

Planned machine-readable payloads:

- `CandidateRequestFramingPayload`
- `CandidateWorkflowAnalysisPayload`
- `CandidateWorkflowSetPayload`

Expected summary fields:

- compared candidate workflow names
- ranked candidate workflow names
- builder baseline workflow name and whether it was considered
- portfolio posture such as direct fit, compose needed, adapt needed, or material gap
- authoritative artifacts
- ready-for-strategy-selection boolean
- concrete next action

Prompt-template requirements:

- Every prompt must explicitly name role, purpose, current work item, required reads, required writes, legal routes, evidence requirements, in-scope/out-of-scope rules, and forbidden actions.
- The analysis prompts must require at least three compared candidates when the portfolio size permits and must explicitly include `workflow_idea_to_workflow_package` as the builder baseline when it exists.
- The building block must stop at candidate-set publication; it must not auto-run downstream workflows or collapse into final route execution.

### Phase 3: front-door integration, recursive memory, and regression proof

Target files:

- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/task_to_workflow_strategy/contracts.py`
- `workflows/task_to_workflow_strategy/prompts/*.md`
- `docs/workflows/task_to_workflow_strategy.md`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `tests/test_architecture_baseline_docs.py`

Planned integration shape:

- Replace the front door's inlined candidate comparison work with an explicit child-workflow composition step that invokes `task_to_candidate_workflow_set`.
- Use the existing composition helpers to:
  - run the child workflow
  - require successful child completion and the expected terminal route
  - validate the child summary indicates readiness for downstream strategy selection
  - adopt the child artifacts needed by `task_to_workflow_strategy`
- Keep `task_to_workflow_strategy` responsible for the final route decision and terminal strategy package so the front door remains the explicit policy owner.

Required closeout content:

- cycle-5 recursive memory updates recording that the builder remained credible, `task_to_candidate_workflow_set` shipped as the chosen addition, and the capability snapshot seam shipped as the paired framework improvement
- roadmap updates moving `candidate_workflow_to_adapted_execution_plan` to the clearest next follow-on
- candidate-ledger updates capturing why candidate retrieval shipped before adaptation
- architecture-baseline test updates protecting the new cycle-5 memory baseline

## Compatibility and regression notes

- No CLI syntax change is planned.
- No `workflow.toml` schema change is planned.
- The existing lightweight workflow-catalog discovery contract should remain intact; richer workflow inspection must be additive and isolated to a separate seam/helper.
- `task_to_workflow_strategy` must preserve its terminal behavior of publishing a strategy package without auto-running the selected workflow, even after it composes the new child building block.
- Existing builder, evidence-pack, security, and front-door tests remain regression gates because cycle 5 touches shared portfolio authoring seams and modifies the current front door.

## Validation plan

Targeted regression command set:

```bash
.venv/bin/pytest -q \
  tests/unit/test_stdlib_and_extensions.py \
  tests/runtime/test_compatibility_runtime.py \
  tests/runtime/test_workflow_builder_package.py \
  tests/runtime/test_investigation_request_to_evidence_pack.py \
  tests/runtime/test_security_finding_to_verified_remediation.py \
  tests/runtime/test_task_to_candidate_workflow_set.py \
  tests/runtime/test_task_to_workflow_strategy.py \
  tests/test_architecture_baseline_docs.py
```

The implementation should add focused unit coverage for the new capability-inspection seam and front-door child-composition behavior if those assertions do not fit naturally in the existing test files above.

## Risk register

1. Risk: richer workflow inspection accidentally regresses the lightweight non-importing discovery seam.
   - Mitigation: keep inspection separate from `discover_workflow_catalog(...)`, preserve existing runtime compatibility tests, and treat any import-on-discovery regression as blocking.
   - Rollback: revert the capability-inspection seam and keep only the existing metadata snapshot helper.

2. Risk: `task_to_candidate_workflow_set` duplicates front-door policy instead of staying a reusable building block.
   - Mitigation: keep the building block boundary at candidate-set publication plus portfolio posture; leave final route ownership and strategy packaging in `task_to_workflow_strategy`.
   - Rollback: revert the new package and front-door composition together if the building-block boundary cannot remain crisp.

3. Risk: front-door composition breaks existing `task_to_workflow_strategy` guarantees around strategy-only termination.
   - Mitigation: preserve explicit parent-local selection and packaging steps, validate the adopted child summary, and keep tests asserting that no downstream workflow is auto-run.
   - Rollback: restore the current inlined strategy workflow if child composition cannot preserve the same terminal contract.

4. Risk: recursive memory drifts from the shipped implementation and misguides later cycles.
   - Mitigation: update all four standing recursive memory files plus `tests/test_architecture_baseline_docs.py` in the same change set.
   - Rollback: revert cycle-5 memory updates if the implementation direction changes before merge.
