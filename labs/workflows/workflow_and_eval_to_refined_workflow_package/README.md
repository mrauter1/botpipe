# Workflow And Eval To Refined Workflow Package

Turn one selected workflow plus evaluation evidence into a candidate workflow surface and typed evaluation result without mutating the authoritative workflow package.

Canonical name: `workflow_and_eval_to_refined_workflow_package`
Aliases: `workflow-refinement-package`, `eval-to-refined-workflow`

## Durable function design

`workflow.py` exports one ordinary Python function decorated with `@workflow`. Python controls phase order, optional passes, loops, and nested workflows. Each phase runs a producer and verifier through durable `Session` operations. Producers return `LabPhaseDraft`; each verifier returns a package-specific `LabPhaseOutcome` subclass from `contracts.py`, so domain evidence is typed before control flow consumes it.

Every declared output is a required `Artifact`. Botpipe snapshots the provider-written file before the operation completes, and later phases read those immutable handles. A verifier may cite only captured artifact names. The final typed `LabWorkflowResult` carries the accepted handles in `artifacts`, convenience snapshot paths in `artifact_paths`, and unique candidate identifiers. When phases reuse an artifact name, the later accepted handle wins.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.workflow_and_eval_to_refined_workflow_package import (
    Params,
    workflow_callable,
)

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable, Params(...), request="Describe the requested outcome"
)
```

Parameters are validated by the package-local Pydantic `Params` model before any operation starts. `request` contains the human-readable task or evidence request.

The workflow accepts exactly one evidence form: the legacy
`evaluation_summary_path` plus `evaluation_findings_path` pair, or an accepted
optimizer-v2 `optimization_receipt_path` plus `candidate_id` pair. The receipt,
review, evidence snapshot, baseline surface, handoff, and selected candidate are
validated as one identity-bound chain. Evaluation-case candidates belong to
`workflow_to_eval_suite`; refinement accepts producer-prompt, verifier-rubric,
token, and workflow candidates.

The workflow copies the selected workflow package into a managed baseline/candidate workspace. The baseline records SHA-256 hashes for every original file. Candidate edits may modify or remove those files and may add files only below the selected package boundary (or explicit `candidate_paths`). The configured `target_test_argv` runs without a shell against an isolated repository overlay. The typed evaluation report records additions, removals, changes, stdout, stderr, timeout status, and return code; evaluation also proves that the authoritative sources retained their baseline hashes.

The project tree and editable surface are frozen before any producer may edit
the candidate. `target_test_command` remains available as a legacy input and is
parsed into argv without a shell; it is mutually exclusive with
`target_test_argv`. `validation_timeout` bounds the configured test command.
When `evaluation_spec_path` is supplied, the workflow materializes disjoint
baseline and candidate arms and performs one frozen paired evaluation. A saved
comparison is reused only after its spec, evaluator, cases, arm identities, and
outputs revalidate. An interrupted attempt is never silently relaunched, and no
comparison automatically promotes the candidate.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_refinement_request` | `refinement_request_brief.md`, `refinement_success_criteria.md` |
| `design_refinement_plan` | `workflow_refinement_plan.md`, `candidate_change_manifest.json` |
| `implement_refined_workflow` | `candidate_workflow_manifest.json`, `candidate_implementation_notes.md` |
| `evaluate_refined_workflow` | `candidate_verification_report.md`, `refinement_summary.json`, `refinement_next_action.md` |

Producer and verifier prompts remain phase-specific. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
