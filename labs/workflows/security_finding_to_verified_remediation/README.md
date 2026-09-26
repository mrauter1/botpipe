# Security Finding To Verified Remediation

Turn a security finding into an evidence-backed, independently reviewed remediation and verification plan; package outstanding proof without claiming premature closure.

Canonical name: `security_finding_to_verified_remediation`
Aliases: `security-remediation`, `security-finding-remediation`

## Durable function design

`workflow.py` exports one ordinary Python workflow. A reviewed investigation child supplies evidence. Independent reviewers gate exploitability assessment and remediation/verification safety; final packaging preserves those judgments and cannot prove implementation or closure.

Every declared output is required when a phase returns `accepted`. Botpipe snapshots those files before completion, and later phases read immutable handles. A prerequisite-seeking `question` or `blocked` result may pause before files exist; it must not fabricate placeholder artifacts. The final typed `LabWorkflowResult` carries accepted handles in `artifacts` and convenience snapshot paths in `artifact_paths`.

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
    workflow_callable,
    Params(finding_title="Authorization bypass", finding_source="internal_review"),
    request="Assess exposure and plan a verifiable, safely deployed fix",
)
```

Parameters are validated before work starts. `max_provider_turns` (default 32) caps parent and nested child provider work plus retries; human pauses have no wall-clock deadline. `request` supplies finding context.

The parent captures declared `evidence_paths` once, then passes that typed immutable intake to the investigation child; the child never rereads the originals. The public input accepts at most 32 bounded-length paths as a resource limit, not a security-evidence quota. Unsafe, missing, and oversized sources remain unavailable records that can trigger a question or block. Provider attempts use isolated writable scratch, source inspection resolves through `source_workspace`, and any later live discovery is labeled separately from the frozen declared baseline.

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
