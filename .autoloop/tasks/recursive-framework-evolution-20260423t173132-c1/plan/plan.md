# Recursive Framework Evolution Cycle 1 Plan

## Scope Considered

- No authoritative clarification entries exist beyond the initial request snapshot.
- The request snapshot's mandatory inspection paths are stale. Current equivalents are:
  - `docs/autoloop_workflow_framework_prd.md` -> `docs/architecture.md`
  - `docs/autoloop_workflow_framework_adr.md` -> `docs/authoring.md` and `Workflow_Instructions.md`
  - `src/autoloop/framework/workflows.py` / `pairs.py` / `store.py` -> `core/steps.py`, `core/compiler.py`, `core/validation.py`, `core/context.py`
  - `src/autoloop/main.py` -> `runtime/cli.py` and `runtime/runner.py`
  - `src/autoloop/workflows/` -> repo-root `workflows/`
- Current workflow inventory is:
  - `workflows/autoloop_v1/`
  - `workflows/workflow_idea_to_workflow_package/`
  - `workflows/release_candidate_to_go_no_go/`
- The workflow-builder is already credible enough to stop defaulting back to builder-first scope. Evidence:
  - explicit builder package topology, prompts, contracts, and docs under `workflows/workflow_idea_to_workflow_package/` and `docs/workflows/workflow_idea_to_workflow_package.md`
  - workflow-specific proof in `tests/runtime/test_workflow_builder_package.py`
  - package-specific baseline still passes in the repo-local venv:
    - `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py tests/runtime/test_release_candidate_to_go_no_go.py`
    - observed result during planning: `12 passed`
- Known pre-existing residual:
  - `.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'recursive_wrapper_targets_the_package_cli_contract or recursive_templates_reference_current_package_repo_layout_only'`
  - observed result during planning: `2 failed`
  - cause: `recursive_autoloop/run_recursive_autoloop.sh` is missing `require_package_autoloop_cli`, and recursive templates still embed legacy `src/autoloop/...` paths
- Repeated authoring pressure confirmed in shipped workflow packages:
  - `workflow_idea_to_workflow_package` and `release_candidate_to_go_no_go` both duplicate deterministic `bootstrap` handlers, session opening, invocation-contract writes, JSON helpers, and publication-receipt system-step logic

## Decision Record: Candidate Additions

| Candidate | Why it matters | Why multi-turn / agentic execution helps | Trade-off | Decision |
| --- | --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Foundational workflow-builder infrastructure | Needs comparison, design, build, evaluation, and promotion artifacts | Already credible and already exerted the first major framework pressure | Deferred because the builder is now strong enough |
| `incident_to_hardening_program` | Turns incident evidence into an operator-ready hardening program, communications, and follow-up backlog | Evidence collection, timeline reconstruction, hypothesis ranking, mitigation design, and hardening packaging all benefit from durable producer/verifier loops | Requires explicit evidence, hypothesis, and hardening boundaries to avoid a vague postmortem blob | Chosen |
| `security_finding_to_verified_remediation` | High-value security workflow from finding to verified closure | Also benefits from durable evidence, remediation, and rollout artifacts | Narrower than incident response and less portfolio-complementary right after release readiness | Deferred |

Selection rationale:

- The repository no longer lacks a credible workflow-builder, so repeating builder-first scope would be lower leverage than extending the domain workflow portfolio.
- `incident_to_hardening_program` is the strongest next workflow because it complements release readiness with an operational recovery and prevention workflow, has a clear terminal package, and naturally pressures reusable lifecycle patterns without needing more runtime machinery.
- `security_finding_to_verified_remediation` remains valuable, but incident response is the broader next proof target for reliability, delivery, and leadership communication work.

## Chosen Addition: `incident_to_hardening_program`

### Problem solved

Turn an incident such as "Payments API returned 500s for 47 minutes last night" into a durable response and prevention package with incident framing, evidence, cause hypotheses, immediate mitigation guidance, stakeholder communication, and a hardening backlog another team can execute.

### Why it matters

