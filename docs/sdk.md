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
  otherwise the recorded limits remain.
- `resolve(run_id, operation_id, *, retry=False, response=...)` explicitly
  reconciles an interrupted operation. Choose exactly one resolution, then call
  `resume`; an explicit `None` response records `None` as the activity result.
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

@activity(retry_safe=False, retries=0)
def external_operation(...): ...
```

`Session.run(prompt, *, input=None, reads=(), writes=(), returns=str,
policy=None, name=None, retries=2, workspace=None)` returns a `Result` with
`value`, `artifacts`, `usage`, and `operation_id`. `Session.arun()` is its async
counterpart. `retries` repairs rejected typed output contracts; it never silently
retries an uncertain provider effect. `workspace` selects an explicit isolated
workspace for an editing branch.

`ask(question, *, returns=str)` requests typed operator input.
`parallel(*callables, max_workers=None, settle="all")` returns ordered results
from independent durable scopes.

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
`policy`, and `journal`.

Run metadata includes `provenance_start` and `provenance_end`. Each observation
records a workflow identity, orchestration fingerprint, and exact package
surface hash when Botpipe can verify them. Capture failures remain explicit as
`verified: false` with unknown identity fields; Botpipe never substitutes the
current package hash for missing historical provenance. Different verified
start/end surfaces mean the run changed source while executing and must not be
pooled as one stable optimizer baseline.

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

`FakeProvider` accepts strings, responses, mappings, or callbacks and records
calls. Use it for tests without a provider CLI.
