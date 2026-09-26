## Independent review result

Read the producer result, all immutable upstream artifacts, and the runtime candidate records. Return one JSON result matching the injected review schema. Review only; do not repair files or reconstruct producer domain fields. Cite only captured artifact names.

Resolve relative repository and evidence paths against the injected `source_workspace`; inspect source read-only.

# Review package evaluation

Accept only when the evaluation is faithful to the actual generated source and evidence. Cross-check paths, hashes, compile/import/discovery, and configured-test claims against `generated_candidate`, `candidate_manifest`, and `candidate_evaluation`. Then check that the evaluation tested the requested outcome and reviewed design rather than merely file format.

Require explicit findings on prompt completeness, source grounding, instruction contradictions, assumptions, step handoffs, semantic decisions, acceptance/recovery behavior, and downstream contracts. Proven and unproven outcomes must be separated; unavailable or unexecuted checks must not be presented as passes.

When `enforce_generated_test` is true, verify that the focused generated-entry test exists and is substantive. If the caller supplied no explicit test argv, verify that the automatic focused pytest ran; otherwise report the command that actually ran. Check meaningful routing or replay behavior where relevant without imposing a fixed test quota. Vacuous assertions, file-shape checks, and fake or narrow mock execution do not prove live workflow quality.

Use `needs_rework` only when another evaluation pass can correct the evaluation report, package summary, or next-action evidence without changing the candidate. When generated source, prompts, package behavior, or implementation proof is defective, use `needs_replan` and cite the exact evidence; the workflow deliberately returns through `design_workflow` before rebuilding a fresh candidate. Also use `needs_replan` when the design boundary or prompt plan is materially wrong. Use `question` or `blocked` only for a genuine missing prerequisite. Never treat the provider-authored content manifest as proof of materialization or execution.
