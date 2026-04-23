# Recursive Framework Evolution Cycle 2 Plan

## Scope Considered

- No authoritative clarification entries exist beyond the initial request snapshot.
- The request snapshot's mandatory inspection paths are stale. Current equivalents are:
  - `docs/autoloop_workflow_framework_prd.md` -> `docs/architecture.md`
  - `docs/autoloop_workflow_framework_adr.md` -> `docs/authoring.md` and `Workflow_Instructions.md`
  - `src/autoloop/framework/workflows.py` / `pairs.py` -> `core/steps.py`, `core/compiler.py`, `core/context.py`, `core/validation.py`
  - `src/autoloop/framework/store.py` -> `runtime/stores/filesystem.py`
  - `src/autoloop/main.py` -> `runtime/cli.py` and `runtime/runner.py`
  - `src/autoloop/workflows/` -> repo-root `workflows/`
- Current workflow inventory is:
  - `workflows/autoloop_v1/`
  - `workflows/workflow_idea_to_workflow_package/`
  - `workflows/release_candidate_to_go_no_go/`
  - `workflows/incident_to_hardening_program/`
- The workflow-builder is already credible enough that this cycle does not need another builder-first end-to-end workflow. Evidence:
  - explicit builder package topology, prompts, contracts, and docs under `workflows/workflow_idea_to_workflow_package/` and `docs/workflows/workflow_idea_to_workflow_package.md`
  - workflow-specific proof in `tests/runtime/test_workflow_builder_package.py`
  - current targeted baseline during planning:
    - `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py tests/runtime/test_workspace_and_context.py tests/unit/test_stdlib_and_extensions.py`
    - observed result: `25 passed`
- Known pre-existing residual still present during planning:
  - `.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'recursive_wrapper_targets_the_package_cli_contract or recursive_templates_reference_current_package_repo_layout_only'`
  - observed result: `2 failed`
  - cause: `recursive_autoloop/run_recursive_autoloop.sh` still lacks `require_package_autoloop_cli`, and recursive templates still embed legacy `src/autoloop/...` paths
- Repeated workflow pressure is now concentrated in framing-plus-evidence-pack work:
  - `release_candidate_to_go_no_go` and `incident_to_hardening_program` both split into a framing step and an `assemble_evidence_pack` step with materially similar verifier doctrine, route grammar, and gap handling
  - the runtime already supports `ctx.invoke_workflow(...)`, child-run metadata, and isolated child workspaces, but the repo has no small authoring seam for explicit child invocation plus parent-local artifact adoption

## Decision Record: Candidate Additions

| Candidate | Why it matters | Why multi-turn / agentic execution helps | Trade-off | Decision |
| --- | --- | --- | --- | --- |
| Strengthen `workflow_idea_to_workflow_package` again | The builder still lacks explicit proof around reusable building-block authoring | Builder work spans candidate analysis, contract design, file generation, and proof | The builder is already credible for the current repo; another builder-first cycle would delay a real reusable operational package | Deferred |
| `security_finding_to_verified_remediation` | High-value security workflow from finding to bounded impact, fix plan, and closure evidence | Evidence gathering, exploit bounding, remediation design, rollout planning, and verification all benefit from durable artifacts and bounded rework loops | It would likely duplicate the same framing/evidence-pack shape a third time before extraction | Deferred |
| `investigation_request_to_evidence_pack` | Reusable evidence-building block for release readiness, incidents, security findings, delivery recovery, and customer escalations | Evidence intake, source inspection, gap handling, and evidence-pack verification are iterative and artifact-heavy | More reusable than another monolithic workflow, but it needs clean composition support to pay off | Chosen |

Selection rationale:

- The repository no longer lacks a credible workflow-builder, so the highest-leverage move is not more builder-first scope but the first strong reusable building block extracted from already-shipped workflows.
- `investigation_request_to_evidence_pack` solves a real operational problem: teams repeatedly need a decision-ready evidence pack before assessment, remediation, or communication can be trusted.
- Shipping `security_finding_to_verified_remediation` before this extraction would likely hard-code a third copy of the same framing and evidence discipline instead of proving reusable composition.

## Chosen Addition: `investigation_request_to_evidence_pack`

### Problem solved

