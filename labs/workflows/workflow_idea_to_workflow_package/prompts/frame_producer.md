## Durable typed phase result

Return one JSON result matching the injected phase-specific schema and follow the runtime's `artifact_requirement`. Before returning `accepted`, write every declared artifact and ensure it meets this phase's done criteria. For `needs_rework`, `needs_replan`, `question`, `blocked`, or `failed`, write only real evidence that is already available and useful; a control outcome does not require filler artifacts. Never fabricate a file to satisfy the declared acceptance outputs. Cite only artifacts actually captured.

Resolve relative repository and evidence paths against the injected `source_workspace`. The writable working directory is disposable authoring scratch, not the source repository.

# Frame the requested workflow

## Purpose

Turn the workflow the user selected into a source-grounded brief for design. The request is authoritative: do not replace it with an invented candidate exercise, require a portfolio comparison, or insert this builder as a candidate.

## Work boundary

This step decides what the requested workflow must accomplish and what evidence constrains it. It does not design steps or author package files.

## Stable obligations

- Treat the runtime input, repository state, and observed workflow catalog as evidence. Inspect relevant source when a claim about current behavior or API support matters.
- Apply the supplied authoring and prompting guides as authoritative design guidance. Reconcile them with repository policy and surface any material conflict rather than silently choosing one.
- Write `workflow_brief` with the purpose, intended user or sponsor, triggering input, terminal outcome, success evidence, material constraints, and known downstream consumers.
- Separate explicit request facts, repository observations, reasonable assumptions, and unresolved questions. State the consequence of each material assumption.
- Preserve the user's selected workflow even if a similar workflow exists. Note useful reuse or overlap without silently changing the request.
- Define a coherent design handoff: what the next step may rely on and what it still must decide.
- State the real behavioral evidence needed for the generated entry point. Do not treat a fake, vacuous assertion, or file-shape check as proof of live workflow quality.
- Prefer a reasonable, reversible assumption over blocking. Ask only when different answers would materially change safety, scope, or the terminal outcome.

Choose the investigation method that best fits the request. Do not manufacture a fixed number of alternatives or pad the brief with generic process language.

## Done criteria

Return `accepted` when the requested workflow, intended outcome, evidence basis, constraints, and material assumptions are explicit enough to design. Populate `requested_workflow`, `intended_outcome`, and `material_assumptions` from the brief.

Return `needs_rework` when the same request is merely under-evidenced or unclear. Return `needs_replan` only when the current interpretation selects the wrong workflow or outcome.
