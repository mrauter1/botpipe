# Test Strategy

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: placeholder-reference-graph
- Phase Directory Key: placeholder-reference-graph
- Phase Title: Placeholder And Reference Graph
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Shared placeholder parser/validator surface coverage:
  `tests/unit/test_placeholder_refs.py`
  Covers prompt, workflow-step message, artifact-template, runtime-template, and worklist-context validation entrypoints through `validate_placeholder_ref(...)`.

- Compiler-owned `ReferenceGraph` population:
  `tests/unit/test_placeholder_refs.py::test_compile_workflow_populates_reference_graph_for_prompt_and_template_surfaces`
  Checks prompt refs, artifact template refs, inferred artifact reads, step output refs, branch refs, fan-in refs, and worklist refs on `WorkflowPlan.reference_graph`.

- Failure-path compiler validation:
  `tests/unit/test_placeholder_refs.py`
  Covers invalid workflow-step message placeholders, invalid artifact-template placeholders, and missing-input-model failures across prompt, workflow-step message, and artifact-template compile surfaces.

- Preserved runtime/rendering invariants:
  `tests/unit/test_placeholder_refs.py`
  Covers runtime rendering quality, artifact-template `ctx.*` rejection, and placeholder resolution behavior that should remain unchanged after centralization.

- Preserved public SDK contract:
  `tests/unit/test_sdk_facade.py`
  Covers `Botlane.run(...)` and `Botlane.step(...)` wrapping placeholder compile failures as `SDKExecutionError`, plus the preserved “requires workflow input” wording for missing-input prompt placeholders.

## Edge Cases

- No workflow `Input` model declared while placeholder surfaces reference `input.*` or `ctx.input.*`.
- Child-workflow message validation failing during compile-time rather than runtime execution.
- Artifact-template validation using step-qualified artifact names rather than bare artifact names in error messages.

## Failure Paths

- Unknown `ctx.state.*` field in workflow-step message compile validation.
- Scoped artifact-template placeholder used without an active scope.
- Missing workflow input surfaced from the centralized compiler validator rather than only via SDK/runtime wrappers.

## Preserved Invariants Checked

- `artifacts.py` remains a thin delegate layer; tests continue asserting the legacy helper names are absent.
- `WorkflowPlan.reference_graph` stays compiler-owned and is populated from canonical plan structures.
- Public SDK entrypoints do not leak raw `WorkflowValidationError` for placeholder-related compile failures.

## Known Gaps

- A broader SDK child-workflow happy-path test still fails outside this phase scope because `ChildWorkflowStepPlan` lacks `.step`; this phase adds regression coverage around placeholder validation only and does not normalize that unrelated runtime issue.