Turn an ambiguous investigation request such as "Assemble the evidence pack for this privilege-escalation finding" or "Gather the release-readiness evidence for release 2026.04" into a durable, decision-ready evidence pack with explicit scope, objectives, inspected sources, findings, unresolved gaps, and a machine-readable receipt.

### Why it matters

- Release, incident, security, and delivery-recovery work all fail when downstream assessment has to guess what evidence was reviewed, what remains missing, or whether scope drift already occurred.
- A reusable evidence-pack building block is directly valuable even before a later assessment workflow exists, because teams often need a durable pack that another human or workflow can consume.
- This is the first building-block-scale proof that the framework can do more than ship monolithic end-to-end workflows.

### Sponsors and users

- Release manager or engineering manager
- Incident commander or SRE lead
- Security engineer or security-response owner
- Technical program manager or recovery lead
- Customer-escalation owner when an evidence pack must feed a response package

### Classification

This should ship as a reusable workflow building block. It is directly runnable, but its main value is composition: a parent workflow can delegate framing-plus-evidence assembly to it and then continue with domain-specific analysis, remediation, or decision packaging.

### Why Autoloop is a fit

- The work spans framing, repository inspection, evidence inventory, gap capture, and durable artifact production across multiple steps.
- Producer/verifier loops matter because weak source tracing, weak gap handling, or hidden scope drift must trigger bounded rework or replan rather than optimistic continuation.
- The output is artifact-first and naturally reusable across later workflows.

### Why a one-shot interaction is insufficient

- The evidence boundary needs explicit framing before evidence collection starts.
- Evidence intake and source inspection often expose missing proof or a materially changed scope, which needs `needs_rework` versus `needs_replan` behavior.
- The terminal result must be a durable evidence pack, not a transient chat summary.

### Invocation path and public interface

- Package path: `workflows/investigation_request_to_evidence_pack/`
- Discovery:
  - `autoloop workflows show investigation_request_to_evidence_pack`
- Example direct run:

```bash
autoloop run investigation_request_to_evidence_pack <task-id> \
  --message "Assemble the evidence pack for the admin impersonation privilege-escalation finding." \
  -wf investigation_title "Admin impersonation privilege escalation" \
  -wf investigation_kind security_remediation \
  -wf sponsor_role "security engineering" \
  -wf evidence_paths pentest/findings/admin-impersonation.md
```

Planned workflow parameters:

- `investigation_title: str` required
- `investigation_kind: Literal["release_readiness", "incident_response", "security_remediation", "delivery_recovery", "customer_escalation", "general"]` required
- `sponsor_role: str | None` optional
- `evidence_paths: list[str]` optional repeatable repo-path hints
- `source_constraints: list[str]` optional repeatable hints for where evidence may or may not be drawn from

### Intended composition interface

Parent workflows should be able to invoke the building block with an explicit message plus workflow parameters, then promote selected child artifacts into the parent workflow folder. Planned authoring-level interface:

```python
from autoloop_v3.stdlib import adopt_child_artifacts, run_child_workflow

child = run_child_workflow(
    ctx,
    "investigation_request_to_evidence_pack",
    message="Assemble the release evidence pack for 2026.04.",
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
        "investigation_scope_brief": "release_scope_brief.md",
        "evidence_pack": "release_evidence_pack.md",
        "evidence_pack_summary": "release_evidence_pack_summary.json",
    },
)
```

No new runtime-owned step type is planned. Composition must stay explicit in workflow code.

### Terminal outcome

An accepted evidence-pack building block run produces:

- `investigation_scope_brief.md`
- `investigation_objectives.md`
- `evidence_intake_register.md`
- `evidence_source_inventory.md`
- `evidence_coverage_matrix.md`
- `evidence_findings.md`
- `evidence_gap_register.md`
- `evidence_pack.md`
- machine-readable `evidence_pack_summary.json`
- deterministic `evidence_pack_receipt.json`

## Workflow Design Contract For The New Building Block

### Objective

Turn an investigation request into a durable evidence pack that another workflow or human can consume without guessing what was reviewed, what remains missing, or why the scope is authoritative.

### Global deterministic workflow responsibilities

