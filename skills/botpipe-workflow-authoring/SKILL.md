---
name: botpipe-workflow-authoring
description: Author, review, and improve Botpipe workflows. Use when Codex is asked to create packaged or workspace-local Botpipe workflows, convert codebases into workflows, design provider-heavy producer/verifier steps, write Botpipe prompts/contracts, inspect Botpipe traces, or apply Codex CLI/gpt-5.5 workflow patterns.
---

# Botpipe Workflow Authoring

## Start with repo truth

Inspect the local Botpipe sources before designing or editing a workflow. Prefer current repository behavior over this skill if they conflict.

Read the most relevant files first:

- `docs/authoring.md`
- `docs/architecture.md`
- `docs/workflow_authoring_guidelines.md` if present
- Compact examples such as `botpipe/workflows/ralph_loop/`
- Mature examples such as `botpipe/workflows/devloop/`
- Meta-workflow examples under `labs/workflows/` when building workflows that generate or optimize workflows

For nontrivial workflow design, also read `references/botpipe-authoring-patterns.md` from this skill.

## Authoring defaults

Use the public authoring surface:

```python
from botpipe import Workflow, Prompt, Route, FINISH
from botpipe import Json, Md, Text, Raw, step, produce_verify_step, workflow_step, python_step
```

Prefer these shapes:

- Workspace-local serious workflow: `.botpipe/workflows/<name>/flow.py` plus optional `specs.py`.
- Packaged workflow: `botpipe/workflows/<name>/__init__.py`, `flow.py` or `workflow.py`, `workflow.toml`, optional `prompts/`, `assets/`, and tests.
- `workflow.toml` is metadata only. Do not put topology, params, prompts, routes, or execution semantics there.

Expose workflow parameters through `Params` and read typed values from `ctx.params`. In bootstrap steps, project typed params into state and invocation artifacts instead of reparsing raw dictionaries.

## Provider-heavy design

Assume the default provider is Codex CLI with `gpt-5.5` unless local configuration says otherwise. Give Codex substantial agency for reasoning, code inspection, implementation choices, and repair loops.

Use deterministic `python_step` handlers only for narrow runtime duties:

- validate and snapshot parameters
- open workflow sessions
- write invocation contracts and publication receipts
- collect manifests or trace summaries
- normalize small structured inputs
- check required artifacts exist

Use `produce_verify_step` for broad work where Codex should reason over a codebase, traces, prompts, tests, or implementation tradeoffs. Producer prompts should specify the goal, evidence, deliverables, constraints, validation commands, and done criteria. They should not over-prescribe how to implement the task unless the repository contract requires it.

Verifier prompts must independently inspect the repository, artifacts, traces, and command output. They should reject with concrete rework instructions when artifacts are missing, behavior coverage is weak, routes are invalid, tests are absent, or validation was only claimed rather than evidenced.

## Artifact shape judgment

Choose artifact formats by how they will be used, not by a default preference for structure. Use JSON, YAML, or Pydantic-shaped artifacts when runtime code, tests, deterministic validators, or downstream steps need stable fields, IDs, statuses, route names, or machine comparison. Keep these schemas small and purposeful.

Use Markdown or other free text when the provider must synthesize context, explain tradeoffs, compare alternatives, review prompt quality, justify adaptations, or record design rationale. Do not turn judgment-heavy work into rigid ledgers, tables, or clause-by-clause checklists unless exact mechanical comparison is truly required.

A good provider artifact should make the next step more capable. Overly narrow schemas can hide important reasoning, encourage shallow field filling, and prevent useful generalization. Prefer a short free-form rationale with stable headings over a large schema when a verifier can judge the result by reading it.

Before adding a structured artifact, ask:

- Will code consume this artifact deterministically?
- Does validation require exact fields or machine comparison?
- Would a rigid schema improve correctness, or just make the provider fill boxes?
- Is the work primarily synthesis, design judgment, adaptation rationale, prompt review, or critique?
- Can a verifier evaluate the artifact better by reading prose plus a few stable headings?

## Session design

Treat sessions as provider conversation continuity. Artifacts remain the durable workflow state, but a shared session can intentionally carry working context so dependent steps do not need to restate every artifact, instruction, or prior decision.

Do not make sessions too granular by default. Consecutive provider steps that extend the same line of reasoning can share a session when prior conversation would reduce rediscovery and make prompts smaller. Split sessions when steps are independent, adversarial, parallel, or should not inherit prior assumptions.

