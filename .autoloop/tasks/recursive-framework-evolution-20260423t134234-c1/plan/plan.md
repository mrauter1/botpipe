# Recursive Framework Evolution Cycle 1 Plan

## Scope Considered

- No authoritative clarification entries exist beyond the initial request snapshot.
- The request's mandatory inspection paths are stale. Current equivalents are:
  - `docs/autoloop_workflow_framework_prd.md` -> [docs/architecture.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/docs/architecture.md)
  - `docs/autoloop_workflow_framework_adr.md` -> [docs/authoring.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/docs/authoring.md) and [Workflow_Instructions.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/Workflow_Instructions.md)
  - `src/autoloop/framework/workflows.py` / `pairs.py` / `store.py` / `main.py` -> [core/steps.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/steps.py), [core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/compiler.py), [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py), [core/providers/models.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/providers/models.py), [runtime/runner.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/runner.py), [runtime/workspace.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/workspace.py), [runtime/loader.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/loader.py), [runtime/cli.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/cli.py), and [runtime/stores/filesystem.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/stores/filesystem.py)
  - `src/autoloop/workflows/` -> repo-root [workflows](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows)
- Current workflow inventory is a single package: [workflows/autoloop_v1](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/autoloop_v1).
- Current authoring support is only the minimal `autoloop init workflow <name>` scaffold in [runtime/cli.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/cli.py). That is not a credible workflow-builder capability because it does not compare candidates, define artifact contracts, author prompts, or verify a generated package.
- The worktree contains large unrelated deletes and refactor fallout outside this task. This cycle must not absorb, revert, or plan around those unrelated changes beyond regression awareness.

## Decision Record: Candidate Additions

| Candidate | Real-world value | Multi-turn / agentic fit | Framework pressure revealed | Decision |
| --- | --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Foundational internal platform capability for any organization building repeatable delivery workflows | Very high; package authoring needs comparison, design, build, verification, and promotion evidence | Exposes the missing narrow control-contract boundary and explicit workflow-authoring artifacts | Chosen |
| `release_candidate_to_go_no_go` | High-value release decision workflow for engineering orgs | High; evidence pack and ops checks benefit from staged orchestration | Pressures evidence packaging and rollback artifacts | Deferred until the workflow-builder exists |
| `incident_to_hardening_program` | High-value incident response and prevention workflow | High; evidence gathering and remediation planning fit Autoloop well | Pressures evidence, ranking, and follow-up backlog patterns | Deferred because the builder gap is more foundational in cycle 1 |

Selection rationale:

- The repository does not yet have a credible workflow-builder capability.
- Choosing a domain workflow first would postpone the most leveraged missing capability without a stronger justification than exists in the codebase.
- The builder workflow directly supports recursive framework improvement and future workflow authoring work.

## Chosen Addition: `workflow_idea_to_workflow_package`

### Problem solved

Turn an ambiguous workflow idea or reusable recipe request into an execution-ready Autoloop workflow package with prompts, routes, artifacts, tests, docs, and exercise evidence.

### Why it matters

- It gives the repository a first-class workflow-builder instead of relying on manual authoring plus a skeleton generator.
- It creates reusable infrastructure for future cycles, not just one more domain-specific workflow.
- It is directly sponsorable by framework owners, engineering productivity teams, internal platform teams, or consulting organizations building repeatable service-delivery playbooks.

### Classification

This should ship as an end-to-end workflow package, not just a reusable helper. The trigger is a workflow idea; the terminal result is a reviewable workflow package and evidence pack another team can immediately use.

### Why Autoloop is a good fit

- The work is artifact-heavy and benefits from staged producer/verifier orchestration.
- The output spans multiple durable surfaces: package files, prompts, tests, docs, and decision records.
- A one-shot interaction is insufficient because the work needs candidate comparison, design discipline, bounded rework, and verification evidence before acceptance.

### Invocation path and public interface

- Package path: `workflows/workflow_idea_to_workflow_package/`
- Discovery and invocation:
  - `autoloop workflows show workflow_idea_to_workflow_package`
  - `autoloop run workflow_idea_to_workflow_package <task-id> --message "We need a workflow for ..."`
- Parameters model:
  - `package_name: str` required
  - `package_title: str | None` optional
  - `workflow_kind: Literal["end_to_end", "building_block"]` required
  - `aliases: list[str]` optional
  - `target_test_command: str = "pytest"` optional
- Generated repo outputs:
  - `workflows/<package_name>/__init__.py`
  - `workflows/<package_name>/workflow.py`
  - `workflows/<package_name>/workflow.toml`
  - `workflows/<package_name>/prompts/*.md`
  - `workflows/<package_name>/assets/`
  - `docs/workflows/<package_name>.md`
  - targeted test coverage under `tests/`
