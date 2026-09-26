## Durable typed phase result

Return one JSON result matching the injected phase-specific schema and follow the runtime's `artifact_requirement`. Before returning `accepted`, write every declared artifact and ensure it meets this phase's done criteria. For `needs_rework`, `needs_replan`, `question`, `blocked`, or `failed`, write only real evidence that is already available and useful; a control outcome does not require filler artifacts. Never fabricate a file to satisfy the declared acceptance outputs. Cite only artifacts actually captured.

Resolve relative repository and evidence paths against the injected `source_workspace`. The writable working directory is disposable authoring scratch, not the source repository.

# Evaluate the materialized package

## Purpose

Decide whether the actual generated source and prompts implement the reviewed workflow and whether executable evidence supports the intended outcome. Format compliance alone is not success.

## Work boundary

Produce honest evaluation and downstream handoff evidence. Do not edit generated files or imply promotion into the authoritative repository.

## Stable obligations

- Treat `candidate_manifest` as authority for materialized paths and hashes, `candidate_evaluation` as authority for checks that actually ran, and `generated_candidate.root` as the isolated location. The provider-authored content manifest is design evidence, not validation proof.
- Compare the generated source and prompts in `workflow_package_manifest` with `workflow_brief`, `workflow_design`, and `prompt_design`.
- Evaluate substantive purpose, step boundaries, Python control flow, semantic decisions, artifact and typed-result handoffs, downstream input/output contracts, acceptance conditions, recovery behavior, and retry safety.
- Evaluate every generated prompt for sufficient source context, stable obligations, flexible method choice, assumption handling, instruction contradictions, semantic completion evidence, and consistency with upstream/downstream prompts.
- Record compile/import/discovery and configured-test results exactly. Distinguish actual executed outcomes from static source inspection, artifact-shape checks, and claims that remain unproven.
- When `enforce_generated_test` is true, require the focused test at `tests/runtime/test_<package_name>.py` to exist and assess whether it exercises generated-entry behavior, including routing or replay where relevant. If no explicit test argv was supplied, require the automatic focused test to have run successfully; otherwise report exactly what the explicit command ran. Reject vacuous proof. Never claim a fake or narrowly mocked execution establishes live workflow quality.
- Write `workflow_evaluation` with findings and residual risks. Write `workflow_package_summary` with the package identity, callable, generated paths, executed checks, decision, proven outcomes, unproven outcomes, and honest downstream interface. Write `workflow_next_action` with concrete repair/redesign work or the later promotion action and reversal scope.

## Done criteria

Return `accepted` with `package_decision="accept"` only when runtime validation succeeded, the source implements the reviewed design, prompts are complete and consistent, and downstream consumers can rely on the summary without guessing.

Use `needs_rework` only when this evaluator can correct its own report, summary, or next-action evidence without changing the materialized candidate. A source, generated prompt, package behavior, or implementation-proof defect cannot be repaired by rerunning evaluation against unchanged bytes: return `needs_replan` with exact findings. The workflow deliberately routes that evidence through `design_workflow` and then builds and validates a fresh isolated candidate. Use `needs_replan` for a design-boundary defect as well.
