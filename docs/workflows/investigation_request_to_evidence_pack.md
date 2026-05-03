# `investigation_request_to_evidence_pack`

`investigation_request_to_evidence_pack` is a reusable workflow building block that turns an ambiguous investigation request into a durable evidence pack with explicit framing, source inventory, coverage mapping, findings, unresolved gaps, a machine-readable summary, and a deterministic publication receipt.

## Problem and value

- Problem solved: convert a vague request like "assemble the evidence pack for this security finding" or "gather the release-readiness proof" into an evidence artifact set another workflow or human can consume without guessing scope, sources reviewed, or missing proof.
- Why it matters: release, incident, security, delivery-recovery, and customer-escalation work often fails when downstream assessment starts from scattered notes instead of an authoritative evidence package.
- Likely sponsors: security engineers, release managers, SRE leads, engineering managers, TPMs, or escalation owners who need a durable evidence base before a decision or remediation plan can be trusted.
- Classification: reusable workflow building block. It is directly runnable, but its main value is composition into larger domain workflows.
- Why Autoloop fits: the work spans framing, repository inspection, source tracing, gap capture, and durable artifact production across explicit producer/verifier loops.
- Why one-shot is insufficient: scope drift, missing proof, and source constraints must be surfaced through artifacts and verifier-gated local repair instead of disappearing into a single chat summary.

## Invocation

- Package path: `workflows/investigation_request_to_evidence_pack/`
- Discovery: `autoloop workflows show investigation_request_to_evidence_pack`
- Direct run:

```bash
autoloop run investigation_request_to_evidence_pack <task-id> \
  --message "Assemble the evidence pack for the admin impersonation privilege-escalation finding." \
  -wf investigation_title "Admin impersonation privilege escalation" \
  -wf investigation_kind security_remediation \
  -wf sponsor_role "security engineering" \
  -wf evidence_paths pentest/findings/admin-impersonation.md \
  -wf source_constraints "Use repository artifacts and named pentest evidence only."
```

Params:

- `investigation_title` required
- `investigation_kind` required: `release_readiness`, `incident_response`, `security_remediation`, `delivery_recovery`, `customer_escalation`, or `general`
- `sponsor_role` optional
- `evidence_paths` optional and repeatable
- `source_constraints` optional and repeatable

Composed usage stays explicit in workflow code through the authoring-only helper seam:

```python
from autoloop.stdlib import adopt_child_artifacts, run_child_workflow

child = run_child_workflow(
    ctx,
    "investigation_request_to_evidence_pack",
    message="Assemble the release readiness evidence pack.",
    parameters={
        "investigation_title": "Release 2026.04 readiness",
        "investigation_kind": "release_readiness",
        "evidence_paths": ["docs/releases/2026.04.md"],
    },
)
adopt_child_artifacts(
    ctx,
    child,
    mapping={
        "investigation_scope_brief": "adopted/release_scope_brief.md",
        "evidence_pack": "adopted/release_evidence_pack.md",
        "evidence_pack_summary": "adopted/release_evidence_pack_summary.json",
    },
)
```

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | The repository’s workflow-builder and the mandatory comparison baseline for new additions | Already credible enough for the current portfolio, so another builder-first cycle would delay reusable operational leverage | Deferred |
| `security_finding_to_verified_remediation` | High-value domain workflow from finding to bounded fix and closure evidence | Valuable, but it would likely duplicate framing-plus-evidence-pack behavior before extraction is proven | Deferred |
| `investigation_request_to_evidence_pack` | Reusable building block for release, incident, security, delivery, and escalation workflows | Needs explicit composition proof to justify itself as a building block instead of another monolithic workflow | Chosen |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Authoring-only composition helpers | Enables explicit child-workflow invocation and parent-local artifact adoption without widening runtime behavior | Must stay additive and visible in workflow code | Chosen in the paired framework phase and exercised by this building block |
| Runtime-owned subworkflow step | Could make composition terser | Hides sequencing in the runtime and violates the explicit-workflow doctrine | Rejected |
| Recursive wrapper/template cleanup | Fixes known package-CLI drift in `recursive_autoloop/` | Useful, but less directly valuable to evidence-pack authoring than reusable composition proof | Deferred residual |

## Meaningful design decisions

### 1. Building-block boundary

- Alternatives considered:
- evidence assembly only after a parent has already framed the work
- framing plus evidence-pack assembly as one reusable building block
- full investigation through diagnosis and remediation
- Selected: framing plus evidence-pack assembly with deterministic bootstrap and publish edges
- Why: the repeated unit of value in the shipped workflows is not evidence gathering alone, but framed evidence gathering that yields an authoritative pack another workflow can trust.

### 2. Evidence authority strategy

- Alternatives considered:
- make `evidence_pack.md` the only deliverable
- make the receipt the only machine-readable artifact
- keep `evidence_pack.md` as the human-facing deliverable, `evidence_pack_summary.json` as the machine-readable authority, and `evidence_pack_receipt.json` as the deterministic terminal receipt
- Selected: dual human-facing plus machine-readable evidence contract with a separate deterministic receipt
- Why: composition needs a stable JSON handoff artifact, while downstream humans still need a readable evidence narrative.

### 3. Reuse proof strategy