Session reuse has two benefits: continuity and efficiency. It preserves the provider's working context, and providers may cache that context across turns, reducing repeated prompt cost and latency. This makes shared sessions attractive for dependent steps that repeatedly need the same repo framing, constraints, and intermediate decisions.

Use the right context strategy:

- Shared-session continuation: keep prompts focused on the next objective, delta from prior work, required outputs, and validation criteria. Reference prior artifacts by path when useful, but do not restate stable context unless the step needs it refreshed.
- Independent-session boundary: provide enough context through `requires`, `reads`, and prompt text for the step to reason correctly without hidden history.
- Verifier boundary: usually use a separate verifier session. Give it the source criteria, generated artifacts, and review targets it needs, but do not rely on producer chat history unless the tradeoff is explicit.
- Scoped repeated work: use work-item or phase sessions when each item or phase needs its own continuity.

When session reuse conflicts with independence, weigh the tradeoff explicitly. Ask whether the step benefits more from inherited context and cache efficiency, or from a clean reasoning boundary. Independent verifier, audit, and replan steps often benefit from a fresh view, but this is not automatic: if the verifier needs deep shared context and the risk of bias is low or controlled by artifacts, a shared or scoped session may be reasonable. Conversely, if inherited assumptions could hide defects, prefer a separate session and provide the needed context through artifacts and prompt text.

Before choosing a session boundary, ask:

- What context must this step know to perform well?
- Is that context already reliably present in the current session?
- Would restating it through artifacts or prompt text be expensive or clearer?
- How harmful would inherited assumptions be for this step?
- Is the value of independence greater than the value of continuity and cache efficiency?
- If the session were unavailable or stale, are artifacts sufficient to recover?

Session anti-patterns:

- one fresh session per step with weak prompts and weak artifact handoffs
- one shared session for unrelated phases or roles
- restating large context packs on every shared-session continuation
- relying only on session memory across semantic boundaries where artifacts should be authoritative
- verifier sharing producer assumptions when independent review is required

## Common route pattern

Use explicit step-local routes. The usual provider loop is:

- `accepted`: advance to the next step with required writes.
- `needs_rework`: route back to the same step with a handoff requiring the producer to read the verifier artifact.
- `needs_replan`: route back to an earlier design boundary when implementation reveals an invalid plan.
- default helper routes such as `question`, `blocked`, and `failed` remain available unless the workflow intentionally overrides them.

## Trace-informed work

When using traces, prefer run-local and repository-local evidence:

- `.botpipe/tasks/**/runs/**/trace.jsonl`
- `.botpipe/tasks/**/runs/**/run.json`
- `.botpipe/tasks/**/runs/**/static_step_graph.json`
- legacy `.autoloop/tasks/**/runs/**/events.jsonl`
- Codex rollout files nested inside a selected Botpipe run's provider raw artifacts

Do not read broad home-level Codex history by default. Normalize traces into bounded summaries before passing them to provider prompts: retain paths, event types, step names, outcomes, errors, usage, and short excerpts; avoid copying full raw transcripts unless the user explicitly requests it.

## Codebase-to-workflow conversion

For a workflow that recreates a codebase as Botpipe behavior, make Codex own the three semantic stages:

1. `distill_behavior`: read the source code and selected traces, then write a behavior inventory and coverage map.
2. `design_botpipe_recreation`: design params, state, artifacts, steps, prompts, routes, and equivalence checks.
3. `build_and_validate`: write the generated runnable workflow, run validation, repair failures, and record evidence.

Wrap these with deterministic bootstrap and publication steps. Design session boundaries explicitly: each independent stage must receive enough durable artifacts to reason correctly, while rework loops inside a shared stage can lean on session continuity to avoid repeated context dumps. Exclude generated output, `.botpipe/`, `.autoloop/`, virtualenvs, caches, `build/`, and `dist/` from source mutation manifests. Treat equivalence as externally observable behavior unless the user asks for source-level fidelity.

## Before finishing

Validate the workflow through the strongest local surface available:

- import or compile the workflow
- `botpipe workflows show <workflow>` when practical
- targeted tests for params, routes, artifacts, and representative runs
- configured validation commands such as `pytest -q`

Report what was changed and what validation ran. If validation cannot run, state why and identify the remaining risk.