- Incident work is high-stakes and typically spans engineering, operations, support, and leadership.
- Teams need more than a diagnosis; they need a reusable package that closes the loop into prevention.
- This is a strong real-software-work workflow for SRE, platform, backend engineering, incident commanders, and delivery leadership.

### Sponsors and users

- Incident commander
- SRE / operations lead
- Engineering manager or technical lead
- Platform or reliability owner
- Support / customer leadership when customer communication is required

### Classification

This should ship as an end-to-end workflow, not only a reusable building block. The trigger is a concrete incident. The terminal outcome is a hardening program and incident-resolution package another team can act on immediately.

### Why Autoloop is a fit

- The work spans framing, evidence gathering, analysis, mitigation planning, and package assembly across durable filesystem artifacts.
- Producer/verifier loops matter because weak evidence, weak hypotheses, and weak hardening plans need bounded rework, not silent optimism.
- The workflow benefits from coherent work items with explicit authorities and downstream artifact use.

### Why a one-shot interaction is insufficient

- The timeline, blast radius, and evidence gaps need separate treatment from hypothesis ranking and remediation design.
- Teams need rework vs replan logic when the incident boundary or evidence surface changes materially.
- The final output must include multiple durable artifacts, not a single free-form answer.

### Invocation path and public interface

- Package path: `workflows/incident_to_hardening_program/`
- Discovery:
  - `autoloop workflows show incident_to_hardening_program`
- Example run:

```bash
autoloop run incident_to_hardening_program <task-id> \
  --message "Payments API returned 500s for 47 minutes last night." \
  -wf incident_title "Payments API 500 spike" \
  -wf incident_window "2026-04-22T03:11Z/2026-04-22T03:58Z" \
  -wf affected_system payments-api \
  -wf severity sev1 \
  -wf evidence_paths incidents/2026-04-22-payments.md
```

Planned workflow parameters:

- `incident_title: str` required
- `incident_window: str | None` optional
- `affected_system: str | None` optional
- `severity: str | None` optional
- `incident_commander: str | None` optional
- `evidence_paths: list[str]` optional repeatable repo-path hints

### Terminal outcome

An accepted incident hardening package containing:

- `incident_scope_brief.md`
- `response_objectives.md`
- `incident_timeline.md`
- `blast_radius.md`
- `observability_gaps.md`
- `cause_hypothesis_ranking.md`
- `immediate_mitigation_plan.md`
- `validation_plan.md`
- `hardening_program.md`
- `hardening_backlog.md`
- `follow_up_owners.md`
- `stakeholder_communications_draft.md`
- `incident_resolution_package.md`
- machine-readable `incident_summary.json`
- deterministic `incident_receipt.json`

## Workflow Design Contract For The New Package

### Objective

Turn a concrete incident into an evidence-backed hardening program and communication package that closes the loop from response to prevention.

### Global deterministic workflow responsibilities

- Bootstrap an authoritative run-local invocation contract from workflow parameters and the run request.
- Keep framing, evidence assembly, hypothesis ranking, and hardening-program assembly as distinct work items.
- Require producer/verifier behavior for all non-trivial steps.
- Keep runtime injection narrow: only `expected_output_schema`, `available_routes`, and `route_contracts`.
- Publish a final incident receipt only after the final package artifacts exist.

### Provider-owned cognitive responsibilities

- Interpret the incident request and workspace evidence.
- Assemble a credible incident timeline, blast radius, and evidence-gap picture.
- Rank plausible causes and immediate mitigations.
- Produce the hardening program, backlog, owner map, and communication artifacts.

### Work-item boundary doctrine for this workflow

- `frame_incident` owns incident boundary, goals, and evidence intake only.
- `assemble_evidence_pack` owns timeline, affected surface, blast radius, and observability gaps only.
- `rank_cause_hypotheses` owns hypothesis ranking, mitigation guidance, and validation logic only.
- `prepare_hardening_program` owns the durable hardening package, backlog, owners, and communications only.
- `needs_rework` means the same work-item boundary still holds.
- `needs_replan` means the incident boundary, artifact graph, or acceptance surface changed materially.

