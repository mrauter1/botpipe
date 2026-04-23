# Recursive Framework Evolution Cycle 1 Plan

## Scope Considered

- No authoritative clarification entries exist beyond the initial request snapshot.
- The request's mandatory inspection paths are stale. Current equivalents are:
  - `docs/autoloop_workflow_framework_prd.md` -> `docs/architecture.md`
  - `docs/autoloop_workflow_framework_adr.md` -> `docs/authoring.md` and `Workflow_Instructions.md`
  - `src/autoloop/framework/workflows.py` / `pairs.py` / `store.py` / `main.py` -> `core/steps.py`, `core/compiler.py`, `core/validation.py`, `core/engine.py`, `runtime/cli.py`, `runtime/runner.py`, `runtime/stores/filesystem.py`, and `runtime/workspace.py`
  - `src/autoloop/workflows/` -> repo-root `workflows/`
- Current workflow inventory is:
  - `workflows/autoloop_v1/`
  - `workflows/workflow_idea_to_workflow_package/`
- The repository already has a credible workflow-builder capability. Evidence:
  - explicit builder package topology and prompts in `workflows/workflow_idea_to_workflow_package/`
  - package-level documentation in `docs/workflows/workflow_idea_to_workflow_package.md`
  - workflow-specific regression coverage in `tests/runtime/test_workflow_builder_package.py`
- Known unrelated regression surface remains in `recursive_autoloop/`: `.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'recursive_wrapper_targets_the_package_cli_contract or recursive_templates_reference_current_package_repo_layout_only'` currently fails because `run_recursive_autoloop.sh` does not define `require_package_autoloop_cli` and the templates still reference legacy `src/autoloop/...` paths.
- The worktree is heavily dirty with unrelated deletes and repo-layout churn. This cycle must stay scoped to additive framework files, the new workflow package, targeted docs/tests, task artifacts, and the standing recursive memory files only if required by the shipped change set.

## Decision Record: Candidate Additions

| Candidate | Why it matters | Why multi-turn / agentic execution helps | Framework pressure revealed | Decision |
| --- | --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Foundational authoring infrastructure for future workflows | Needs comparison, design, build, evaluation, and promotion artifacts | Already revealed and shipped the narrow runtime control-contract seam | Deferred because it is now credible enough |
| `release_candidate_to_go_no_go` | Gives engineering organizations a concrete release-readiness decision workflow with an execution-ready terminal package | Evidence collection, blocker triage, rollback analysis, and decision packaging are artifact-heavy and benefit from durable producer/verifier loops | Pressures route contracts to carry explicit evidence and work-item-effect semantics cleanly | Chosen |
| `incident_to_hardening_program` | High-value incident response and prevention workflow | Requires durable evidence collection, hypothesis ranking, remediation planning, and leadership communication | Pressures evidence ranking and remediation-backlog patterns | Deferred because release go/no-go has the clearest trigger and terminal outcome for the first domain workflow |

Selection rationale:

- The builder now exists in strong form, so repeating a builder-first cycle would have lower leverage than using it to grow the domain workflow portfolio.
- `release_candidate_to_go_no_go` has the cleanest end-to-end trigger, clearest terminal output package, and the most direct pressure on explicit evidence-gated routing.
- `incident_to_hardening_program` remains a strong next-cycle candidate after the release decision pattern exists.

## Chosen Addition: `release_candidate_to_go_no_go`

### Problem solved

Turn an ambiguous release request such as "ship release 2026.04 on Friday" into an explicit go/no-go decision package with blockers, evidence, rollback readiness, operational checklist, communications draft, and a signed recommendation.

### Why it matters

- Release decisions are high-stakes, cross-functional, and rarely reducible to a one-shot answer.
- Teams need an evidence-backed package another operator, manager, or incident commander can use immediately.
- This is a strong real-software-work workflow for release management, QA, SRE, platform, and engineering leadership.

