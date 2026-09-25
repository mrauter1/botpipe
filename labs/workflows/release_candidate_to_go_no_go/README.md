# Release Candidate To Go No Go

Frame a release candidate, gather evidence, assess go/no-go readiness, and publish a deterministic decision package.

Canonical name: `release_candidate_to_go_no_go`
Aliases: `release-go-no-go`, `release-readiness`

## Durable function design

`workflow.py` exports one ordinary Python function decorated with `@workflow`. Python controls phase order, optional passes, loops, and nested workflows. Each phase runs one producer with `Provider.run`; the producer returns the package-specific typed domain result from `contracts.py`. Evidence-quality and risk decisions that benefit from independent judgment add a read-only reviewer, whose result contains the review decision and findings rather than a copy of the domain handoff.

Every declared output is a required `Artifact`. Botpipe snapshots the provider-written file before the operation completes, and later phases read those immutable handles. A reviewer, when present, may cite only captured artifact names. The final typed `LabWorkflowResult` carries the accepted handles in `artifacts`, convenience snapshot paths in `artifact_paths`, and unique candidate identifiers. When phases reuse an artifact name, the later accepted handle wins.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.release_candidate_to_go_no_go import Params, workflow_callable

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable, Params(...), request="Describe the requested outcome"
)
```

Parameters are validated by the package-local Pydantic `Params` model before any operation starts. `request` contains the human-readable task or evidence request.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_release` | `release_scope_brief.md`, `decision_criteria.md`, `evidence_intake_register.md` |
| `assemble_evidence_pack` | `release_inventory.md`, `test_evidence_pack.md`, `operational_readiness.md`, `rollback_readiness.md`, `blocking_issues.md` |
| `assess_go_no_go` | `go_no_go_assessment.md`, `risk_register.json`, `decision_summary.json` |
| `prepare_decision_package` | `release_decision_package.md`, `release_communications_draft.md` |

Producer prompts remain phase-specific; independent reviewer prompts exist only for phases where a second judgment materially improves the outcome. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
