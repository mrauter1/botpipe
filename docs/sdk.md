# SDK reference

## Client

```python
from botpipe import Botpipe, Policy

client = Botpipe(
    workspace=".",
    provider="codex",            # or a Provider object
    provider_config={"command": ["codex", "exec"]},
    policy=Policy(model="gpt-5.5"),
    state_dir=None,
    max_operations=1000,
    timeout=3600,
)
```

- `run(workflow_or_name, *args, task_id=None, run_id=None, **kwargs)` creates a
  new run and returns `RunResult`. A duplicate `run_id` is rejected.
- `arun(...)` is the async equivalent.
- `resume(run_id, *, answer=..., workflow=None, max_operations=None,
  timeout=None)` resumes. Supply `workflow` for a local callable that cannot be
  imported from stored metadata. `max_operations` may explicitly extend the
  recorded operation budget, and `timeout` may replace its positive limit;
  otherwise the recorded limits remain. Limits belong to the run and its child
  contexts; resuming never changes the client's defaults for another run.
  Operation limits require positive integers; timeouts require finite positive
  numbers. Booleans and silently truncated values are rejected.
  A completed run returns its saved result without executing the workflow or
  changing its limits and revision history.
- `resolve(run_id, operation_id, *, retry=False, response=..., artifact_digests=None)` explicitly
  reconciles an interrupted operation. Choose a resolution, then call
  `resume`; an explicit `None` response records `None` as the activity result.
  Provider reconciliation first checks recovery: an authoritative completed
  response wins over supplied input, and running or unknown attempts remain
  blocked. A manual provider response or retry requires confirmed stopped effects.
  When a completed response has no durable artifact inventory, provide a complete
  `artifact_digests` mapping from declared name to SHA-256 digest (`None` means an
  optional artifact is absent). It may accompany a manual response, but cannot
  accompany `retry=True`. The current files are verified and recorded as operator
  reconciliation, then verified again during capture.
- `runs()` returns run metadata mappings.
- `inspect(run_id)` returns run metadata, operations, events, and artifacts.

`RunResult` contains `run_id`, `task_id`, `status`, `value`, `artifacts`,
`error`, `pending_input`, `folder`, and `usage`. `ok` is true for a completed
run. Status is one of `completed`, `failed`, `awaiting_input`, `interrupted`, or
`budget_exceeded`.

## Authoring API

```python
@workflow(name=None, version="1", policy=None)
def workflow_function(...): ...

@activity(retry_safe=False, retries=0, name=None)
def external_operation(...): ...
```

Implementation edits are allowed between executions. Completed operations retain
their saved outcomes; future operations use current code. Replay matches logical
callable identities, operation positions, and inputs, and checks stored types and
field layout. An explicit `name` supplies the logical activity or workflow name;
otherwise its module and qualified callable name identify it. Workflow `version`
labels a release for observation; it is not a resume gate.

Automatic retry requires both the recorded attempt and current activity to declare
`retry_safe=True`. Editing that flag cannot authorize repeating an earlier unsafe
attempt; use explicit reconciliation when its effect is uncertain.

`Session.run(prompt, *, input=None, reads=(), writes=(), returns=str,
policy=None, name=None, retries=2, workspace=None)` returns a `Result` with
`value`, `artifacts`, `usage`, and `operation_id`. `Session.arun()` is its async
counterpart. `retries` repairs rejected typed output contracts; it never silently
retries an uncertain provider effect. `workspace` selects an explicit isolated
workspace for an editing branch.

`ask(question, *, returns=str)` requests typed operator input.
Submitted answers are validated and durably encoded by the matching `ask`
operation. Invalid or non-durable answers keep the run in `awaiting_input` with
a JSON-safe `pending_input.diagnostic`; a later resume can submit a correction.
`parallel(*callables, max_workers=None, settle="all")` returns ordered results
from independent durable scopes.

External run arguments, provider output, and human answers are normalized at
entry and saved as typed state. Internal workflow and activity calls follow
ordinary Python argument semantics; annotations do not trigger another coercion.
Restoration never revalidates committed model values. Validation must remain
side-effect-free because a crash before its checkpoint can require repeating it.

`provider_budget(*, max_turns, max_seconds=None, turn_timeout_seconds=None)` limits
actual provider dispatches in its dynamic scope. Child workflows and parallel
branches share the same journal-backed counter. Initial calls, typed-output
repairs, and explicitly authorized manual retries each reserve a turn before
dispatch; native receipt recovery does not. Time limits require a
provider with `supports_timeout=True`. The absolute deadline includes suspended
time, survives resume, and never extends. Nested budgets all apply.

## Runtime context

`current_run()` is available inside workflows and activities. It exposes
`workspace`, `folder`, `task_folder`, `task_id`, `run_id`, `scope`, `client`,
`policy`, `limits`, and `journal`. `limits` is the immutable configuration for
the current run, independent of `client.limits` (defaults for new runs).

Each execution appends `execution_revision` events with start and end source
observations. Run metadata retains `provenance_start` and `provenance_end` as
summaries; inspection and optimizer attribution use the complete event history.
Observations record workflow identity, orchestration fingerprint, and package
surface hash when verifiable. Unavailable source stays explicit as
`verified: false`. Any revision changes or unavailable observations prevent the
run from becoming verified evidence for one revision, even if a later execution
returns to the original source.

Verified provenance requires source-backed module definitions. Functions created
later inside another function, transformed bytecode, stale imports, or unavailable
source remain executable but carry unverified provenance.

Integration code can call:

```python
ctx.operation(
    kind="remote-read",
    inputs={"key": key},
    execute=lambda: remote.get(key),
    retry_safe=True,
)
```

The result must use Botpipe's JSON codec. Use this low-level boundary for runtime
integrations; ordinary workflows should prefer sessions and activities.

## Provider boundary

A provider implements `run(ProviderRequest) -> ProviderResponse` and may
implement `recover(request)`. `ProviderRequest` contains the operation ID,
rendered prompt, workspace, session ID, output schema, resolved policy, artifact
destinations, receipt directory, timeout, and attempt number. A provider writes
durable attempt receipts before reporting completion.

Recovery returns `Completed(response)`, `Stopped(detail)`, `Running(detail)`, or
`Unknown(detail)` from `botpipe.recovery`. Completed means the response is
authoritative and no owned attempt can continue writing. Stopped means effects
cannot continue and no completed response exists. Adapters must establish these
facts; a missing receipt is not proof of termination. Legacy response returns
remain supported, while legacy `None` and generic recovery errors mean Unknown.
Native starting receipts without a verifiable process remain Unknown.

Declared output files are preserved before dispatch. When completed output
fails validation, Botpipe quarantines that attempt's files and restores every
previous declared destination before repair. It does not roll back arbitrary
workspace edits or overwrite conflicts from other tools. Interrupted capture or
rollback retains the workspace fence and resumes before further provider work.

`FakeProvider` accepts strings, responses, mappings, or callbacks and records
calls. Use it for tests without a provider CLI.