### Sponsors and users

- Release managers
- Engineering managers
- QA or test leads
- SRE / operations leads
- Product or delivery leadership when release risk needs explicit sign-off

### Classification

This should ship as an end-to-end workflow, not only a reusable building block. The trigger is a specific release candidate. The terminal outcome is a concrete decision package another team can act on.

### Why Autoloop is a fit

- The work spans framing, evidence gathering, readiness assessment, and final package assembly.
- The durable outputs are filesystem artifacts, not just prose.
- Rework and replan boundaries are meaningful: some issues need local evidence repair, while others mean the release boundary or decision criteria changed materially.

### Why a one-shot interaction is insufficient

- Evidence must be gathered, checked, and packaged.
- Missing proof needs bounded rework loops.
- The final recommendation should only be promotable after explicit verification surfaces have been satisfied.

### Invocation path and public interface

- Package path: `workflows/release_candidate_to_go_no_go/`
- Discovery:
  - `autoloop workflows show release_candidate_to_go_no_go`
- Example run:

```bash
autoloop run release_candidate_to_go_no_go <task-id> \
  --message "We want to ship release 2026.04 on Friday." \
  -wf release_name 2026.04 \
  -wf target_date 2026-04-24 \
  -wf deployment_environment production
```

Planned workflow parameters:

- `release_name: str` required
- `target_date: str | None` optional ISO-like date string
- `deployment_environment: str = "production"`
- `release_owner: str | None` optional
- `evidence_paths: list[str]` optional repeatable repo-path hints for release notes, test evidence, or rollout docs

### Terminal outcome

An accepted release decision package containing:

- `release_scope_brief.md`
- `decision_criteria.md`
- `test_evidence_pack.md`
- `operational_readiness.md`
- `rollback_readiness.md`
- `blocking_issues.md`
- `go_no_go_assessment.md`
- `risk_register.md`
- `release_decision_package.md`
- `release_communications_draft.md`
- machine-readable decision metadata and final receipt

## Workflow Design Contract For The New Package

### Global deterministic workflow responsibilities

- Bootstrap authoritative run-local invocation inputs.
- Fix the release boundary and decision criteria before evidence packaging starts.
- Keep evidence assembly, readiness assessment, and final package assembly as separate coherent work items.
- Enforce producer/verifier behavior on all non-trivial steps.
- Keep runtime injection narrow: only `expected_output_schema`, `available_routes`, and `route_contracts`.
- Publish a final decision receipt only after the decision package is accepted.

### Provider-owned cognitive responsibilities

- Read the release brief and repo evidence.
- Decide how to collect and package release evidence from the workspace.
- Evaluate whether evidence gaps are locally repairable or require replan.
- Write the assessment and final decision package artifacts.

### Work-item boundary doctrine for this workflow

- `frame_release` owns release boundary, sponsor context, decision criteria, and evidence intake requirements.
- `assemble_evidence_pack` owns collection and packaging of release evidence artifacts.
- `assess_go_no_go` owns risk synthesis, blocker determination, and explicit recommendation.
- `prepare_decision_package` owns the final release packet and stakeholder communication draft.
- `needs_rework` means the same step can succeed with better evidence or tighter synthesis.
- `needs_replan` means the release boundary, artifact graph, decision criteria, or assessment surface changed materially.

### Role topology

- `release strategist` / `release critic`
- `evidence assembler` / `evidence verifier`
- `readiness assessor` / `decision verifier`
- `decision packager` / `package verifier`
- deterministic `bootstrap` and `publish_decision` system steps

### Control flow as explicit procedure

1. `bootstrap`
2. `frame_release`
3. `assemble_evidence_pack`
4. `assess_go_no_go`
5. `prepare_decision_package`
6. `publish_decision`

