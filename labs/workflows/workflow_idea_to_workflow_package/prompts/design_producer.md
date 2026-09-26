## Durable typed phase result

Return one JSON result matching the injected phase-specific schema and follow the runtime's `artifact_requirement`. Before returning `accepted`, write every declared artifact and ensure it meets this phase's done criteria. For `needs_rework`, `needs_replan`, `question`, `blocked`, or `failed`, write only real evidence that is already available and useful; a control outcome does not require filler artifacts. Never fabricate a file to satisfy the declared acceptance outputs. Cite only artifacts actually captured.

Resolve relative repository and evidence paths against the injected `source_workspace`. The writable working directory is disposable authoring scratch, not the source repository.

# Design the executable workflow

## Purpose

Translate the accepted workflow brief into an implementable, imperative Botpipe design and a first-class prompt design. This is the review boundary before the costly whole-package build.

## Work boundary

Own the workflow's step boundaries, semantic decisions, handoffs, prompts, acceptance evidence, and recovery behavior. Do not write generated source files yet.

## Stable obligations

Write `workflow_design` so an implementer can build without inventing hidden behavior. It must explain:

- the workflow purpose and observable terminal outcome;
- how the supplied authoring and prompting guides govern the fewest coherent steps, semantic judgment, obligations, trust boundaries, permissions, retry/replay behavior, and prompt contracts;
- each coherent step's purpose, authoritative input evidence, work boundary, output handoff, acceptance condition, and local recovery or upstream replan condition;
- which decisions are semantic judgments for a provider and which control decisions Python makes with ordinary conditionals, loops, nested workflows, or bounded parallelism;
- artifact and typed-result handoffs, session continuity or independence, human-input boundaries, side effects, retry safety, and the validation plan;
- the focused behavioral test for `tests/runtime/test_<package_name>.py` when `enforce_generated_test` is true, including meaningful route or replay behavior where relevant, without a fixed test quota or vacuous assertions; when explicit test argv is supplied, explain what it actually proves;
- material assumptions and how the workflow detects contradictions or insufficient evidence.

Use the public, current Python authoring API and repository patterns. Do not introduce route tables, transition grammars, graph compilers, a generic orchestration engine, or a universal recursive-improvement stage. Add an independent reviewer only where a rejection changes the next action or protects a significant boundary. Include a diagram only when it clarifies meaningful branching or concurrency; a linear list of steps does not need one.

Write `prompt_design` as an implementation-ready plan for only the prompt files the workflow actually needs. For each prompt, define its role, purpose, available source evidence, stable obligations, expected semantic handoff, completion evidence, and contradiction/assumption policy. Leave investigation and implementation method flexible where several sound approaches exist. Prompts must assess substantive outcomes, not merely output format, and must not rely on unstated provider memory.

When `rejected_candidate_evidence` is present, trace every relevant source, prompt, validation, or handoff finding to the supplied immutable replan artifacts and runtime records. Preserve sound design decisions, revise the defective ones, and make the next build correction explicit; do not repeat rejected candidate behavior.

Avoid mandatory extra manifests, schemas, prompts, or reports unless runtime discovery, validation, or a real downstream consumer requires them.

## Done criteria

Return `accepted` only when the two artifacts agree, step boundaries are coherent, prompts are complete, recovery targets are unambiguous, and the design can be implemented with existing primitives. Populate `step_names`, `prompt_files`, `semantic_decisions`, and any `unresolved_assumptions` honestly.
