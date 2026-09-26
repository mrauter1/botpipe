# Investigation Request To Evidence Pack

Frame an investigation request, assemble a durable evidence pack, and return typed downstream-readiness evidence.

Canonical name: `investigation_request_to_evidence_pack`
Aliases: `investigation-evidence-pack`, `evidence-pack-building-block`

## Durable function design

`workflow.py` exports one ordinary Python workflow. Python controls framing, evidence assembly, and replanning. The evidence pack receives an independent read-only review because provenance, contradictions, and readiness are the material gate.

Every declared output is required when a phase returns `accepted`. Botpipe snapshots those files before completion, and later phases read immutable handles. A prerequisite-seeking `question` or `blocked` result may pause before files exist; it must not fabricate placeholder artifacts. The final typed `LabWorkflowResult` carries accepted handles in `artifacts` and convenience snapshot paths in `artifact_paths`.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.investigation_request_to_evidence_pack import (
    Params,
    workflow_callable,
)

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable,
    Params(investigation_title="Checkout latency", investigation_kind="general"),
    request="Trace the regression evidence for downstream diagnosis",
)
```

Parameters are validated before work starts. `max_provider_turns` (default 32) caps producers, the reviewer, and retries; human pauses have no wall-clock deadline. `request` contains the evidence question.

Before framing, the workflow captures declared `evidence_paths` once as bounded immutable artifacts. The public input accepts up to 32 paths of bounded length as a resource limit, not a coverage target. Intake accepts only regular, non-symlink files inside the source workspace; missing, unsafe, or oversized entries become explicit unavailable records rather than placeholder evidence. Providers write in isolated per-attempt workspaces, read source through the injected `source_workspace`, prefer frozen declared evidence, and label legitimate additional live discovery separately.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_investigation` | `investigation_scope_brief.md`, `evidence_intake_plan.md` |
| `assemble_evidence_pack` | `evidence_pack.md`, `source_register.json`, `evidence_gaps.md`, `investigation_summary.json` |

Producer prompts remain phase-specific; independent reviewer prompts exist only for phases where a second judgment materially improves the outcome. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
