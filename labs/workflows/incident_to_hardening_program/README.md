# Incident To Hardening Program

Frame an incident, assemble evidence, rank likely causes, and publish a durable hardening program and communications package.

Canonical name: `incident_to_hardening_program`
Aliases: `incident-hardening`, `incident-response-package`

## Durable function design

`workflow.py` exports one ordinary Python workflow. Python controls framing and replanning. Independent reviewers gate evidence integrity and causal/mitigation judgment; final program packaging preserves those reviewed decisions and is validated at publication.

Every declared output is required when a phase returns `accepted`. Botpipe snapshots those files before completion, and later phases read immutable handles. A prerequisite-seeking `question` or `blocked` result may pause before files exist; it must not fabricate placeholder artifacts. The final typed `LabWorkflowResult` carries accepted handles in `artifacts` and convenience snapshot paths in `artifact_paths`.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.incident_to_hardening_program import Params, workflow_callable

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable,
    Params(incident_title="Checkout error-rate spike"),
    request="Establish impact, likely causes, and safe hardening follow-through",
)
```

Parameters are validated before work starts. `max_provider_turns` (default 32) caps producers, reviewers, and retries; human pauses have no wall-clock deadline. `request` supplies incident context.

Declared `evidence_paths` are captured once before framing under small file-count and byte limits. The public input accepts at most 32 bounded-length paths as a resource limit, not a required evidence count. Only regular, non-symlink files inside the source workspace become immutable reads; every missing, unsafe, or oversized declaration remains an explicit unavailable record. Each provider attempt writes to isolated scratch, resolves source paths through `source_workspace`, and distinguishes frozen declared evidence from time-bound live discovery.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_incident` | `incident_scope_brief.md`, `response_objectives.md`, `evidence_intake_register.md` |
| `assemble_evidence_pack` | `incident_timeline.md`, `affected_surface.md`, `blast_radius.md`, `observability_gaps.md`, `evidence_gap_register.md` |
| `rank_cause_hypotheses` | `cause_hypothesis_ranking.md`, `immediate_mitigation_plan.md`, `validation_plan.md`, `incident_summary.json` |
| `prepare_hardening_program` | `hardening_program.md`, `hardening_backlog.json`, `follow_up_owners.md`, `stakeholder_communications_draft.md`, `incident_resolution_package.md` |

Producer prompts remain phase-specific; independent reviewer prompts exist only for phases where a second judgment materially improves the outcome. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