- Alternatives considered:
- migrate `release_candidate_to_go_no_go` immediately
- prove only direct execution
- add a targeted fixture parent workflow that composes the building block through the new helper seam
- Selected: targeted fixture parent composition proof
- Why: it proves reusable composition without expanding the regression surface across already-shipped workflows.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Monolithic pair step | Frame and assemble the evidence pack in one provider-owned loop | Faster to author, but blurs artifact ownership and makes rework less precise | Rejected |
| Explicit two-step package with deterministic bootstrap and publish | Separate framing and evidence-pack assembly, then publish a deterministic receipt | More artifacts to manage, but much clearer contracts and composition value | Selected |
| Immediate migration of existing workflows | Replace the repeated release/incident evidence steps right away | Larger regression surface and weaker isolation for cycle-two proof | Rejected |

## Workflow contract

### Objective

Turn an investigation request into a durable evidence pack that another workflow or human can consume without guessing what was reviewed, what remains missing, or why the scope is authoritative.

### Global deterministic workflow responsibilities

- Bootstrap the authoritative invocation contract from workflow parameters and the run request.
- Hold framing and evidence-pack assembly as separate work items.
- Keep runtime control data narrow: `expected_output_schema`, `available_routes`, step-local `Route.to(...)` metadata, and `required_writes` only.
- Publish a deterministic evidence-pack receipt only after the terminal artifacts exist.

### Provider-owned cognitive responsibilities

- Interpret the investigation request and repository context.
- Frame the investigation boundary, downstream objectives, and evidence intake plan.
- Inspect evidence sources, record concrete findings, and make missing proof explicit.
- Assemble the final evidence pack so a downstream assessor or parent workflow can use it directly.

### Work-item boundary doctrine

- `frame_investigation`: scope, objectives, and evidence intake only.
- `assemble_evidence_pack`: source inventory, coverage, findings, gaps, human-facing evidence pack, and machine-readable summary only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the investigation boundary, downstream consumer, or evidence surface changed materially.

### Role topology

- `investigation strategist` / `investigation critic`
- `evidence assembler` / `evidence verifier`
- deterministic `bootstrap` and `publish_evidence_pack` `python_step`s

### Control flow

1. `bootstrap`
2. `frame_investigation`
3. `assemble_evidence_pack`
4. `publish_evidence_pack`

### Route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `investigation_framed`
- `evidence_pack_ready`
- `needs_rework`
- `needs_replan`
- `evidence_pack_published`

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `frame_investigation` | request, invocation contract, framework docs | `investigation_scope_brief.md`, `investigation_objectives.md`, `evidence_intake_register.md` | authoritative investigation boundary and evidence intake plan |
| `assemble_evidence_pack` | framing artifacts, checklist, and repo evidence | `evidence_source_inventory.md`, `evidence_coverage_matrix.md`, `evidence_findings.md`, `evidence_gap_register.md`, `evidence_pack.md`, `evidence_pack_summary.json` | authoritative evidence pack for downstream assessment or parent-workflow adoption |
| `publish_evidence_pack` | evidence-pack artifacts and summary | `evidence_pack_receipt.json` | deterministic terminal receipt |

Authoritative precedence:

- `investigation_scope_brief.md` and `investigation_objectives.md` become authoritative after framing.
- `evidence_pack.md` is the primary human-facing deliverable.
- `evidence_pack_summary.json` is the machine-readable authority for downstream workflow composition.
- `evidence_pack_receipt.json` is the immutable workflow receipt.

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `InvestigationFramingPayload`
- `InvestigationEvidencePackPayload`

### Prompt templates

The package includes explicit step prompts for:

- `prompts/frame_producer.md`
- `prompts/frame_verifier.md`
- `prompts/evidence_producer.md`
- `prompts/evidence_verifier.md`

Each prompt names the role, purpose, current work item, required reads, required writes, legal routes, evidence rules, and forbidden actions.

### Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose the typed route metadata as normalized runtime metadata.
- A scripted-provider runtime test must prove legal route flow and creation of:
- `invocation_contract.json`
- `investigation_scope_brief.md`
- `evidence_pack.md`
- `evidence_pack_summary.json`
- `evidence_pack_receipt.json`
- A targeted composition proof must show helper-based child invocation plus explicit parent-local adoption of selected child artifacts.

### Rework / replan / block / fail policy

- `needs_rework`: local repair inside the current framing or evidence-pack boundary.
- `needs_replan`: the investigation boundary, consumer need, or evidence plan changed materially.
- `blocked`: required evidence sources or repository prerequisites are missing in a way the current step cannot repair locally.
- `failed`: irreconcilable contradictions make the evidence package non-credible.

### Recursive self-improvement policy

- The building block follows the builder-era package doctrine and exercises the paired composition-helper seam without widening runtime behavior.
- Promotion remains evidence-gated by workflow-local artifacts and runtime proof.
- Broader recursive memory updates remain cycle-level closeout work rather than workflow-local semantics.

## Evidence

- Package implementation: `workflows/investigation_request_to_evidence_pack/`
- Package asset: `workflows/investigation_request_to_evidence_pack/assets/evidence_pack_checklist.md`
- Workflow-specific proof: `tests/runtime/test_investigation_request_to_evidence_pack.py`
- The scripted exercises prove discovery, compilation, direct execution, helper-based composition, artifact adoption, and deterministic publication of `evidence_pack_receipt.json`.
