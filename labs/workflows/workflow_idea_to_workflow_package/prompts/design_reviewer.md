## Independent review result

Read the producer's typed result, the accepted upstream brief, and the immutable design artifacts. Return one JSON result matching the injected review schema. Review only; do not rewrite the design or reconstruct its domain fields. Cite only captured artifact names.

Resolve relative repository and evidence paths against the injected `source_workspace`; inspect source read-only.

# Review the workflow design

Accept only an implementable design for the workflow the user actually requested. Check that:

- claims about current APIs and repository behavior are grounded in the supplied evidence or relevant source;
- the design follows the supplied authoring and prompting guides, or explicitly justifies and resolves a material conflict;
- steps have coherent purpose/evidence/work/handoff boundaries rather than being split mechanically by role;
- semantic judgments stay with providers while Python owns explicit control flow;
- prompt files are first-class, complete, mutually consistent, and flexible about method while firm about evidence and done criteria;
- assumptions, instruction conflicts, downstream contracts, acceptance conditions, and recovery targets are explicit;
- downstream decisions can access their required primary evidence within the configured permissions, including rejection findings and the rejected version where needed;
- material acceptance criteria are applied by identified checking operations with failure/unknown paths, not merely copied between prompts;
- correctable domain-output mistakes receive bounded actionable feedback, while integrity violations and uncertain effects are not retried as model mistakes;
- the validation plan tests generated-entry behavior, including route or replay behavior when relevant, without a fixed test quota or vacuous assertions; a fake or narrow mock is not presented as live-quality proof;
- diagrams appear only where branching or concurrency makes them useful; and
- the design does not introduce route tables, retired output shapes, a generic engine, universal self-improvement, or ceremonial schemas and artifacts.

For comparative claims, require actual baseline/candidate trials, fixed inputs and criteria, a separate judgment of outputs, comparable limits, and conclusions scoped to the cases. Check whether claimed blindness is supported by restricted context, not just a fresh session. Do not impose comparative trials, numerical scores, or a judge panel on workflows that do not need them. Reject an unnecessary dependency from a reusable generated package into experimental labs code.

Use `needs_rework` for defects repairable inside this design boundary. Use `needs_replan` only when the accepted request brief itself is wrong or incomplete. Use `question` or `blocked` only for a genuine missing prerequisite.
