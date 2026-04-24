# Eval Suite Checklist

- Keep the selected workflow fixed; this building block authors an eval suite and does not choose a new workflow.
- Publish at least one `benchmark`, one `edge`, and one `adversarial` case.
- Keep `eval_case_manifest.json` as plain JSON with a top-level `cases` array.
- Use only expected artifacts declared on the selected workflow contract.
- Use only supported workflow parameters for the selected workflow.
- Keep `workflow_eval_suite_summary.json` aligned with the case manifest and selected workflow capability.
- Reference `validated_eval_case_manifest.json` and `eval_rubric.md` in the terminal package and next-action artifact.
- Stop at suite publication; do not execute the selected workflow in this run.