- Generated workflow-scope evidence artifacts:
  - `{workflow_folder}/candidate_comparison.md`
  - `{workflow_folder}/workflow_package_spec.md`
  - `{workflow_folder}/step_contracts.json`
  - `{workflow_folder}/verification_report.md`
  - `{workflow_folder}/promotion_record.md`
  - `{workflow_folder}/rollback_plan.md`

### Terminal outcome

An accepted workflow package with explicit prompts, artifact interfaces, route grammar, docs, targeted tests, and a verification record proving it compiles and is exercisable.

## Workflow Design Contract For The New Package

### Global deterministic workflow responsibilities

- Compare at least three strong candidate additions and explicitly include the workflow-builder itself.
- Fix the selected package identity, workflow kind, role topology, route grammar, artifact contract, and verification surface before code generation completes.
- Enforce producer/verifier behavior on all non-trivial steps.
- Keep runtime/provider boundary narrow: runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
- Require verification evidence before final acceptance.

### Provider-owned cognitive responsibilities

- Analyze the requested problem and compare candidate workflow shapes.
- Author workflow package files, prompts, docs, and tests.
- Decide whether feedback is locally repairable or requires replan, subject to the route contract.
- Gather proof from filesystem artifacts and test execution.

### Work-item boundary doctrine for this workflow

- `frame_candidate` owns candidate comparison and selection artifacts.
- `design_package` owns the workflow specification, prompt contract matrix, route grammar, and artifact contract.
- `build_package` owns repo file creation and updates for the generated workflow package, docs, and tests.
- `evaluate_package` owns proof gathering, regression checks, and promotion or rollback recommendations.
- `needs_rework` keeps the same step, specialization, artifact family, and acceptance surface.
- `needs_replan` is required when package identity, role topology, route grammar, artifact graph, or verification strategy changes materially.

### Role topology

- `workflow strategist` / `workflow critic`
- `workflow author` / `package verifier`
- `evaluator` / `release verifier`
- `publish` system step for final promotion record

### Control flow as explicit procedure

1. `frame_candidate` pair step
2. `design_package` pair step
3. `build_package` pair step
4. `evaluate_package` pair step
5. `publish_package` system step

### Route grammar

- Reserved routes: `question`, `blocked`, `failed`
- Application routes:
  - `candidate_selected`
  - `design_accepted`
  - `package_built`
  - `evaluation_passed`
  - `needs_rework`
  - `needs_replan`
  - `package_published`

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `frame_candidate` | run request, `docs/architecture.md`, `docs/authoring.md`, `Workflow_Instructions.md`, current `workflows/`, `.autoloop_recursive/workflow_candidate_ledger.md` | `{workflow_folder}/candidate_comparison.md`, `{workflow_folder}/selected_workflow_brief.md` | brief becomes authoritative selection record for downstream design |
| `design_package` | selected brief, framework docs, current kernel files | `{workflow_folder}/workflow_package_spec.md`, `{workflow_folder}/step_contracts.json`, `{workflow_folder}/prompt_contract_matrix.md`, `{workflow_folder}/verification_plan.md` | package spec and contracts are authoritative for build/evaluate |
| `build_package` | package spec, step contracts, prompt matrix, `autoloop init workflow` conventions from `runtime/cli.py` | generated package files under `workflows/<package_name>/`, prompt files, docs file, tests, `{workflow_folder}/build_report.md` | generated package files become authoritative candidate implementation |
| `evaluate_package` | package files, tests, verification plan, build report | `{workflow_folder}/verification_report.md`, `{workflow_folder}/promotion_record.md`, `{workflow_folder}/rollback_plan.md` | verification report and promotion record gate success |
| `publish_package` | promotion record | update promotion metadata only | final success record; no hidden runtime mutation |

### Runtime-injected control contract

Implementation target:

- add step-owned control-contract metadata in the strict kernel
- derive `available_routes` mechanically from compiled step routes plus legal global routes
- treat `expected_output_schema` as the schema for `Outcome.payload`, not a replacement for `Outcome.tag`
- pass `expected_output_schema`, `available_routes`, and `route_contracts` through provider request objects
- validate `Outcome.tag` against legal routes and validate `Outcome.payload` against the declared schema when present

Planned payload models for the new workflow:

- `CandidateSelectionPayload`
- `WorkflowDesignPayload`
- `WorkflowBuildPayload`
- `WorkflowEvaluationPayload`

These should live in a workflow-local helper module such as `workflows/workflow_idea_to_workflow_package/contracts.py`, then compile to JSON schema for provider injection.

### Step prompt template inventory

