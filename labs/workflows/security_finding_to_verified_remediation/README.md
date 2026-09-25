# Security Finding To Verified Remediation

Turn a security finding into an evidence-backed remediation plan, closure package, and typed closure result.

Canonical name: `security_finding_to_verified_remediation`
Aliases: `security-remediation`, `security-finding-remediation`

## Durable function design

`workflow.py` exports one ordinary Python function decorated with `@workflow`. Python controls phase order, optional passes, loops, and nested workflows. Each phase runs one producer with `Provider.run`; the producer returns the package-specific typed domain result from `contracts.py`. Evidence-quality and risk decisions that benefit from independent judgment add a read-only reviewer, whose result contains the review decision and findings rather than a copy of the domain handoff.

Every declared output is a required `Artifact`. Botpipe snapshots the provider-written file before the operation completes, and later phases read those immutable handles. A reviewer, when present, may cite only captured artifact names. The final typed `LabWorkflowResult` carries the accepted handles in `artifacts`, convenience snapshot paths in `artifact_paths`, and unique candidate identifiers. When phases reuse an artifact name, the later accepted handle wins.

The workflow calls `investigation_request_to_evidence_pack` as a durable child. Its returned `artifacts` handles become immutable reads for the security phases, and its typed result is included in their input context.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.security_finding_to_verified_remediation import (
    Params,
    workflow_callable,
)

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable, Params(...), request="Describe the requested outcome"
)
```

Parameters are validated by the package-local Pydantic `Params` model before any operation starts. `request` contains the human-readable task or evidence request.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `assess_security_finding` | `security_assessment.md`, `threat_scenario.md`, `remediation_acceptance_criteria.md` |
| `plan_verified_remediation` | `remediation_plan.md`, `verification_evidence.md`, `residual_risk.json` |
| `prepare_closure_package` | `security_remediation_package.md`, `security_remediation_summary.json`, `security_next_action.md` |

Producer prompts remain phase-specific; independent reviewer prompts exist only for phases where a second judgment materially improves the outcome. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
