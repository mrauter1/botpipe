# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: placeholder-reference-graph
- Phase Directory Key: placeholder-reference-graph
- Phase Title: Placeholder And Reference Graph
- Scope: phase-local authoritative verifier artifact

## Findings

- `IMP-001` `blocking` [botlane/core/compiler.py:439-479] The phase objective says all supported placeholder surfaces should be validated from one parser, but the compiler still only enforces prompt-surface validation. `ChildWorkflowStepPlan.message` refs are parsed and recorded without any validation, and artifact-template validation explicitly swallows `WorkflowValidationError`. Concrete repros from the current tree both compile successfully when they should be rejected by the centralized validator: `simple.workflow_step(Child, message="{ctx.state.missing}")` and `simple.Md("note", path="reports/{item.payload.foo}.md")` on a non-scoped step. That defers malformed `workflow_step_message` / `artifact_template` placeholders to runtime and leaves the phase incomplete against its own acceptance contract. Minimal fix: centralize compiler-side placeholder-surface validation and run it for `prompt`, `workflow_step_message`, and `artifact_template` refs, propagating `WorkflowValidationError` instead of dropping it.
