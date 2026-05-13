# Workflow Authoring Guidelines

Botpipe workflows are executable SOPs for strong agentic providers such as Codex
CLI. A provider-backed step is not a small LLM completion. It is a full provider
execution that can inspect the workspace, edit files, run commands, gather
evidence, and continue until the current step contract is satisfied or blocked.

Design workflows for that capability.

## Core Boundary

The workflow owns the global procedure:

- role topology
- step sequence and loops
- work-item boundaries
- artifact contracts
- legal routes
- validation and acceptance gates
- retry, rework, replan, pause, and terminal behavior
- promotion, rollback, and recursive-improvement policy

The provider owns cognition inside the current step:

- repository inspection
- command selection
- analysis and synthesis
- implementation strategy
- local testing and repair
- evidence gathering
- choosing the correct legal route from the current step contract

The runtime owns mechanical enforcement:

- workflow topology validation
- route legality
- required artifact obligations
- structured provider outcome parsing
- selected-route payload and route-field validation
- checkpoint, resume, traces, events, and task state
- provider-policy emission and capability reporting

Do not hide workflow semantics in provider autonomy, and do not turn the runtime
into a second prompt system. The rendered step prompt is the provider's local
execution contract.

## Step Granularity

Prefer high-granularity, coherent steps.

Codex CLI can handle substantial work inside one provider-backed step. Do not
split a workflow into tiny procedural fragments such as "open file", "edit
function", "run tests", and "write summary" unless those fragments have distinct
roles, policies, artifacts, or acceptance gates.

A good step owns one coherent unit of work:

- one primary role or fixed producer/verifier role pair
- one related family of artifacts or repository changes
- one acceptance surface that a verifier can judge
- local repairability when rejected
- clear route semantics

Good step boundaries:

- implement one feature end-to-end, including code edits, relevant tests, and
  validation evidence
- investigate one incident and publish the evidence pack
- assess one release candidate and produce a go/no-go package
- refine one workflow package candidate and publish reviewable diff evidence
- process one worklist item whose artifact family and acceptance criteria are
  stable

Poor step boundaries:

- create a file
- add one import
- run one command
- write an artifact only so a later step can inspect whether it exists
- ask the provider to perform a trivial mechanical action that has no separate
  role, policy, or acceptance gate

Split a step when:

- a different role should own the next decision
- a human or deterministic Python gate must intervene
- the next unit needs a different provider policy
- the artifact family changes materially
- the acceptance surface changes materially
- work should fan out across independent worklist items or branches
- a verifier rejection would require reframing instead of local repair

Use `needs_rework` when the same step boundary still holds and better execution
can fix the problem. Use `needs_replan` when the work item, role, artifact
family, ordering, or acceptance surface was framed incorrectly.

## Producer And Verifier Design

Use `produce_verify_step(...)` for non-trivial, quality-sensitive work.

The producer should do the real work:

- inspect the repository and relevant artifacts
- make code, prompt, docs, or workflow changes when the step owns them
- run relevant checks
- write required artifacts
- record useful evidence
- select a legal route with a concise outcome payload

The verifier is a quality gate. It should judge whether the work is correct,
complete, maintainable, and evidenced. It should not merely check that files
exist or that JSON has the expected keys; runtime schema and artifact validation
already cover mechanical shape.

A verifier should inspect:

- the actual repository diff or produced artifacts
- behavior against the request and acceptance criteria
- tests, command output, or other evidence
- architecture fit and regression risk
- policy, security, and data-handling implications when relevant
- whether the producer respected the step boundary

A verifier should reject when:

- the implementation is incomplete or incorrect
- tests are missing, weak, or failing
- artifacts are semantically shallow even if structurally valid
- the change creates unrelated regressions or architecture drift
- the evidence does not support the claimed route
- local repair is possible and should loop through `needs_rework`
- the original work item was wrong and should route to `needs_replan`

Verifier feedback must be actionable. It should name the concrete gaps to fix,
the evidence that failed, and whether the current boundary still holds.

## Prompt Guidelines

Prompt files, inline prompts, operation prompts, workflow-step messages, and
artifact templates use Jinja. Use explicit roots such as:

```jinja
{{ message }}
{{ request.text }}
{{ input.topic }}
{{ params.mode }}
{{ state.status }}
{{ artifacts.report.path }}
{{ item.id }}
{{ current_worklist.name }}
{{ worklist.review_queue.current.id }}
{{ branch.name }}
{{ fan_in.branch_count }}
{{ fan_in.context_text }}
```

Python handlers use the runtime `ctx` object:

```python
ctx.message
ctx.request.text
ctx.input.topic
ctx.params.mode
ctx.state.status
ctx.artifacts.report
```

Do not use old single-brace prompt syntax such as `{ctx.message}` or
`{input.topic}`. Those are literals in prompts and rejected in artifact
templates.

For Codex CLI backed by GPT-5.5-class models, write prompts as operational
contracts:

- be precise about the role, objective, scope, constraints, and deliverables
- use short sections and bullets instead of dense paragraphs
- include stable rubrics, acceptance criteria, route rules, and artifact
  contracts directly in the prompt
- put task-specific data and dynamic context in clearly labeled Jinja sections
- keep route decisions and final verdicts after inspection and evidence
- ask for concise evidence summaries, not hidden chain-of-thought
- give examples only when they clarify a format or judgment boundary
- avoid conflicting instructions and vague "do your best" language
- rerun workflow tests or eval-style fixtures after meaningful prompt changes
- pin production provider/model config when reproducibility matters