### Role topology

- `incident strategist` / `incident critic`
- `evidence assembler` / `evidence verifier`
- `incident analyst` / `analysis verifier`
- `hardening planner` / `package verifier`
- deterministic `bootstrap` and `publish_incident_package` system steps

### Control flow as explicit procedure

1. `bootstrap`
2. `frame_incident`
3. `assemble_evidence_pack`
4. `rank_cause_hypotheses`
5. `prepare_hardening_program`
6. `publish_incident_package`

### Route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `incident_framed`
- `evidence_pack_ready`
- `hypotheses_ranked`
- `hardening_program_ready`
- `needs_rework`
- `needs_replan`
- `incident_package_published`

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `frame_incident` | request, invocation contract, architecture/authoring docs, evidence hints | `incident_scope_brief.md`, `response_objectives.md`, `evidence_intake_register.md` | incident framing becomes authoritative for all downstream work |
| `assemble_evidence_pack` | framing artifacts and repo evidence | `incident_timeline.md`, `affected_surface.md`, `blast_radius.md`, `observability_gaps.md`, `evidence_gap_register.md` | authoritative evidence pack for analysis |
| `rank_cause_hypotheses` | framing artifacts and evidence pack | `cause_hypothesis_ranking.md`, `immediate_mitigation_plan.md`, `validation_plan.md`, `incident_summary.json` | machine-readable and narrative analysis authority for package assembly |
| `prepare_hardening_program` | incident summary plus evidence and analysis artifacts | `hardening_program.md`, `hardening_backlog.md`, `follow_up_owners.md`, `stakeholder_communications_draft.md`, `incident_resolution_package.md` | operator-facing terminal deliverables |
| `publish_incident_package` | incident summary and final package artifacts | `incident_receipt.json` | deterministic terminal receipt |

Authoritative precedence:

- `incident_scope_brief.md` and `response_objectives.md` are authoritative after framing.
- `incident_summary.json` is the machine-readable authority for the analysis outcome and recommended hardening posture.
- `incident_resolution_package.md` is the primary operator-facing terminal deliverable.
- `incident_receipt.json` is the immutable workflow receipt.

### Runtime-injected control contract

The workflow must rely only on:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `IncidentFramingPayload`
- `IncidentEvidencePayload`
- `IncidentHypothesisPayload`
- `IncidentHardeningProgramPayload`

Planned route-contract semantics:

- each application route declares `summary`, `required_artifacts`, and `work_item_effect`
- runtime validates route legality and payload schema
- prompt templates remain the provider-facing local SOP

### Step prompt template inventory

