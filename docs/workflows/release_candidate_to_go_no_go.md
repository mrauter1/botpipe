# `release_candidate_to_go_no_go`

`release_candidate_to_go_no_go` turns a release request such as "ship release 2026.04 on Friday" into a concrete decision package with explicit framing, evidence, assessment, communications, and a deterministic publication receipt.

## Problem and value

- Problem solved: convert an ambiguous release push into an evidence-backed go, conditional-go, or no-go package another team can act on immediately.
- Why it matters: release decisions are high-stakes, cross-functional, and usually fail when teams keep the boundary, blocker criteria, and rollback expectations implicit.
- Likely sponsors: release managers, engineering managers, QA leads, SRE or operations leads, and delivery leadership.
- Classification: end-to-end workflow. The trigger is a release candidate. The terminal result is a release decision package and receipt.
- Why Botlane fits: the work spans framing, evidence collection, readiness assessment, and package assembly across durable filesystem artifacts.
- Why one-shot is insufficient: missing evidence must be surfaced explicitly, verifier loops must gate local repair versus replan, and the final outcome needs both human-facing and machine-readable artifacts.

## Invocation

- Package path: `botlane/workflows/release_candidate_to_go_no_go/`
- Discovery: `botlane workflows show release_candidate_to_go_no_go`
- Run:

```bash
botlane run release_candidate_to_go_no_go <task-id> \
  --message "We want to ship release 2026.04 on Friday." \
  -wf release_name 2026.04 \
  -wf target_date 2026-04-24 \
  -wf deployment_environment production \
  -wf release_owner "Release Captain" \
  -wf evidence_paths docs/releases/2026.04.md
```

Params:

- `release_name` required
- `target_date` optional
- `deployment_environment` optional, default `production`
- `release_owner` optional
- `evidence_paths` optional and repeatable

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Foundational builder infrastructure for all later workflows | Already shipped as a credible package with docs and runtime coverage | Deferred because the builder now exists in strong form |
| `release_candidate_to_go_no_go` | Concrete release-readiness workflow with a clear trigger and terminal package | Requires explicit evidence-gated routing and durable package outputs | Chosen |
| `incident_to_hardening_program` | Strong incident-response and prevention workflow | Valuable, but less direct than release readiness for the first domain workflow after the builder | Deferred |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Step-local `Route.to(...)` metadata | Makes release-gating semantics explicit and keeps runtime control data narrow | Needed additive validation and compiler normalization | Chosen in the preceding route-metadata phase and exercised by this package |
| Artifact-bundle helper for grouped release evidence | Could reduce repeated path prefixes | Hides artifact meaning behind a new abstraction | Rejected |
| Declarative child-workflow release composition | Could help future portfolios | Too much runtime machinery for the first domain workflow | Rejected |

## Meaningful design decisions

### 1. Release workflow boundary

- Alternatives considered:
- a monolithic release review
- a reusable release-evidence building block only
- a four-work-item end-to-end release decision workflow
- Selected: framing, evidence assembly, assessment, and package assembly with deterministic bootstrap and publish edges
- Why: this keeps role, artifact, and acceptance boundaries coherent so rework stays local and replan stays explicit.

### 2. Publication strategy

- Alternatives considered:
- stop at the last pair step
- hide terminal metadata in runtime-only state
- add a deterministic `publish_decision` `python_step`
- Selected: deterministic `publish_decision`
- Why: the workflow needs an inspectable terminal receipt without expanding runtime behavior.

### 3. Route-contract expression

- Alternatives considered:
- freeform dict route metadata only
- prompt-only route guidance
- typed route metadata with normalized runtime shape
- Selected: step-local `Route.to(...)` metadata
- Why: the release workflow needs explicit evidence and work-item-effect semantics while staying inside the narrow runtime contract surface.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Monolithic release workflow | Collapse evidence, assessment, and packaging into one producer/verifier loop | Faster to author, but blurs artifact ownership and rework boundaries | Rejected |
| Explicit four-step package with deterministic bootstrap/publish | Separate framing, evidence, assessment, and packaging work items | More artifacts to manage, but much clearer acceptance surfaces | Selected |
| Composed child workflows | Split release work across reusable sub-workflows this cycle | Adds composition machinery before the first domain workflow is proven | Rejected |

## Workflow contract

### Objective

Turn a release candidate into a durable go/no-go package that captures scope, evidence, blockers, risk, communications, and a machine-readable publication receipt.

### Global deterministic workflow responsibilities

