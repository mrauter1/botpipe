Goal:
Build and validate the generated workspace-local Botpipe workflow.

Context:
- Request: {{ message }}
- Invocation contract: {{ workflow.folder }}/invocation_contract.json
- Source manifest: {{ workflow.folder }}/source_manifest.json
- Trace corpus: {{ workflow.folder }}/trace_corpus.json
- Behavior inventory: {{ workflow.folder }}/behavior_inventory.json
- Behavior inventory report: {{ workflow.folder }}/behavior_inventory.md
- Trace pattern notes: {{ workflow.folder }}/trace_pattern_notes.md
- Behavior review: {{ workflow.folder }}/behavior_review.md
- Workflow design: {{ workflow.folder }}/workflow_design.md
- Step contracts: {{ workflow.folder }}/step_contracts.json
- Prompt contract matrix: {{ workflow.folder }}/prompt_contract_matrix.md
- Equivalence plan: {{ workflow.folder }}/equivalence_plan.md
- Coverage map: {{ workflow.folder }}/coverage_map.json
- Design review: {{ workflow.folder }}/design_review.md
- Botpipe workflow authoring skill: {{ package.folder }}/skills/botpipe-workflow-autoring.md
- If build_review.md exists, read it first and address every required correction.

Deliverables:
- Create `.botpipe/workflows/<generated_workflow_name>/`.
- Write `.botpipe/workflows/<generated_workflow_name>/flow.py`.
- Write `.botpipe/workflows/<generated_workflow_name>/workflow.toml`.
- Add `specs.py`, prompts, or assets if the design needs them.
- Write `generated_layout.json`.
- Write `validation_report.md`.

Constraints:
- Keep generated files under the workspace-local output directory.
- Preserve the original source code outside generated output unless the request explicitly says otherwise.
- Do not add unnecessary workflow params.
- Use public `botpipe` imports in generated workflow code where possible.
- Apply the Botpipe workflow authoring skill, especially its guidance on session design, artifact handoffs, provider-heavy implementation, route contracts, and validation.
- For workflow-level artifacts that are read, required, or written by multiple steps, declare stable workflow artifacts rather than step-local simple output helpers. A workflow must pass Botpipe discovery from the target workspace.
- Treat the accepted design as the primary plan, but use the source manifest, trace corpus, behavior report, trace notes, behavior review, and design review as source-of-truth checks when implementation details are ambiguous.
- Implement the session topology from `workflow_design.md` deliberately. Preserve shared sessions where the design uses continuity and cache efficiency; preserve independent sessions where the design relies on clean review, audit, branch, or scoped item context.

Validation:
- Run or explain workflow import/discovery/compile checks, including `botpipe workflows show <generated_workflow_name> --workspace <workspace>` or the equivalent local module command.
- Run relevant local tests or explain why they are unavailable.
- Repair failures caused by the generated workflow.

Done criteria:
- Required generated files exist.
- The generated workflow is directly discoverable and runnable by Botpipe from the target workspace.
- `generated_layout.json` lists generated files and their purpose.
- `validation_report.md` records commands, outcomes, and remaining risks.
- Coverage remains aligned with `coverage_map.json`.

Choose the implementation approach that best fits the accepted design.
