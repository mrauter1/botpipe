# Architecture

Botpipe is a durable-functions runtime for trusted Python workflows.

## The invariant

Python owns control flow. Every material observation or external effect goes
through a recorded Botpipe operation.

The workflow body can use normal functions, conditions, loops, exceptions,
nested workflows, and `parallel()`. Botpipe does not compile that code into a
second state machine. Instead it assigns deterministic operation identities and
replays committed results from a SQLite ledger.

## Ledger and replay

Each run records metadata, source fingerprints, operation intent and outcomes,
provider sessions, human-input events, usage, and immutable artifact references.
Files become durable before the ledger refers to them. A workspace lock protects
one active run from another process.

On replay, a completed operation returns its recorded result. A changed kind,
scope, input, prompt, schema, or source raises a mismatch instead of silently
doing different work. Workflow versions label intentional releases; they do not
bypass source validation.

The automatic fingerprint follows the workflow and referenced Python helpers
and contracts. It is not an immutable process or environment snapshot: provider
installations, external modules, environment values, and configuration semantics
can change outside that source bundle. Authors should bump
`@workflow(version=...)` when those dependencies change meaningfully and start a
new run when the original environment cannot be reproduced.

An operation that may have started an external effect but has no committed
outcome is `interrupted`. Botpipe will not infer that the effect failed or rerun
it. The operator must record the observed response or explicitly authorize a
retry with `Botpipe.resolve()`.

While a workspace has an unresolved uncertain effect, its durable workspace
fence blocks a different run from starting there, even when clients choose
different state directories. Resolve the recorded effect before continuing work
in that workspace.

## Operation boundary

Provider calls, activities, prompt-file reads, human input, worklist snapshots,
and artifact publication are operations. Runtime integrations can use
`current_run().operation(...)` for the same durable boundary.

```python
@activity(retry_safe=False)
def create_ticket(title: str) -> dict[str, str]:
    return remote_api.create_ticket(title)
```

`retry_safe=True` means retry is safe according to the activity contract. It is
not an exactly-once guarantee.

## Scopes and concurrency

The root workflow has a scope. Nested workflows and parallel branches derive
child scopes from deterministic call sites and ordinals. Worklist iteration
stays in the current scope; `Session.work_item()` derives stable provider
identity from the worklist and item ID. Each parallel callable receives an
independent scope, so scheduling order does not change operation identity.
Concurrent mutation through one shared session is rejected. Parallel provider
edits require an explicit isolated workspace per branch; read-only sessions may
share the application workspace.

## Inspection

Before a run, inspection reports the callable signature, typed schemas, policy,
source, and source digest. Python topology is dynamic, so it does not claim to
enumerate future branches. After a run, inspection adds the operations and edges
actually observed. A completed run proves only the path taken for those inputs.
