Goal:
Distill the current workspace into an evidence-backed behavior inventory for recreating it as a Botpipe workflow.

Context:
- Request: {{ message }}
- Invocation contract: {{ workflow.folder }}/invocation_contract.json
- Source manifest: {{ workflow.folder }}/source_manifest.json
- Trace corpus: {{ workflow.folder }}/trace_corpus.json
- Botpipe authoring examples may be provided as readable artifacts.
- If behavior_review.md exists, read it first and address every required correction.

Deliverables:
- Write `behavior_inventory.json`.
- Write `behavior_inventory.md`.
- Write `trace_pattern_notes.md`.

Required `behavior_inventory.json` shape:
{
  "schema": "botpipe.code_to_workflow.behavior_inventory/v1",
  "summary": "short summary",
  "behaviors": [
    {
      "id": "behavior-1",
      "summary": "externally observable behavior",
      "required": true,
      "evidence": ["source or trace references"],
      "inputs": ["observable inputs"],
      "outputs": ["observable outputs"],
      "error_modes": ["observable failures or edge cases"]
    }
  ]
}

Constraints:
- Treat equivalence as externally observable behavior, not source-level translation.
- Prefer evidence from source files and repository-local traces.
- Do not include broad home-level Codex history.
- Do not overfit to internal implementation details unless they affect observable behavior.

Validation:
- Inspect enough source entrypoints, tests, docs, configs, and trace summaries to justify the inventory.
- If the request narrows scope, honor it and record that scope.

Done criteria:
- Every major user-visible operation, API/CLI contract, data effect, state transition, and error mode has an id.
- Each behavior has concrete evidence.
- Trace notes identify useful trace patterns or state that no useful traces were available.

Choose the analysis approach that best fits the repository.
