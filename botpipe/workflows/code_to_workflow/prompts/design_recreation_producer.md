Goal:
Design a Botpipe workflow that recreates the behavior inventory with equivalent externally observable behavior.

Context:
- Request: {{ message }}
- Invocation contract: {{ workflow.folder }}/invocation_contract.json
- Behavior inventory: {{ workflow.folder }}/behavior_inventory.json
- Behavior report: {{ workflow.folder }}/behavior_inventory.md
- Trace notes: {{ workflow.folder }}/trace_pattern_notes.md
- Botpipe workflow authoring skill: {{ package.folder }}/skills/botpipe-workflow-autoring.md
- Botpipe authoring examples may be provided as readable artifacts.
- If design_review.md exists, read it first and address every required correction.

Deliverables:
- Write `workflow_design.md`.
- Write `step_contracts.json`.
- Write `prompt_contract_matrix.md`.
- Write `equivalence_plan.md`.
- Write `coverage_map.json`.
- Include session topology and rationale in `workflow_design.md`: which generated workflow steps share sessions, which use independent sessions, what context each independent session receives through artifacts, and why those tradeoffs fit the behavior inventory.

Required `coverage_map.json` shape:
{
  "schema": "botpipe.code_to_workflow.coverage_map/v1",
  "coverage": [
    {
      "behavior_id": "behavior-1",
      "status": "implemented",
      "target": "generated step, artifact, route, prompt, or validation",
      "evidence": ["design or validation references"],
      "reason": "required when status is unsupported"
    }
  ]
}

Constraints:
- Use the public `botpipe` authoring surface for generated workflow design.
- Apply the Botpipe workflow authoring skill, especially its provider-heavy, session-design, route, trace, and validation guidance.
- Keep generated output under `.botpipe/workflows/<generated_workflow_name>/`.
- Prefer provider-heavy producer/verifier steps where semantic reasoning is required.
- Use deterministic Python only for narrow bootstrap, validation, and publication duties.
- Do not introduce Botpipe runtime plumbing as generated workflow params unless it is true workflow intent.
- Do not make generated workflow sessions accidentally too granular. Share sessions for dependent continuation work when it improves continuity and efficiency; split sessions where independence, audit quality, parallelism, or scoped repeated work is more important.

Validation:
- Map every behavior inventory id into `coverage_map.json`.
- Mark unsupported behavior only with a concrete reason.
- Ensure the topology can be built as a workspace-local workflow package.

Done criteria:
- The design is directly implementable.
- Every required behavior has a coverage entry.
- Step contracts and prompt matrix are specific enough for the build step without over-prescribing internal code.

Choose the Botpipe topology that best fits the behavior inventory.