- Bootstrap the authoritative invocation contract from workflow parameters and the run request.
- Hold framing, evidence assembly, assessment, and package assembly as separate work items.
- Keep runtime control data narrow: `expected_output_schema`, `available_routes`, step-local `Route.to(...)` metadata, and `required_writes` only.
- Publish a deterministic decision receipt only after the final package exists.

### Provider-owned cognitive responsibilities

- Interpret the release request and repository evidence.
- Gather concrete release proof and make evidence gaps explicit.
- Synthesize the recommendation, risks, and blockers.
- Assemble the final operator-facing package and stakeholder communication draft.

### Work-item boundary doctrine

- `frame_release`: release boundary, sponsor goal, criteria, and evidence intake only.
- `assemble_evidence_pack`: evidence collection, readiness summaries, and blocker inventory only.
- `assess_go_no_go`: recommendation, risk synthesis, and machine-readable decision summary only.
- `prepare_decision_package`: final packet assembly and stakeholder communications only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the release boundary, artifact graph, or acceptance surface changed materially.

### Role topology

- `release strategist` / `release critic`
- `evidence assembler` / `evidence verifier`
- `readiness assessor` / `decision verifier`
- `decision packager` / `package verifier`
- deterministic `bootstrap` and `publish_decision` `python_step`s

### Control flow

1. `bootstrap`
2. `frame_release`
3. `assemble_evidence_pack`
4. `assess_go_no_go`
5. `prepare_decision_package`
6. `publish_decision`

### Route grammar

Helper routes:

- `question` when provider questions are allowed by the interaction policy
- question routes use `outcome.route_fields.questions`; blocked and failed routes use nullable `outcome.route_fields.reason`

Application routes:

- `inputs_prepared`
- `release_framed`
- `evidence_pack_ready`
- `assessment_ready`
- `decision_package_ready`
- `needs_rework`
- `needs_replan`
- `decision_published`

Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local release input snapshot |
| `frame_release` | request, invocation contract, framework docs | `release_scope_brief.md`, `decision_criteria.md`, `evidence_intake_register.md` | authoritative release boundary and evidence gate |
| `assemble_evidence_pack` | framing artifacts plus repo evidence | `release_inventory.md`, `test_evidence_pack.md`, `operational_readiness.md`, `rollback_readiness.md`, `blocking_issues.md` | authoritative evidence pack for assessment |
| `assess_go_no_go` | criteria plus evidence pack | `go_no_go_assessment.md`, `risk_register.md`, `decision_summary.json` | authoritative recommendation and machine-readable decision |
| `prepare_decision_package` | assessment artifacts, evidence pack, package checklist | `release_decision_package.md`, `release_communications_draft.md` | operator-facing terminal package |
| `publish_decision` | decision summary and final package artifacts | `decision_receipt.json` | deterministic terminal receipt |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `ReleaseFramingPayload`
- `ReleaseEvidencePayload`
- `ReleaseAssessmentPayload`
- `ReleaseDecisionPackagePayload`

### Prompt templates

The package includes explicit step prompts for:

- `prompts/frame_producer.md`
- `prompts/frame_verifier.md`
- `prompts/evidence_producer.md`
- `prompts/evidence_verifier.md`
- `prompts/assessment_producer.md`
- `prompts/assessment_verifier.md`
- `prompts/package_producer.md`
- `prompts/package_verifier.md`

### Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose the typed route metadata as normalized runtime metadata.
- A scripted-provider runtime test must prove legal route flow and creation of:
- `invocation_contract.json`
- `decision_summary.json`
- `release_decision_package.md`
- `release_communications_draft.md`
- `decision_receipt.json`

### Rework / replan / block / fail policy

- `needs_rework`: local repair inside the current work-item boundary.
- `needs_replan`: the release boundary, decision criteria, or assessment surface changed materially.
- When the workflow explicitly authors `blocked`, use it when required evidence sources or approvals are missing in a way the current step cannot repair locally.
- When the workflow explicitly authors `failed`, use it when irreconcilable contradictions make the release package non-credible.

### Recursive self-improvement policy

- The package follows the builder-established package contract and exercises the normalized route-metadata seam.
- Promotion remains evidence-gated by workflow-local artifacts and the runtime proof.
- Broader recursive memory updates remain part of the later closeout phase, not this package-local change.

## Evidence

- Package implementation: `botlane/workflows/release_candidate_to_go_no_go/`
- Package asset: `botlane/workflows/release_candidate_to_go_no_go/assets/release_decision_package_checklist.md`
- Workflow-specific proof: `tests/runtime/test_release_candidate_to_go_no_go.py`
- The scripted exercise proves discovery, compilation, route legality, terminal package creation, and deterministic publication of `decision_receipt.json`.