- Bootstrap an authoritative run-local invocation contract from workflow parameters and the run request.
- Keep investigation framing and evidence-pack assembly as separate work items.
- Require producer/verifier behavior on both provider-owned work items.
- Keep runtime injection narrow: only `expected_output_schema`, `available_routes`, and `route_contracts`.
- Publish a final evidence-pack receipt only after the terminal artifacts exist.

### Provider-owned cognitive responsibilities

- Interpret the investigation request and repository context.
- Frame the investigation boundary, objectives, and evidence intake plan.
- Inspect evidence sources, record concrete findings, and make missing proof explicit.
- Assemble the final evidence pack so a downstream assessor can use it directly.

### Work-item boundary doctrine for this building block

- `frame_investigation` owns scope, objectives, and evidence intake only.
- `assemble_evidence_pack` owns source inventory, coverage, findings, gaps, and final evidence-pack assembly only.
- `needs_rework` means the same work-item boundary still holds.
- `needs_replan` means the investigation boundary, target consumer, or evidence surface changed materially.

### Role topology

- `investigation strategist` / `investigation critic`
- `evidence assembler` / `evidence verifier`
- deterministic `bootstrap` and `publish_evidence_pack` system steps

### Control flow as explicit procedure

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
| `frame_investigation` | request, invocation contract, architecture/authoring docs, evidence hints | `investigation_scope_brief.md`, `investigation_objectives.md`, `evidence_intake_register.md` | authoritative investigation boundary and evidence intake plan |
| `assemble_evidence_pack` | framing artifacts plus repo evidence | `evidence_source_inventory.md`, `evidence_coverage_matrix.md`, `evidence_findings.md`, `evidence_gap_register.md`, `evidence_pack.md`, `evidence_pack_summary.json` | authoritative evidence pack for downstream assessment or parent-workflow adoption |
| `publish_evidence_pack` | evidence-pack artifacts and summary | `evidence_pack_receipt.json` | deterministic terminal receipt |

Authoritative precedence:

- `investigation_scope_brief.md` and `investigation_objectives.md` become authoritative after framing.
- `evidence_pack.md` is the primary human-facing deliverable.
- `evidence_pack_summary.json` is the machine-readable authority for downstream workflow composition.
- `evidence_pack_receipt.json` is the immutable workflow receipt.

### Runtime-injected control contract

The building block must rely only on:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `InvestigationFramingPayload`
- `EvidencePackPayload`

Planned route-contract semantics:

- each application route declares `summary`, `required_artifacts`, and `work_item_effect`
- runtime validates route legality and payload schema
- prompt templates remain the provider-facing local SOP

### Step prompt template inventory

| Prompt file | Purpose | Reads | Writes | Legal routes |
| --- | --- | --- | --- | --- |
| `prompts/frame_producer.md` | define the investigation boundary and evidence intake plan | request, invocation contract, framework docs, evidence hints | framing artifacts | `investigation_framed`, reserved routes |
| `prompts/frame_verifier.md` | verify framing quality and route choice | framing inputs plus producer artifacts | verifier feedback only | `investigation_framed`, `needs_rework`, `needs_replan`, reserved routes |
| `prompts/evidence_producer.md` | inspect evidence sources and assemble the evidence pack | framing artifacts and evidence sources | evidence-pack artifacts | `evidence_pack_ready`, reserved routes |
| `prompts/evidence_verifier.md` | verify evidence quality, source tracing, gap handling, and pack completeness | evidence artifacts plus framing | verifier feedback only | `evidence_pack_ready`, `needs_rework`, `needs_replan`, reserved routes |

Prompt doctrine for every file:

- name the role and work-item purpose
- identify exact artifacts to read and write
- specify overwrite handling
- define required evidence and legal routes
- forbid invented evidence, hidden scope drift, or hidden downstream analysis

### Verification and evidence contract

- workflow discovery and compilation must succeed through the package loader
- route-contract normalization must be exercised on each provider-owned step
- add workflow-specific runtime proof, e.g. `tests/runtime/test_investigation_request_to_evidence_pack.py`
- use a scripted provider to prove:
  - legal route flow
  - declared artifacts are created
  - the terminal evidence pack and `evidence_pack_receipt.json` are written
- add one targeted composition proof with a small fixture parent workflow that:
  - invokes the building block through the new helper seam
  - adopts selected child artifacts into the parent workflow folder
  - proves parent-local artifact contracts can stay explicit without a new runtime step type

