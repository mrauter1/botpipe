# Release Candidate To Go No Go

Frame a release candidate, gather evidence, assess go/no-go readiness, and publish a defensible decision package.

Canonical name: `release_candidate_to_go_no_go`
Aliases: `release-go-no-go`, `release-readiness`

## Durable function design

`workflow.py` exports one ordinary Python workflow. Python controls framing and replanning. Independent reviewers gate evidence integrity and the go/no-go judgment; final packaging must preserve the reviewed decision and never executes or approves a release.

Every declared output is required when a phase returns `accepted`. Botpipe snapshots those files before completion, and later phases read immutable handles. A prerequisite-seeking `question` or `blocked` result may pause before files exist; it must not fabricate placeholder artifacts. The final typed `LabWorkflowResult` carries accepted handles in `artifacts` and convenience snapshot paths in `artifact_paths`.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.release_candidate_to_go_no_go import Params, workflow_callable

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable,
    Params(release_name="checkout-api 2.4.0"),
    request="Decide whether this candidate is safe to deploy to production",
)
```

Parameters are validated before work starts. `max_provider_turns` (default 32) caps producers, reviewers, and retries; human pauses have no wall-clock deadline. `request` supplies release context.

Declared `evidence_paths` are captured once before framing under bounded count and byte limits. The public input accepts at most 32 bounded-length paths as a resource limit, not a release-coverage requirement. Only regular, non-symlink source-workspace files become immutable reads; unavailable declarations remain visible and may prevent a decision. Provider attempts write in isolated scratch, use the injected `source_workspace` for read-only source discovery, and label live discoveries separately from the frozen release evidence.

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
