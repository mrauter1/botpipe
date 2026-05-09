# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: sdk-single-step-cutover
- Phase Directory Key: sdk-single-step-cutover
- Phase Title: SDK Single Step Cutover
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [botlane/sdk.py:1827](../../../../../../../../../../botlane/sdk.py:1827) `_build_single_step_workflow_plan(...)` reimplements a large slice of compiler/discovery ownership inside the SDK by importing and orchestrating private helpers such as `_compile_routes`, `_compile_steps`, `_compile_reference_graph`, `_lower_simple_steps`, and `collect_artifact_inventory`. This makes `Botlane.step(...)` a second compilation path rather than a thin SingleStepPlan caller, so future compiler changes to route lowering, artifact inventory, placeholder validation, topology hashing, or step lowering can silently diverge from single-step SDK behavior even though `compile_workflow(...)` still changes correctly. The adjacent child-workflow breakage fixed in this phase is an example of the kind of drift this creates. Minimal fix: centralize one-step plan/workflow-plan construction under compiler-owned code and have `botlane/sdk.py` call that helper instead of rebuilding `WorkflowDefinition` and compiler stages locally.
