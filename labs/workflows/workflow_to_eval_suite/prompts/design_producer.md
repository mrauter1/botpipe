# Design discriminating evaluation cases

Design the smallest suite that covers the meaningful behavior identified in framing. Use case kinds `benchmark`, `edge`, and `adversarial` where they add distinct evidence; do not manufacture redundant cases to satisfy symmetry.

- `benchmark_case_matrix`, `edge_case_matrix`, and `adversarial_case_matrix` document cases of their corresponding kind or explain why that kind is not applicable to this workflow.
- `eval_case_manifest.json` has a top-level `cases` array. Each case defines `case_id`, `case_kind`, `prompt`, `expected_artifacts`, and optional `workflow_parameters`.
- Use only artifacts and parameters declared by `selected_workflow_contract`.
- `eval_rubric` defines observable success, partial success, critical failure, evidence handling, and how uncertainty affects judgment.
- Incorporate an optimizer handoff without changing its candidate identity; never describe development cases as independent validation.

Accept when every case adds a clear pressure and the manifest matches the typed result. Rework case or rubric defects; replan if the target or evaluation dimensions must change. Do not execute cases or claim measured quality.