| Prompt file | Purpose | Reads | Writes | Legal routes |
| --- | --- | --- | --- | --- |
| `prompts/frame_producer.md` | compare candidate additions, explicitly include the workflow-builder, and choose one | request, current workflow inventory, recursive candidate ledger, architecture docs | `candidate_comparison.md`, `selected_workflow_brief.md` | `candidate_selected`, `needs_replan`, reserved routes |
| `prompts/frame_verifier.md` | verify candidate set quality, explicit comparison, and selection rationale | producer outputs plus same inputs | verifier feedback in raw output only | `candidate_selected`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/design_producer.md` | define objective, topology, routes, artifacts, prompt plan, verification plan, and recursive policy | selected brief, kernel docs, current workflow patterns | `workflow_package_spec.md`, `step_contracts.json`, `prompt_contract_matrix.md`, `verification_plan.md` | `design_accepted`, `needs_replan`, reserved routes |
| `prompts/design_verifier.md` | verify doctrine compliance and implementation readiness | design artifacts | verifier feedback in raw output only | `design_accepted`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/build_producer.md` | create or update package files, prompts, docs, and tests using the accepted design | design artifacts, `runtime/cli.py` scaffold contract, existing package conventions | generated package files, docs, tests, `build_report.md` | `package_built`, reserved routes |
| `prompts/build_verifier.md` | verify file completeness, interface consistency, and test/doc presence | generated files and design artifacts | verifier feedback in raw output only | `package_built`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/evaluate_producer.md` | run or inspect targeted checks, collect evidence, and prepare promotion/rollback artifacts | generated files, tests, verification plan | `verification_report.md`, `promotion_record.md`, `rollback_plan.md` | `evaluation_passed`, reserved routes |
| `prompts/evaluate_verifier.md` | accept or reject promotion based on evidence and regression surface | evaluation artifacts and generated package | verifier feedback in raw output only | `evaluation_passed`, `needs_rework`, `needs_replan`, reserved routes |

Prompt authoring rule for every file:

- spell out role, step purpose, current work item, required reads, required writes, artifact handling, expected outcome, evidence requirements, legal routes, forbidden behavior, and finish criteria
- keep provider-facing operational guidance in the prompt files, not in runtime-only metadata

### Verification and evidence contract

- compile and resolve the new workflow package through the existing discovery path
- add targeted tests covering:
  - step-level control-contract compilation and validation
  - additive provider request plumbing
  - discovery / compile / invocation metadata for `workflow_idea_to_workflow_package`
  - a scripted-provider workflow run proving artifact creation and route flow
- rerun existing regression-sensitive suites touching:
  - `tests/contract/test_engine_contracts.py`
  - `tests/unit/test_validation.py`
  - `tests/runtime/test_package_cli.py`
  - `tests/runtime/test_workflow_integration_parity.py`
- update docs and recursive memory to record what was chosen, what was deferred, and why

### Rework / replan / block / fail policy

- `needs_rework`: allowed only when the same step can correct missing files, incomplete evidence, or doctrine gaps without changing package identity or artifact graph
- `needs_replan`: required when the workflow should become a reusable building block instead of an end-to-end package, when package naming/output paths change materially, or when verification surface or route grammar must be restructured
- `blocked`: use for package-name collisions, missing repository prerequisites, or environmental constraints preventing proof
- `failed`: use for unrecoverable contradictions or invalid repository state

### Recursive self-improvement policy

- baseline artifacts: current workflow inventory, architecture docs, selected brief
- candidate artifacts: generated package files plus build report
- evaluation artifacts: verification report and targeted test results
- promotion artifact: promotion record confirming the candidate remains accepted in place
- rollback artifact: rollback plan listing candidate-created paths to remove or revert if evaluation fails

## Decision Record: Framework Improvement Candidates

| Candidate | Benefits | Costs / trade-offs | Decision |
| --- | --- | --- | --- |
| Step-owned control-contract metadata compiled into provider requests | Keeps semantics visible near step declarations, satisfies doctrine, and generalizes to future workflows | Requires additive kernel, validation, and request-model changes | Chosen |
| Prompt-front-matter parsing for machine-readable contracts | Keeps control data near prompt files | Mixes runtime-only metadata into provider-facing prompt assets and duplicates state across producer/verifier files | Rejected |
| Workflow-global side tables or runner branches for contracts | Smaller local edits initially | Hides workflow meaning in parallel maps or runtime logic; conflicts with charter and authoring doctrine | Rejected |

Chosen improvement:

- add additive step-level contract fields in the strict kernel
- compile them once
- pass them mechanically through provider request models
- validate payloads and routes without inventing a new provider-facing packet abstraction

## Meaningful Design Decisions

1. Addition shape
   - Alternatives: workflow-builder workflow, domain workflow, reusable scaffold-only helper
   - Selected: end-to-end `workflow_idea_to_workflow_package`
   - Why: the repository lacks a credible workflow-builder today; this is the highest-leverage missing capability

2. Generated package creation strategy
   - Alternatives: direct repo generation seeded by `autoloop init workflow`, staged candidate directory with later copy, hidden generator helper
   - Selected: direct repo generation seeded by the existing scaffold contract, plus explicit promotion and rollback artifacts
   - Why: reuses existing conventions without adding new framework machinery, while still keeping promotion evidence explicit

3. Expected-output schema transport
   - Alternatives: raw JSON Schema dicts on steps, brand-new provider response object, Pydantic-backed payload schemas compiled to JSON schema
   - Selected: Pydantic-backed payload schemas compiled to JSON schema, while keeping `Outcome.tag` as the route carrier
   - Why: additive to current provider protocol, consistent with existing state/parameter patterns, and avoids a new packet abstraction

4. Available-route declaration strategy
   - Alternatives: duplicate route lists on steps, prompt-only route documentation, derive from compiled transitions
   - Selected: derive `available_routes` from compiled transitions plus legal global routes
   - Why: prevents drift between workflow topology and runtime-injected contracts

5. Route-contract coverage rule
   - Alternatives: require contracts for every route including reserved routes, require them only for application routes, make them fully optional
   - Selected: require explicit contracts for application routes and allow reserved-route defaults
   - Why: keeps workflow semantics explicit without duplicating generic reserved-route behavior on every step

## Chosen Implementation Record

| Implementation candidate | Outcome |
| --- | --- |
| Docs-only workflow design record with no executable package or kernel change | Reject; does not satisfy the requirement to ship a new workflow and evidence it can be exercised |
| Runnable builder workflow using only prompt prose and existing runtime surface | Reject; does not satisfy the doctrine requiring narrow runtime-injected control contracts |
| Runnable builder workflow plus additive step control contracts, targeted tests, docs, and recursive memory updates | Select |

## File Targets And Ownership

Framework files in scope:

- `core/steps.py`
- `core/compiler.py`
- `core/validation.py`
- `core/engine.py`
- `core/providers/models.py`
- `core/providers/fake.py`
- any minimal shim changes required to keep the authoring surface consistent without widening it

New workflow package in scope:

- `workflows/workflow_idea_to_workflow_package/__init__.py`
- `workflows/workflow_idea_to_workflow_package/workflow.py`
- `workflows/workflow_idea_to_workflow_package/workflow.toml`
- `workflows/workflow_idea_to_workflow_package/contracts.py`
- `workflows/workflow_idea_to_workflow_package/prompts/*.md`
- `workflows/workflow_idea_to_workflow_package/assets/`

Docs and tests in scope:

- `docs/architecture.md` and/or `docs/authoring.md` if the new control-contract surface must be documented
- `docs/workflows/workflow_idea_to_workflow_package.md`
- targeted tests under `tests/`
- recursive memory files under `.autoloop_recursive/`

Out of scope:

- real Codex or Claude provider adapters
- broad CLI redesign
- unrelated dirty deletions and legacy `autoloop_v3/` tree cleanup

## Compatibility And Regression Notes

- Keep public CLI syntax unchanged; the only public addition is one more discovered workflow package.
- Keep provider request changes additive and default-safe so existing fake-provider and parity tests continue to pass.
- Do not change workspace layout, run metadata contracts, or session persistence formats unless the chosen control-contract implementation truly requires additive metadata.
- Current `workflows/autoloop_v1/workflow.py` still parses its `phase_plan.yaml` artifact as JSON. This task's planner-owned `phase_plan.yaml` is a separate YAML contract and must not be reused as input to that parser without a dedicated compatibility fix.

## Risk Register

- Stale request paths may cause implementation drift.
  - Mitigation: target the current repo-root `core/`, `runtime/`, and `workflows/` files named above.
- Additive control-contract metadata may accidentally widen the public authoring surface.
  - Mitigation: prefer new step constructor kwargs and compiled metadata over new runtime-facing helper layers.
- Route duplication could create mismatches between transitions and injected control surfaces.
  - Mitigation: derive `available_routes` from compiled transitions instead of declaring them twice.
- Direct repo generation can leave partially authored package files after a failed run.
  - Mitigation: require explicit rollback artifacts and keep generated file scope narrow and predictable.
- Unrelated dirty worktree state may contaminate the cycle.
  - Mitigation: keep edits scoped to the new workflow, additive framework files, targeted docs/tests, and recursive memory only.

## Validation Plan

- Run targeted tests for kernel/control-contract behavior and workflow-package behavior.
- Re-run existing parity-sensitive tests touching workflow discovery, engine contracts, and autoloop_v1 integration.
- Confirm the new package is discoverable with `autoloop workflows show workflow_idea_to_workflow_package`.
- Confirm recursive memory files reflect the chosen addition, chosen framework improvement, and deferred candidates.