| Prompt file | Purpose | Reads | Writes | Legal routes |
| --- | --- | --- | --- | --- |
| `prompts/frame_producer.md` | define the incident boundary and response objectives | request, invocation contract, evidence hints | framing artifacts | `incident_framed`, reserved routes |
| `prompts/frame_verifier.md` | verify the framing and intake quality | framing inputs plus producer artifacts | verifier feedback only | `incident_framed`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/evidence_producer.md` | build the incident evidence pack | framing artifacts and evidence sources | evidence-pack artifacts | `evidence_pack_ready`, reserved routes |
| `prompts/evidence_verifier.md` | verify evidence quality and gap handling | evidence artifacts plus framing | verifier feedback only | `evidence_pack_ready`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/analysis_producer.md` | rank hypotheses and define mitigation and validation | evidence pack plus framing | analysis artifacts and `incident_summary.json` | `hypotheses_ranked`, reserved routes |
| `prompts/analysis_verifier.md` | verify analysis credibility and route choice | analysis artifacts plus evidence pack | verifier feedback only | `hypotheses_ranked`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/program_producer.md` | assemble the hardening program and communications | incident summary plus upstream artifacts | final package artifacts | `hardening_program_ready`, reserved routes |
| `prompts/program_verifier.md` | verify final package completeness and actionability | package artifacts plus incident summary | verifier feedback only | `hardening_program_ready`, `needs_rework`, `needs_replan`, reserved routes |

Prompt doctrine for every file:

- name the role and work-item purpose
- identify exact artifacts to read and write
- specify overwrite / append handling
- define required evidence and legal routes
- forbid inventing missing evidence or silently widening the incident boundary

### Verification and evidence contract

- workflow discovery and compilation must succeed through the package loader
- route-contract normalization must be exercised on every provider-owned step
- add a workflow-specific runtime proof, e.g. `tests/runtime/test_incident_to_hardening_program.py`
- use a scripted provider to prove:
  - legal route flow
  - required artifacts are created
  - the terminal package and `incident_receipt.json` are written
- targeted validation set:
  - `.venv/bin/pytest -q tests/unit/test_validation.py tests/contract/test_engine_contracts.py`
  - `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_incident_to_hardening_program.py`
  - `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`

### Rework / replan / block / fail policy

- `needs_rework`: weak evidence, weak analysis, or weak package quality inside the current work-item boundary
- `needs_replan`: incident boundary, evidence surface, or package contract changed materially
- `blocked`: required evidence or approvals are missing in a way the current step cannot repair locally
- `failed`: irreconcilable contradictions or invalid repository state make the package non-credible

### Recursive self-improvement policy

- The workflow follows the builder-era package contract and should be authorable by the existing builder in later cycles.
- Promotion remains evidence-gated by workflow-local artifacts, targeted tests, and recursive memory updates.

## Decision Record: Framework Improvement Candidates

| Candidate | Benefits | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow lifecycle authoring helpers for bootstrap and publication | Removes repeated deterministic system-step boilerplate across builder, release, and incident workflows while keeping workflow semantics explicit | Must stay helper-level only and must not become hidden runtime behavior | Chosen |
| Recursive package-CLI wrapper/template cleanup | Fixes the known failing recursive wrapper/template tests and stops future stale `src/autoloop/...` task generation | Important, but less directly helpful to the new incident workflow's authoring surface than lifecycle helper reuse | Deferred residual unless implementation intentionally expands scope |
| Child-workflow composition for shared evidence/analysis subflows | Could enable future reusable building blocks across release, incident, and security workflows | Too much new runtime and authoring machinery before a second incident-style workflow proves stable composition seams | Deferred |

## Chosen Framework Improvement: Workflow Lifecycle Authoring Helpers

### Objective

Add a small authoring-level helper seam for deterministic workflow lifecycle work that is currently copy-pasted across packages: opening declared sessions, writing `invocation_contract.json`, writing workflow-local JSON files, and publishing terminal receipts after checking required artifacts.

### Why this is the best fit now

- The repetition is already real across shipped packages and will otherwise be copied a third time into the incident workflow.
- The helper can live in `stdlib/` so workflow authors opt into it explicitly; the runtime stays narrow and mechanical.
- This improves inspectability and authoring quality without hiding step topology, artifacts, routes, or prompts.

### Boundary and non-goals

- No new runtime-owned hidden sequencing in `core/engine.py`, `runtime/runner.py`, or `runtime/cli.py`
- No new workflow DSL, registry, or step type
- No prompt-side machine-readable front matter
- No artifact-bundle abstraction that hides concrete file contracts

### Planned interface and files

Primary files:

- new helper module under `stdlib/` such as `stdlib/lifecycle.py`
- optional `stdlib/__init__.py` export if needed for consistency
- targeted authoring docs updates in `docs/authoring.md`
- migrate:
  - `workflows/workflow_idea_to_workflow_package/workflow.py`
  - `workflows/release_candidate_to_go_no_go/workflow.py`
  - new `workflows/incident_to_hardening_program/workflow.py`

Helper responsibilities:

- open a declared set of session names deterministically
- write workflow-local JSON artifacts with consistent formatting
- support a workflow-owned invocation-contract write path
- support a workflow-owned publication-receipt write path after checking required artifacts

Compatibility rule:

- existing workflow-local artifact names and receipt payload shapes for builder and release must remain stable unless a test-backed reason requires a field addition

## Meaningful Design Decisions

### 1. Addition boundary

- Alternatives considered:
  - repeat the workflow-builder as the chosen addition
  - ship a reusable incident-evidence building block first
  - ship `incident_to_hardening_program` as the next end-to-end domain workflow
- Selected: ship `incident_to_hardening_program` as an end-to-end workflow
- Why: the builder is already credible, and a second real domain workflow is the clearest next proof of portfolio value

### 2. Incident workflow topology

- Alternatives considered:
  - one monolithic incident review step
  - a highly fragmented six-plus-step chain
  - four coherent pair steps plus deterministic bootstrap and publish edges
- Selected: four pair steps plus deterministic bootstrap/publish
- Why: this keeps role, artifact, and acceptance surfaces coherent while still supporting bounded rework and explicit replan

### 3. Lifecycle improvement boundary

- Alternatives considered:
  - runtime-owned automatic invocation-contract and receipt behavior
  - optional `stdlib/` helper functions used from workflow handlers
  - workflow-local copy/paste handlers in every package
- Selected: optional `stdlib/` helper functions
- Why: the helper removes boilerplate without moving workflow meaning into the runtime

### 4. Publication contract

- Alternatives considered:
  - stop at the last pair step
  - hide terminal metadata in runtime-only run state
  - keep an explicit deterministic publish system step that writes a workflow-local receipt
- Selected: deterministic publish step with workflow-local receipt
- Why: it preserves an inspectable terminal artifact and keeps publication semantics visible in workflow topology

## Implementation Candidates

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Direct incident package with copied bootstrap/publish handlers | Fastest narrow implementation | Bakes a third copy of the same deterministic lifecycle logic into the repo | Rejected |
| Add lifecycle helper but use it only in the new incident workflow | Improves the new package, but leaves shipped packages duplicated | Weak proof that the helper is truly reusable | Rejected |
| Add shared lifecycle helper and migrate builder + release while authoring incident workflow on top of it | Slightly larger diff, but proves the abstraction is reusable and keeps existing package behavior aligned | Chosen |

## Milestones

1. Add shared lifecycle authoring helpers under `stdlib/` and migrate existing builder/release packages without changing their public behavior.
2. Implement `incident_to_hardening_program` with explicit prompts, contracts, assets, docs, and runtime proof.
3. Run targeted validation, update workflow docs and `.autoloop_recursive/` memory files, and record any residual risk that remains intentionally out of scope.

## Compatibility, Validation, And Rollback Notes

- Public CLI contract remains additive only: one new workflow package becomes discoverable, with no breaking CLI changes.
- Persisted runtime schema should remain unchanged; the lifecycle helper is authoring-side only.
- Existing builder and release workflow tests are regression gates because they currently pass under `.venv/bin/pytest`.
- Known recursive wrapper/template package-CLI failures are pre-existing. Do not claim them fixed unless implementation intentionally edits `recursive_autoloop/` and reruns the targeted failing subset.
- If the shared lifecycle helper causes behavioral drift in builder or release packages, rollback should prefer reverting helper adoption before discarding the new incident workflow design.

## Risk Register

- Lifecycle helper grows into hidden runtime machinery.
  - Mitigation: keep it in `stdlib/`, helper-only, with no new runtime control surfaces or inferred topology.
- Incident workflow collapses evidence, analysis, and hardening into a vague postmortem blob.
  - Mitigation: keep the four work-item boundaries explicit in prompts, artifacts, and route contracts.
- Migrating builder and release to the helper changes receipt payloads or artifact handling.
  - Mitigation: preserve file names and payload keys, and keep their current runtime proofs in the validation gate.
- Recursive memory remains stale about repo layout even if recursive templates stay untouched.
  - Mitigation: explicitly update `.autoloop_recursive/framework_evolution_charter.md`, `.autoloop_recursive/framework_roadmap.md`, `.autoloop_recursive/framework_gap_ledger.md`, and `.autoloop_recursive/workflow_candidate_ledger.md` during closeout.
