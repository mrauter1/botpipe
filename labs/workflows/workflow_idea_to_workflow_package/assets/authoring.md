# Authoring durable workflows

A Botpipe workflow is an ordinary typed Python function decorated with
`@workflow`. Python owns durable control flow; provider turns do semantic work
and use tools to gather facts. Design the workflow before writing its code.

## Treat the workflow as an executable SOP

Standardize the outcome, obligations, evidence, authority, handoffs, and recovery
rules—not every worker motion. The workflow is an adaptive operating procedure:
Python makes the durable commitments executable, while capable providers choose
methods that fit the current evidence. It is not a script of guessed clicks,
files, or reasoning steps.

This framing follows established procedure practice: make instructions clear
and reproducible, fit detail to task risk and worker competence, and distinguish
conditional routing from parallel work and joins. See the
[EPA SOP guidance](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=200144GJ.TXT),
[HSE procedure guidance](https://www.hse.gov.uk/humanfactors/topics/procedures.htm),
and [OMG BPMN specification](https://www.omg.org/spec/BPMN/2.0.2/PDF). Botpipe
does not require their document forms or diagrams; the useful principles become
Python control flow and provider-operation contracts.

## Start with the operating contract

Answer these questions. They guide design; they are not required metadata.

1. What outcome must exist at the end, and what obligations must always hold?
2. What evidence establishes success? Which sources are authoritative, and which
   inputs are untrusted or advisory?
3. What can one capable provider turn finish? Where would a durable handoff,
   different permission boundary, independent judgment, or human decision help?
4. For every step, what enters, what leaves, what uncertainty remains, and what
   can the next step safely assume?
5. What can fail or remain ambiguous? Which cases retry, rework, stop, or
   escalate to a person?

Keep goals, obligations, and acceptance evidence stable. Let the provider adapt
its method to the repository and evidence it finds. Prescribe exact procedure
only when order, safety, or reproducibility requires it.

Start with one capable operation. Split it only when an intermediate result must
survive or be reused, permissions differ, independent review protects a material
boundary, work can safely run in parallel, or failure isolation materially helps.
More steps create more handoffs, latency, replay contracts, and context loss.

## Give each step a coherent contract

A useful step has one outcome a capable worker can complete and verify:

- **Goal:** the observable result, not a persona or list of motions.
- **Inputs:** the request, immutable artifacts, and prior decisions. State which
  evidence wins when sources disagree.
- **Output:** a typed domain value and, only when needed, declared files.
- **Authority:** tools and runtime permissions set in Python, plus decisions
  reserved for a person.
- **Uncertainty:** what to report as unknown, blocked, or unverified.
- **Done condition:** concrete checks proportional to the risk.

Preserve continuity across handoffs. Pass the actual decision, evidence, and open
uncertainty—not a vague summary or an unsupported claim that work passed. See
[Prompting provider operations](prompting.md) for prompt design.

## Express topology in Python

| Relationship | Form | Rule |
| --- | --- | --- |
| One result enables the next | sequential calls | Pass the validated value or captured artifact. |
| Exactly one path should run | `if` / `match` | Branch on a typed decision. |
| Several tasks are independent | `parallel` / `aparallel` | Use separate sessions; join after all required branches finish. |
| Work may need correction | bounded `for` loop | Feed exact findings back and define exhaustion. |
| A subprocess needs a replay scope | nested `@workflow` call | Treat the child as a durable unit. |
| Authority or information is human | `ask_human` | Ask a typed, answerable question. |

Parallelism is not branching: a branch selects a path; parallel work executes
multiple required paths. Parallelize only work without an ordering dependency
that can safely share a workspace. Botpipe does not merge or isolate writes.

Use Python for deterministic policy—bounds, routing, budgets, permissions, and
mechanical transformations. Use provider turns for semantic judgment,
investigation, and tool-driven work. Do not imitate semantic review with keyword
checks or a prose-derived route table.

## Bound implementation and review

This producer and reviewer have separate sessions. The reviewer uses `run`
because it must execute tests. Rejection carries exact findings into a bounded
next attempt. Three attempts are illustrative, not a universal recommendation;
choose a bound from consequence, uncertainty, and budget.

```python
from pydantic import BaseModel, Field
from botpipe import Provider, Session, workflow

class Change(BaseModel):
    summary: str
    checks_claimed: list[str] = Field(default_factory=list)

class Review(BaseModel):
    accepted: bool
    findings: list[str] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    checks_unavailable: list[str] = Field(default_factory=list)

@workflow(name="implement", version="1")
def implement(request: str) -> Review:
    producer = Provider(instructions="Implement the requested repository change.")
    reviewer = producer.with_config(
        instructions="Independently verify the change; do not repair it.",
        session=Session(),
    )
    findings: list[str] = []

    for _attempt in range(3):
        change = producer.run(
            "Implement the request and run suitable checks.",
            input={"request": request, "review_findings": findings},
            returns=Change,
        )
        review = reviewer.run(
            "Inspect the current diff and independently run suitable checks. "
            "Separate unavailable checks from failures.",
            input={"request": request, "producer_summary": change.value.summary},
            returns=Review,
        )
        if review.value.accepted:
            return review.value
        findings = review.value.findings

    return Review(accepted=False, findings=findings)
```

Use `query` for inspection-only review. Use `run`, usually without declared
artifacts, when review must execute tests or builds. `writes=()` means no durable
output artifacts; it does not make a call read-only or prevent test caches.
Never claim checks ran when an operation only inspected files. A typed schema
validates response shape, not the truth of its findings.

Add a reviewer only when its verdict changes the next action or protects a
material boundary. Give it a session separate from the producer and direct
access to source, diff, artifacts, and checks. Do not ask it merely to endorse a
producer summary. Isolate the source when review needs a stable tree.

## Choose the operation boundary

| Work | Operation |
| --- | --- |
| Edit files, execute tests/builds, or use write-capable tools | `provider.run` / `arun` |
| Inspect without write-producing checks | `provider.query` / `aquery` |
| Produce a result mainly from supplied context; opt into any tools explicitly | `provider.generate` / `agenerate` |
| Custom API, subprocess, clock, randomness, or material file I/O | `@activity` |
| Typed operator decision or missing input | `ask_human(question, returns=Model)` |

`query` and `generate` are fixed read-only, network-off presets. Configure
sandbox, network, tools, and retry policy in code rather than asking a prompt to
enforce permissions. An enabled remote tool may still have remote effects.
Every material observation or effect belongs in a provider call, activity,
human-input operation, or nested workflow; ordinary workflow Python reruns.

## Artifacts, worklists, and sessions

Prefer typed returns for decisions and compact domain values. Use
`Artifact.json`, `.md`, `.text`, or `.raw` when a file is a durable deliverable or
substantial handoff. Pass declared destinations through `writes`, then pass
returned immutable handles through `reads`. Capture validates current bytes; it
does not prove which concurrent writer created them or form an atomic snapshot.

The shared lab `run_phase` helper adds a narrower convention for artifact-only
producers: each attempt gets a distinct writable directory owned by the current
run, and declared output destinations are remapped inside it. The original
workspace is supplied separately as `source_workspace` for read-only inspection;
it is not the producer's writable workspace or an artifact destination. A
`question` or `blocked` outcome may omit artifacts, while `accepted` must capture
the complete declared set. This is a lab-helper contract, not isolation that
arbitrary `Provider.run` calls receive automatically.

Use `Worklist.from_artifact` when a generated list must keep the same selection
across resume. Give items stable unique IDs, use `Session.work_item(item)` for
item continuity, and call `complete` only after acceptance.

Reusing a provider continues one conversation. `with_config` shares it unless
`session=` replaces it. Use `Session.task(key)` for task continuity, `Session()`
for a distinct durable conversation, and `session=None` for independent turns.
Keep durable keys stable. Give parallel branches different sessions; use
separate worktrees or sequencing when writes can conflict.

## Replay, recovery, and limits

The run's `ledger.jsonl` is the replay authority. Do not add another checkpoint
or receipt to control resume. Completed operations replay recorded results.
Changing a completed operation's prompt, input, read digest, output schema, or
effective configuration can cause a replay mismatch; source hashes are
provenance, not replay keys.

Botpipe does not back up, restore, or roll back workspace files around an
attempt. A retry sees the current workspace. `retry_safe=True` permits another
attempt after a confirmed stop; it does not prove idempotence or exactly-once
execution. Set it false for effects that must not repeat. Unknown or running
effects require reconciliation or operator resolution, not a replacement call.

Bound rework in Python and provider work with
`provider_budget(max_turns=..., max_seconds=..., turn_timeout_seconds=...)`.
Repairs consume budget. Run `timeout` supplies provider-dispatch and session-wait
defaults; it is not a wall-clock deadline for arbitrary workflow Python. A
provider-budget breach suspends the run as `budget_exceeded`; it is not a typed
domain exhaustion result. If callers need such a result, stop at an explicit
domain attempt bound before another dispatch and return it from the workflow.

## Generate a workflow candidate

The packaged [workflow author](../botpipe/workflows/workflow_author/README.md)
applies this guide and the prompting guide to build a workflow package in a
run-owned candidate root. It requires behavioral evidence for the generated
entry point, validates compilation, import, discovery, and a focused generated
test or caller-supplied test argv, and returns typed paths, file hashes, checks,
and errors. The result is a candidate for inspection and deliberate promotion;
the workflow does not copy it into the authoritative workspace. A passing fake
or narrowly mocked check proves only the behavior it exercised, not live-system
quality.

## Authoring checklist

- Outcome, obligations, evidence, and human authority are explicit.
- Every step has coherent inputs, output, uncertainty, and done condition.
- A split, branch, parallel join, loop, or review has a concrete reason.
- Permissions are code, not prompt promises; external effects have honest retry policy.
- Review is independent where needed and its validation claim matches the operation.
- Tests assert outcomes, artifacts, routing, and replay—not exact prose or one path.
