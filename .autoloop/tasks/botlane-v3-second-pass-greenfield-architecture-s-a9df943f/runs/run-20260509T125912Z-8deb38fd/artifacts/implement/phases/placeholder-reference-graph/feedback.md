# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: placeholder-reference-graph
- Phase Directory Key: placeholder-reference-graph
- Phase Title: Placeholder And Reference Graph
- Scope: phase-local authoritative verifier artifact

## Findings

- `IMP-001` `non-blocking` [resolved in producer cycle 2] The previously missing centralized compiler validation for `workflow_step_message` and `artifact_template` refs is now present in `botlane/core/compiler.py`; no further action is needed on this finding.
- `IMP-002` `blocking` [botlane/sdk.py:_resolve_and_compile_workflow, botlane/sdk.py:Botlane.run, botlane/sdk.py:Botlane.step] The new compile-time validation for `workflow_step_message` placeholders now leaks raw `WorkflowValidationError` through the public SDK entrypoints instead of preserving the SDK’s established error-wrapping behavior. Concrete repros in the current tree: `Botlane.run(Parent, message="hello")` and `Botlane.step(simple.workflow_step(Child, name="launch", message="{ctx.state.missing}"), message="hello")` both now raise `WorkflowValidationError("workflow step 'launch' message placeholder {ctx.state.missing} references unknown State field 'missing'")`. That is a user-facing compatibility regression against the request’s frozen SDK behavior and exception-wrapping requirements. Minimal fix: normalize compile-time workflow validation failures for SDK-managed execution through the same SDK error boundary as other invocation failures, or otherwise preserve the existing SDK-facing exception class/message contract for invalid child-workflow message placeholders.