### Route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `release_framed`
- `evidence_pack_ready`
- `assessment_ready`
- `decision_package_ready`
- `needs_rework`
- `needs_replan`
- `decision_published`

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `frame_release` | request, invocation contract, architecture/authoring docs, repo evidence hints | `release_scope_brief.md`, `decision_criteria.md`, `evidence_intake_register.md` | release brief and criteria become authoritative framing artifacts |
| `assemble_evidence_pack` | release brief, criteria, repo evidence, optional `evidence_paths` | `release_inventory.md`, `test_evidence_pack.md`, `operational_readiness.md`, `rollback_readiness.md`, `blocking_issues.md` | evidence pack is authoritative for assessment |
| `assess_go_no_go` | framing artifacts and evidence pack | `go_no_go_assessment.md`, `risk_register.md`, `decision_summary.json` | assessment and machine-readable summary gate final packaging |
| `prepare_decision_package` | assessment, risk register, blockers, evidence pack | `release_decision_package.md`, `release_communications_draft.md` | final human-facing package for operators and leadership |
| `publish_decision` | decision package and summary | `decision_receipt.json` | immutable final receipt for terminal success |

Authoritative precedence:

- `release_scope_brief.md` and `decision_criteria.md` are authoritative after `frame_release`.
- `decision_summary.json` is the machine-readable authority for the final recommendation.
- `release_decision_package.md` is the primary operator-facing terminal deliverable.
- `decision_receipt.json` is the final deterministic workflow receipt.

### Runtime-injected control contract

The workflow must rely only on:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `ReleaseFramingPayload`
- `ReleaseEvidencePayload`
- `ReleaseAssessmentPayload`
- `ReleaseDecisionPackagePayload`

Planned route-contract semantics:

- route contracts carry a brief summary, required evidence artifacts, and a first-class work-item effect
- runtime validates route legality and payload schema
- prompts remain the provider-facing local SOP

### Step prompt template inventory

