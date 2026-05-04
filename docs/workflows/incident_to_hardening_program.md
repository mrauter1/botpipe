# `incident_to_hardening_program`

`incident_to_hardening_program` turns an incident request such as "Payments API returned 500s for 47 minutes last night" into a concrete incident hardening package with explicit framing, evidence, ranked hypotheses, mitigation guidance, backlog, communications, and a deterministic publication receipt.

## Problem and value

- Problem solved: convert an ambiguous or partially evidenced incident into an evidence-backed hardening program and leadership-ready response package another team can execute immediately.
- Why it matters: incident work is high-stakes, cross-functional, and often fails when teams stop at diagnosis instead of producing durable follow-up actions, owners, and communication artifacts.
- Likely sponsors: incident commanders, SRE leads, engineering managers, platform or reliability owners, and support leadership when customer impact exists.
- Classification: end-to-end workflow. The trigger is a concrete incident. The terminal result is a hardening program, response package, and deterministic receipt.
- Why Autoloop fits: the work spans framing, evidence collection, hypothesis ranking, mitigation planning, and package assembly across durable filesystem artifacts with bounded producer/verifier loops.
- Why one-shot is insufficient: missing evidence must be surfaced explicitly, verifier loops must gate local repair versus replan, and the final outcome needs multiple durable artifacts instead of a single postmortem blob.

## Invocation

- Package path: `autoloop/workflows/incident_to_hardening_program/`
- Discovery: `autoloop workflows show incident_to_hardening_program`
- Run:

```bash
autoloop run incident_to_hardening_program <task-id> \
  --message "Payments API returned 500s for 47 minutes last night." \
  -wf incident_title "Payments API 500 spike" \
  -wf incident_window 2026-04-22T03:11Z/2026-04-22T03:58Z \
  -wf affected_system payments-api \
  -wf severity sev1 \
  -wf incident_commander "A. Operator" \
  -wf evidence_paths incidents/2026-04-22-payments.md
```

Params:

- `incident_title` required
- `incident_window` optional
- `affected_system` optional
- `severity` optional
- `incident_commander` optional
- `evidence_paths` optional and repeatable

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Foundational workflow-builder infrastructure for all later workflows | Already shipped as a credible package with docs and runtime coverage | Deferred because the builder now exists in strong form |
| `incident_to_hardening_program` | Concrete incident-response and prevention workflow with a clear trigger and terminal package | Requires explicit evidence, analysis, and hardening boundaries to avoid a vague postmortem blob | Chosen |
| `security_finding_to_verified_remediation` | High-value workflow from security finding to verified closure | Valuable, but narrower than incident response for the next portfolio expansion | Deferred |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Workflow lifecycle authoring helpers | Removes repeated deterministic bootstrap/publication boilerplate while keeping workflow semantics explicit | Must stay authoring-only and must not become hidden runtime behavior | Chosen in the paired lifecycle phase and exercised by this package |
| Recursive package-CLI wrapper/template cleanup | Fixes the known recursive wrapper/template drift | Less directly helpful to the new incident workflow authoring surface than lifecycle helper reuse | Deferred residual |
| Child-workflow composition for evidence and analysis | Could enable future reusable incident subflows | Too much new runtime and authoring machinery before a second domain workflow proves the portfolio shape | Rejected for this cycle |

## Meaningful design decisions

### 1. Incident workflow boundary

- Alternatives considered:
- a monolithic incident review
- a reusable incident-evidence building block only
- a four-work-item end-to-end incident hardening workflow
- Selected: framing, evidence assembly, cause ranking, and hardening-package assembly with deterministic bootstrap and publish edges
- Why: this keeps role, artifact, and acceptance boundaries coherent so rework stays local and replan stays explicit.

### 2. Publication strategy

- Alternatives considered:
- stop at the last pair step
- hide terminal metadata in runtime-only state
- add a deterministic `publish_incident_package` `python_step`
- Selected: deterministic `publish_incident_package`
- Why: the workflow needs an inspectable terminal receipt without expanding runtime behavior.

### 3. Lifecycle helper boundary

- Alternatives considered:
- runtime-owned automatic invocation-contract and receipt behavior
- optional `stdlib/` helper functions used from workflow handlers
- workflow-local copy/paste handlers in every package
- Selected: optional `stdlib/` helper functions
- Why: the helper removes boilerplate without moving workflow meaning into the runtime.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Monolithic incident workflow | Collapse evidence, analysis, and package assembly into one producer/verifier loop | Faster to author, but blurs artifact ownership and rework boundaries | Rejected |
| Explicit four-step package with deterministic bootstrap/publish | Separate framing, evidence, analysis, and packaging work items | More artifacts to manage, but much clearer acceptance surfaces | Selected |
| Composed child workflows | Split incident work across reusable sub-workflows this cycle | Adds composition machinery before the second domain workflow is proven | Rejected |

## Workflow contract

### Objective

Turn a concrete incident into a durable hardening program and response package that captures framing, evidence, likely causes, mitigations, follow-up work, and stakeholder communications.

### Global deterministic workflow responsibilities

