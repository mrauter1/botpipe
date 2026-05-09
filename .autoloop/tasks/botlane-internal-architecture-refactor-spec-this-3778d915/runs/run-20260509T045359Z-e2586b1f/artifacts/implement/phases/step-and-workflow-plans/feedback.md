# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: step-and-workflow-plans
- Phase Directory Key: step-and-workflow-plans
- Phase Title: Step And Workflow Plans
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — `botlane/core/plan_adapters.py::_step_header_from_compiled_step`, `botlane/core/step_plans.py::StepHeader`
  The new adapter stores the full source `CompiledStep` on `StepHeader.original_step`. That silently reintroduces the old optional-field bag, including `route_table`, `available_routes`, `authored_routes`, and provider-visible route tuples, through every typed plan object. This contradicts the phase contract that `StepHeader` must not duplicate canonical route metadata and leaves `WorkflowPlan` with two mutable route sources (`WorkflowPlan.routes` and `header.original_step.route_table`) that can drift. Minimal fix: keep `original_step` as the authored `Step` object and move any parity-only compiled backreference into a dedicated private adapter carrier owned by `plan_adapters.py`, not onto `StepHeader`.

- IMP-002 `blocking` — `botlane/core/plan_adapters.py::compiled_step_from_step_plan`, branch-group round-trip path
  `compiled_step_from_step_plan(...)` only round-trips branch-group plans because `StepHeader.original_step` is secretly a `CompiledStep`; when that backreference is absent, the branch-group path falls back to `branch_group=None`, which yields an invalid `CompiledStep` and proves the typed `BranchGroupPlan` is not self-contained. Concrete failure scenario: a later phase constructs or transforms a `WorkflowPlan` from typed plan fields rather than from `workflow_plan_from_compiled(...)`, then `compiled_workflow_from_plan(...)` loses nested branch-group structure entirely. Minimal fix: centralize the nested branch-group compatibility state in typed plan data or a private adapter-side parity record that is copied explicitly, instead of depending on a hidden `CompiledStep` escape hatch on `StepHeader`.