Model prompting guidance changes over time. Keep prompts consistent with current
OpenAI/Codex prompting guidance when upgrading models, but preserve Botpipe's
workflow boundary: the prompt is the local SOP for one step, not the global
workflow controller.

## Canonical Step Prompt Shape

Every provider-backed prompt should make these things explicit when relevant:

1. Role
2. Step purpose
3. Current work item
4. Required inputs and artifacts to read
5. Required outputs and artifacts to write
6. Repository or filesystem scope
7. Evidence requirements
8. Quality bar and acceptance criteria
9. Forbidden actions and non-goals
10. Legal routes and when to choose each route
11. Rework vs replan distinction
12. Expected structured outcome

The runtime renders a shared control contract for routes, required writes, retry
feedback, and structured outcome requirements. The authored prompt should add
the domain-specific judgment and operational context the runtime cannot infer.

## Artifact Doctrine

Filesystem artifacts are the durable system of record.

Use artifacts for:

- plans and workboards
- evidence packs
- review reports
- implementation notes
- validation results
- release decisions
- remediation packages
- candidate diffs and promotion evidence
- machine-readable receipts and summaries

For every meaningful artifact, define:

- name
- path or Jinja path template
- read/write role
- required vs optional status
- overwrite, append, or patch semantics
- downstream consumers
- what makes it authoritative
- how stale or conflicting artifacts should be handled

Do not rely on provider prose alone as the durable deliverable.

## Route Doctrine

Everything is a route.

Application routes are workflow-specific, for example:

- `planned`
- `implemented`
- `accepted`
- `needs_rework`
- `needs_replan`
- `published`
- `blocked`
- `failed`

Helper routes such as `question`, `blocked`, and `failed` are ordinary compiled
routes with conventional defaults. They are only legal when the current step
contract exposes them.

Canonical provider outcomes route through:

```json
{
  "outcome": {
    "tag": "accepted",
    "payload": {},
    "route_fields": {}
  }
}
```

Use `outcome.route_fields.questions` for question-style routes and nullable
`outcome.route_fields.reason` for blocked or failed routes when the selected
route schema requires them. Do not rely on legacy top-level `question` or
`reason` fields in new authoring.

For every route, document:

- what it means
- when it is legal
- what evidence is required
- which artifacts must exist
- where execution goes next

## Policy And Security

Provider policy declares the intended execution posture. Enforcement is backend
dependent and must be reported honestly.

The default Botpipe posture is full-auto sandboxed workspace-write with outbound
network available. That matches the framework's operational use case: Codex can
do real repository work without prompting for every command.

Tighten policy when a workflow needs it:

- read-only review steps should use read-only policy
- implementation steps should restrict writable roots when practical
- regulated, secret-heavy, or deterministic CI workflows should disable network
- dangerous unsandboxed execution should be explicit and rare

Do not overstate backend enforcement. The current Codex CLI emission surface can
set sandbox mode, writable roots, and network access in workspace-write mode, but
does not enforce `deny_read` or domain-level network filters. Botpipe fails by
default when a requested provider-policy control cannot be enforced unless the
operator explicitly changes validation to warn or ignore.

Workflow code, prompt files, Jinja templates, and Python handlers are trusted
author code. Do not run untrusted workflows in sensitive workspaces.

## Worklists, Branches, And Fan-In

Use worklists when the same step contract should run over multiple coherent
items. Each item should have a stable identity, status, payload, and local
artifact path strategy.

Use branch groups when independent role-specific executions should run in
parallel or converge through an explicit fan-in step.

Branch and fan-in prompts should use the runtime roots exposed for their scope,
such as `{{ branch.name }}`, `{{ branch.group }}`, `{{ branch.input }}`,
`{{ fan_in.branch_count }}`, and `{{ fan_in.context_text }}`.
Do not reference branch or fan-in data from prompts that are outside that scope.

The fan-in step is the acceptance surface for the grouped work. It should merge,
rank, reconcile, or reject based on evidence, not just concatenate outputs.

## Recursive Self-Improvement

If a workflow can change workflows, prompts, policy, or artifact schemas, it must
have explicit gates:

- baseline artifacts
- candidate artifacts
- evaluation or regression evidence
- verifier decision
- promotion threshold
- rollback condition
- durable receipt

The provider may propose or implement candidate improvements. It must not
self-promote without deterministic evaluation and verifier acceptance.

## Authoring Checklist

Before shipping a workflow, check:

- The workflow objective is explicit.
- Each provider-backed step is coherent and high enough granularity for Codex
  CLI capability.
- Each verifier is a real quality gate.
- Prompts use Jinja roots, not legacy single-brace placeholders.
- Artifacts are named, durable, and consumed downstream.
- Routes are explicit and have evidence requirements.
- `needs_rework` and `needs_replan` are distinguishable.
- Runtime validation catches deterministic shape errors.
- Provider-policy assumptions match backend capability.
- Resume behavior has stable task, run, worklist, branch, and artifact
  identities.
- Recursive self-improvement cannot bypass evaluation.

Design workflows so the global procedure is deterministic, the provider has
room to do serious work inside each step, the verifier owns acceptance, and the
filesystem preserves the durable evidence.