- Bootstrap the authoritative invocation contract from workflow parameters and the run request.
- Hold framing, evidence assembly, analysis, and package assembly as separate work items.
- Keep runtime control data narrow: `expected_output_schema`, `available_routes`, step-local `Route.to(...)` metadata, and `required_writes` only.
- Publish a deterministic incident receipt only after the final package exists.

### Provider-owned cognitive responsibilities

- Interpret the incident request and repository evidence.
- Gather concrete incident proof and make evidence gaps explicit.
- Rank likely causes, immediate mitigations, and validation work.
- Assemble the final operator-facing package and stakeholder communication draft.

### Work-item boundary doctrine

- `frame_incident`: incident boundary, objectives, and evidence intake only.
- `assemble_evidence_pack`: timeline, affected surface, blast radius, observability gaps, and evidence gaps only.
- `rank_cause_hypotheses`: ranked hypotheses, immediate mitigations, validation logic, and machine-readable summary only.
- `prepare_hardening_program`: final hardening program, backlog, owner map, communications, and incident package only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the incident boundary, artifact graph, or acceptance surface changed materially.

### Role topology

- `incident strategist` / `incident critic`
- `evidence assembler` / `evidence verifier`
- `incident analyst` / `analysis verifier`
- `hardening planner` / `package verifier`
- deterministic `bootstrap` and `publish_incident_package` `python_step`s

### Control flow

1. `bootstrap`
2. `frame_incident`
3. `assemble_evidence_pack`
4. `rank_cause_hypotheses`
5. `prepare_hardening_program`
6. `publish_incident_package`

### Route grammar

Runtime control route:

- `question` when provider questions are allowed by the interaction policy

Application routes:

- `inputs_prepared`
- `incident_framed`
- `evidence_pack_ready`
- `hypotheses_ranked`
- `hardening_program_ready`
- `needs_rework`
- `needs_replan`
- `incident_package_published`

If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local incident input snapshot |
| `frame_incident` | request, invocation contract, framework docs | `incident_scope_brief.md`, `response_objectives.md`, `evidence_intake_register.md` | authoritative incident boundary and response goals |
| `assemble_evidence_pack` | framing artifacts plus repo evidence | `incident_timeline.md`, `affected_surface.md`, `blast_radius.md`, `observability_gaps.md`, `evidence_gap_register.md` | authoritative evidence pack for analysis |
| `rank_cause_hypotheses` | framing artifacts plus evidence pack | `cause_hypothesis_ranking.md`, `immediate_mitigation_plan.md`, `validation_plan.md`, `incident_summary.json` | authoritative analysis and machine-readable hardening posture |
| `prepare_hardening_program` | incident summary, analysis artifacts, evidence pack, package checklist | `hardening_program.md`, `hardening_backlog.md`, `follow_up_owners.md`, `stakeholder_communications_draft.md`, `incident_resolution_package.md` | operator-facing terminal package |
| `publish_incident_package` | incident summary and final package artifacts | `incident_receipt.json` | deterministic terminal receipt |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `IncidentFramingPayload`
- `IncidentEvidencePayload`
- `IncidentHypothesisPayload`
- `IncidentHardeningProgramPayload`

### Prompt templates

The package includes explicit step prompts for:

- `prompts/frame_producer.md`
- `prompts/frame_verifier.md`
- `prompts/evidence_producer.md`
- `prompts/evidence_verifier.md`
- `prompts/analysis_producer.md`
- `prompts/analysis_verifier.md`
- `prompts/program_producer.md`
- `prompts/program_verifier.md`

### Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose the typed route metadata as normalized runtime metadata.
- A scripted-provider runtime test must prove legal route flow and creation of:
- `invocation_contract.json`
- `incident_summary.json`
- `hardening_program.md`
- `hardening_backlog.md`
- `follow_up_owners.md`
- `stakeholder_communications_draft.md`
- `incident_resolution_package.md`
- `incident_receipt.json`

### Rework / replan / block / fail policy

- `needs_rework`: local repair inside the current work-item boundary.
- `needs_replan`: the incident boundary, evidence plan, or package contract changed materially.
- When the workflow explicitly authors `blocked`, use it when required evidence sources or approvals are missing in a way the current step cannot repair locally.
- When the workflow explicitly authors `failed`, use it when irreconcilable contradictions make the incident package non-credible.

### Recursive self-improvement policy

- The package follows the builder-established package contract and exercises the lifecycle-helper seam without widening runtime behavior.
- Promotion remains evidence-gated by workflow-local artifacts and the runtime proof.
- Broader recursive memory updates remain cycle-level closeout work rather than workflow-local semantics.

## Evidence

- Package implementation: `autoloop/workflows/incident_to_hardening_program/`
- Package asset: `autoloop/workflows/incident_to_hardening_program/assets/incident_hardening_package_checklist.md`
- Workflow-specific proof: `tests/runtime/test_incident_to_hardening_program.py`
- The scripted exercise proves discovery, compilation, route legality, terminal package creation, and deterministic publication of `incident_receipt.json`.