### Rework / replan / block / fail policy

- `needs_rework`: local repair inside the current framing or evidence-pack boundary
- `needs_replan`: the investigation boundary, intended consumer, or evidence surface changed materially
- `blocked`: required evidence sources or permissions are missing in a way the current step cannot repair
- `failed`: irreconcilable contradictions make the evidence pack non-credible

### Recursive self-improvement policy

- This package is the first explicit reusable evidence-building block and should become a candidate child workflow for future security, release, incident, delivery-recovery, and escalation workflows.
- The package does not self-edit; promotion remains evidence-gated through package-local docs/tests plus recursive-memory updates in the cycle closeout.

## Decision Record: Framework Improvement Candidates

Exactly three core framework improvements were considered for this cycle:

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Authoring-only child-workflow composition helpers | Makes reusable building blocks practical without hiding control flow, and addresses artifact locality directly | Requires careful boundary design so helpers stay additive and explicit | Chosen |
| First-class runtime `SubworkflowStep` | Would make composition look more declarative in workflow definitions | Adds a new runtime-owned control surface, hides sequencing in the engine/compiler, and broadens regression risk | Rejected |
| Recursive wrapper/template package-CLI cleanup | Fixes the known stale `src/autoloop/...` guidance and missing CLI guard | Important but orthogonal to making reusable building blocks expressible and safely composable | Deferred residual |

## Chosen Framework Improvement: Workflow Composition Authoring Helpers

### Goal

Add a small `stdlib` helper seam that keeps child-workflow composition explicit in workflow code while removing the repeated mechanics of child invocation, success gating, and parent-local artifact adoption.

### Planned surface

- New additive helper module under `stdlib/`, e.g. `stdlib/composition.py`
- New exports from `stdlib/__init__.py`
- Authoring guidance in `docs/authoring.md`
- Unit/runtime proof in `tests/unit/test_stdlib_and_extensions.py` and `tests/runtime/test_workspace_and_context.py`

Planned helper responsibilities:

- invoke `ctx.invoke_workflow(...)` explicitly from workflow code
- fail fast when the child run does not end in an allowed status
- copy or materialize selected child artifacts into the parent workflow folder so downstream parent artifacts stay local and explicit
- return enough metadata for the parent workflow to record or branch deterministically

Explicitly out of scope for the helper:

- any new step type in `core/steps.py`
- hidden runtime sequencing in `core/engine.py` or `runtime/runner.py`
- automatic route injection or implicit artifact mapping
- any change to public CLI shape, persisted run metadata shape, or session payload schema

### Compatibility notes

- Public CLI behavior remains unchanged.
- Persisted run metadata and `ChildWorkflowResult` shape should remain backward-compatible unless tests prove a bug that requires a narrow additive fix.
- Existing workflows should keep their current behavior; this cycle intentionally avoids migrating `release_candidate_to_go_no_go` and `incident_to_hardening_program` to the new helper.

## Meaningful Design Decisions

### 1. Addition choice

- Alternatives considered:
  - further strengthen `workflow_idea_to_workflow_package`
  - `security_finding_to_verified_remediation`
  - `investigation_request_to_evidence_pack`
- Selected: `investigation_request_to_evidence_pack`
- Why: it captures a repeated real-world operational unit of work already visible in the shipped release and incident workflows and creates stronger reusable leverage than a third monolithic domain workflow.

### 2. Building-block boundary

- Alternatives considered:
  - evidence assembly only after a parent has already framed the work
  - framing plus evidence-pack assembly as one reusable building block
  - full investigation through diagnosis/remediation
- Selected: framing plus evidence-pack assembly
- Why: direct CLI use stays valuable, the reusable boundary is coherent, and downstream analysis/remediation remains domain-specific rather than forced into an over-general package.

### 3. Composition boundary

- Alternatives considered:
  - parent workflows consume child artifact paths in place from the child run folder
  - authoring-only helper seam that promotes selected child artifacts into the parent workflow folder
  - runtime-owned `SubworkflowStep`
- Selected: authoring-only helper seam with parent-local artifact adoption
- Why: it preserves explicit parent artifact contracts, avoids hidden cross-workflow path coupling, and keeps composition visible in workflow code.