| Prompt file | Purpose | Reads | Writes | Legal routes |
| --- | --- | --- | --- | --- |
| `prompts/frame_producer.md` | define release boundary and decision criteria | request, invocation contract, repo evidence hints | `release_scope_brief.md`, `decision_criteria.md`, `evidence_intake_register.md` | `release_framed`, reserved routes |
| `prompts/frame_verifier.md` | verify boundary quality, sponsor alignment, and evidence plan | same inputs plus producer artifacts | verifier feedback only | `release_framed`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/evidence_producer.md` | collect and package release evidence | framing artifacts, evidence sources | release evidence artifacts and blockers | `evidence_pack_ready`, reserved routes |
| `prompts/evidence_verifier.md` | verify evidence completeness and artifact quality | evidence artifacts plus framing | verifier feedback only | `evidence_pack_ready`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/assessment_producer.md` | assess readiness, blockers, rollback safety, and recommendation | evidence pack plus criteria | `go_no_go_assessment.md`, `risk_register.md`, `decision_summary.json` | `assessment_ready`, reserved routes |
| `prompts/assessment_verifier.md` | verify recommendation quality and route choice | assessment artifacts plus evidence pack | verifier feedback only | `assessment_ready`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/package_producer.md` | build the final decision package and stakeholder communication draft | assessment artifacts plus evidence pack | `release_decision_package.md`, `release_communications_draft.md` | `decision_package_ready`, reserved routes |
| `prompts/package_verifier.md` | verify final package completeness and decision evidence | final package plus decision summary | verifier feedback only | `decision_package_ready`, `needs_rework`, `needs_replan`, reserved routes |

Prompt doctrine for every file:

- name the role and step purpose
- identify exact artifacts to read and write
- specify overwrite / append behavior
- describe expected evidence and legal routes
- forbid inventing missing evidence or silently widening scope

### Verification and evidence contract

- workflow discovery and compilation must succeed through the package loader
- route-contract normalization must be exercised on the new workflow's steps
- add a workflow-specific runtime test, e.g. `tests/runtime/test_release_candidate_to_go_no_go.py`
- use a scripted provider to prove:
  - route flow is legal
  - required artifacts are written
  - the terminal decision package and receipt are created
- rerun regression-sensitive suites touching the new framework seam:
  - `tests/unit/test_validation.py`
  - `tests/contract/test_engine_contracts.py`
  - `tests/runtime/test_workflow_builder_package.py`
  - `tests/runtime/test_release_candidate_to_go_no_go.py`
  - `tests/test_architecture_baseline_docs.py`

### Rework / replan / block / fail policy

- `needs_rework`: missing or weak evidence, incomplete artifact content, or local assessment defects inside the current step boundary
- `needs_replan`: release boundary, sponsor goal, decision criteria, or artifact graph changed materially
- `blocked`: missing evidence sources, unrecoverable environment constraints, or an explicitly paused stakeholder dependency
- `failed`: irreconcilable contradictions in release inputs or invalid repository state

### Recursive self-improvement policy

- builder-authored patterns remain the package baseline
- this cycle may update the builder package only if the chosen route-contract improvement requires repo-owned packages to stay consistent
- promotion remains evidence-gated by the runtime tests, workflow docs, and recursive memory updates

## Decision Record: Framework Improvement Candidates

| Candidate | Benefits | Costs / trade-offs | Decision |
| --- | --- | --- | --- |
| Typed / normalized route contracts with first-class evidence and work-item-effect semantics | Makes release-gating rules explicit, reusable, and inspectable while staying inside the allowed runtime contract surface | Requires additive validation and compiler normalization; repo-owned packages may need route-contract updates | Chosen |
| Artifact-bundle helper for grouped evidence directories | Reduces repeated path prefixes for large artifact families | Risks hiding artifact meaning behind a new abstraction; explicit artifact declarations are still readable enough for this cycle | Rejected |
| Declarative child-workflow invocation step | Could improve composition for later workflow portfolios | Introduces broader runtime machinery and higher regression risk than this cycle needs | Rejected |

Chosen improvement:

- add a typed helper and normalization path for `route_contracts`
- standardize route contracts around:
  - `summary`
  - `required_artifacts`
  - `work_item_effect`
- validate `required_artifacts` names against the workflow artifact inventory
- keep runtime injection limited to normalized `route_contracts`, not a larger execution abstraction

## Meaningful Design Decisions

1. Addition shape
   - Alternatives: another builder-improvement cycle, a reusable release evidence building block, or a full domain workflow
   - Selected: full end-to-end `release_candidate_to_go_no_go`
   - Why: the builder already exists; the portfolio now needs a real domain workflow with a clear terminal decision

2. Release workflow boundary
   - Alternatives: a monolithic two-step flow, a reusable release-evidence building block only, or a four-work-item release decision workflow
   - Selected: explicit framing, evidence, assessment, and packaging work items with deterministic bootstrap/publish edges
   - Why: this keeps rework local and replan exceptional without collapsing distinct acceptance surfaces

3. Final publication strategy
   - Alternatives: stop at the final pair step, add a hidden runtime metadata mutation, or add a deterministic publish receipt step
   - Selected: deterministic `publish_decision` system step with `decision_receipt.json`
   - Why: it preserves an inspectable terminal receipt without expanding runtime logic

4. Route-contract interface
   - Alternatives: keep freeform dicts only, document route-contract conventions in prompts/docs only, or add a typed helper plus normalized internal shape
   - Selected: typed helper plus normalized internal shape with backward-compatible dict input support
   - Why: the release workflow needs stronger evidence and work-item semantics, but existing package behavior must remain additive

5. Builder usage strategy
   - Alternatives: automate package generation by running the builder during this cycle, hand-author the release workflow while ignoring builder conventions, or author directly in repo while following builder-shaped package conventions
   - Selected: direct repo package authoring that follows the builder's package and prompt doctrine
   - Why: it keeps scope controlled and avoids depending on runtime orchestration just to land the next workflow package

## Chosen Implementation Record

| Implementation candidate | Outcome |
| --- | --- |
| Add only the release workflow package and keep current freeform route contracts | Reject; it misses the most reusable framework pressure revealed by the chosen workflow |
| Add a typed / normalized route-contract seam, then implement the release workflow against it with explicit docs/tests | Selected; best balance of reusable framework value, explicit semantics, and contained regression risk |
| Add a broader composition subsystem and split release work across child workflows this cycle | Reject; too much framework machinery for the first domain workflow and not necessary to ship the target outcome |

## Milestones

1. Introduce normalized route contracts
   - Add a framework-owned `RouteContract` helper on the strict authoring surface
   - Normalize route-contract inputs in validation/compiler paths
   - Validate required artifact names and work-item-effect values
   - Keep existing mapping-style declarations additive

2. Ship `release_candidate_to_go_no_go`
   - Add the workflow package, prompt set, docs, and runtime test
   - Use explicit artifact-first step design with deterministic bootstrap and publish steps
   - Keep the runtime/provider boundary narrow and mechanical

3. Prove, document, and record
   - Run targeted regression suites
   - Update recursive memory with the chosen addition, deferred candidates, and the route-contract improvement
   - Record the known recursive-wrapper drift as a residual gap unless it is pulled into scope intentionally

## Compatibility And Regression Notes

- Public CLI syntax should remain unchanged; this cycle only adds a new discovered workflow package and an additive authoring helper.
- Existing workflows must continue to compile unchanged:
  - `autoloop_v1` has no route contracts and should remain unaffected
  - `workflow_idea_to_workflow_package` currently uses mapping-style route contracts; normalization must preserve those semantics
- No persisted run/session/checkpoint schema changes are required.
- `route_contracts` normalization must remain additive:
  - typed helper support is new
  - raw mapping input remains valid
- Do not widen proof expectations to full `tests/runtime/test_package_cli.py` green while the known recursive-wrapper/template drift remains out of scope.

## Validation And Rollback

Validation target:

- `.venv/bin/pytest -q tests/unit/test_validation.py`
- `.venv/bin/pytest -q tests/contract/test_engine_contracts.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py tests/runtime/test_release_candidate_to_go_no_go.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`

Known non-gating residual unless explicitly fixed in-scope:

- `.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'recursive_wrapper_targets_the_package_cli_contract or recursive_templates_reference_current_package_repo_layout_only'`

Rollback strategy:

- If route-contract normalization causes regressions outside repo-owned workflow packages, revert the normalization/helper changes and keep the release workflow package out of tree.
- If the release workflow package cannot be verified cleanly, remove `workflows/release_candidate_to_go_no_go/`, `docs/workflows/release_candidate_to_go_no_go.md`, and `tests/runtime/test_release_candidate_to_go_no_go.py`, then leave only independently safe framework improvements if they are fully proven.
- Do not revert unrelated dirty files.

## Risk Register

1. Risk: route-contract normalization could break existing mapping-based route contracts.
   Mitigation: keep dict input valid, normalize centrally, and rerun builder plus contract suites.

2. Risk: the release workflow may become too broad and blur rework vs replan boundaries.
   Mitigation: keep four coherent pair steps with explicit artifact families and acceptance surfaces.

3. Risk: required-artifact validation may over-constrain legitimate upstream evidence usage.
   Mitigation: validate artifact names against inventory and allow steps to require upstream artifacts explicitly in their declared inputs.

4. Risk: known recursive wrapper/template drift may distract proof closure.
   Mitigation: keep it explicitly recorded as a residual unless the implementation must touch `recursive_autoloop/`.

5. Risk: unrelated worktree churn increases accidental scope creep.
   Mitigation: limit touched files to the framework seam, the new workflow package, targeted docs/tests, task artifacts, and required recursive memory files.