### 4. Proof strategy

- Alternatives considered:
  - ship the building block only and prove it with a direct runtime test
  - migrate the shipped release and incident workflows immediately
  - ship the building block plus helper seam and prove composition with a targeted fixture parent workflow
- Selected: direct runtime proof plus a fixture parent composition proof
- Why: it validates real reuse while keeping regression risk away from the currently shipped end-to-end workflows.

## Implementation Candidates

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Standalone building block only | Add the new package and direct runtime test, but no composition helper or composition proof | Lowest diff, but does not actually prove clean reusable composition | Rejected |
| Building block plus immediate migration of release and incident workflows | Extract the repeated evidence-pack work and wire both shipped workflows to the child package now | Highest reuse proof, but too much regression surface for one cycle | Rejected |
| Building block plus additive composition helper seam and targeted composition proof | Add the package, document/implement helper functions, and prove reuse with a fixture parent workflow | Slightly broader than package-only scope, but the best balance of reuse proof and bounded risk | Selected |

## Milestones

### Milestone 1: Composition Helper Seam

- Add a pure-authoring composition helper module and export it through `stdlib/__init__.py`.
- Document the helper boundary in `docs/authoring.md`.
- Add unit/runtime tests that keep the helper additive and explicit.

### Milestone 2: New Evidence-Pack Building Block

- Create `workflows/investigation_request_to_evidence_pack/` with `__init__.py`, `workflow.py`, `workflow.toml`, `params.py`, `contracts.py`, `prompts/`, and `assets/`.
- Add workflow-local docs under `docs/workflows/investigation_request_to_evidence_pack.md`.
- Add runtime proof for direct execution and targeted parent composition.

### Milestone 3: Proof, Memory, And Closeout

- Run the targeted validation set.
- Update `.autoloop_recursive/framework_evolution_charter.md`, `framework_roadmap.md`, `framework_gap_ledger.md`, and `workflow_candidate_ledger.md`.
- Record scope boundaries, chosen direction, residual wrapper drift, and deferred security workflow follow-up.

## Regression Prevention And Validation

### Affected surfaces

- `stdlib/__init__.py` and new composition helper module
- `docs/authoring.md`
- new workflow package under `workflows/investigation_request_to_evidence_pack/`
- new workflow docs and tests
- recursive memory files under `.autoloop_recursive/`

### Invariants that must remain true

- runtime-owned control surfaces stay limited to `expected_output_schema`, `available_routes`, and `route_contracts`
- no new core/runtime step type or hidden sequencing is introduced
- existing public CLI behavior and persisted session/run metadata stay unchanged
- existing shipped workflows keep their behavior because they are not migrated this cycle
- child-workflow composition remains explicit in workflow code and uses parent-local artifacts where the parent declares them

### Targeted validation

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workspace_and_context.py`
- `.venv/bin/pytest -q tests/runtime/test_investigation_request_to_evidence_pack.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`
- rerun the recursive wrapper/template package-cli subset only if implementation intentionally edits `recursive_autoloop/`

### Compatibility / migration / rollback

- This cycle should be additive only: a new workflow package plus additive `stdlib` helpers and docs/tests.
- No workflow migrations are planned for `release_candidate_to_go_no_go` or `incident_to_hardening_program`.
- If the composition helper cannot stay additive, revert it and keep the new building block standalone rather than widening runtime behavior.
- If the new package cannot be proven safely, remove the new package, docs, and test file together.

## Risk Register

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Building block becomes too generic | An over-abstract package would be hard to author, hard to test, and less useful to real teams | Keep the boundary to investigation framing plus evidence-pack assembly only |
| Composition helper drifts into runtime logic | Hidden sequencing would violate the framework doctrine | Keep helpers in `stdlib/`, not `core/` or `runtime/`, and add explicit tests/docs |
| Parent-child artifact locality becomes muddy | Downstream parent workflows could depend on fragile child-run paths | Prefer explicit parent-local artifact adoption and prove it with a fixture parent workflow |
| Recursive wrapper drift gets confused with the chosen improvement | The known failing recursive-template residual could silently steal scope | Keep wrapper cleanup explicitly deferred unless implementation intentionally expands scope |
