# SDK reference

## Configured providers

`Provider()` is the ordinary configured-provider facade. It is not an adapter
protocol or a type-changing factory. Its backend is selected lazily from the
active run, an attached `Botpipe`, or standalone project configuration, in that
order. The first effective selection pins the provider family.

```text
Provider(
    *,
    runtime=None,
    session=<omitted>,     # managed continuity when supported
    instructions=None,
    model=None,
    effort=None,
    allow_commands=<omitted>,
)
```

`with_config(**settings)` returns the same public type. Omitted fields inherit;
explicit nullable values clear; collections replace. Unknown or unsupported
settings fail before dispatch. Runtime references and native clients are
resources and are not serialized configuration.

Common methods return `Result[T]`:

```text
generate(prompt, *, input=None, session=<omitted>, reads=(),
         allow_commands=<omitted>, returns=str, output_retries=2, ...)
query(prompt, *, input=None, session=<omitted>, reads=(),
      returns=str, output_retries=2, ...)
run(prompt, *, input=None, session=<omitted>, reads=(), writes=(),
    returns=str, output_retries=2, ...)
decide(*, state, questions, ...)
```

Async forms are `agenerate`, `aquery`, `arun`, and `adecide`. Streaming entry
points must name the intended operation and have the same final result contract.

`Result[T]` exposes `value`, `artifacts`, `usage`, `run_id`, `operation_id`, and
explicitly nonportable provider metadata. A result is returned only after typed
validation and required artifact capture commit.

`Codex`, `ClaudeCode`, `Pi`, and `Jev` explicitly select a backend. Their actual
capabilities are adapter-declared and checked before dispatch. Installation of
an adapter does not by itself prove native support for every operation.

JEV keeps its native typed decision shape; it is not converted into a chat
prompt or text verdict:

```python
from botpipe import Jev
from botpipe.decisions import Noul

decision = Jev().decide(
    state={"criteria": criteria, "evidence": evidence},
    questions={
        "satisfied": Noul(
            instructions="Does the evidence satisfy the supplied criteria?"
        )
    },
)
probability = decision.value["satisfied"].noul
```

`Choice` preserves options and probability distributions; `Score` preserves its
ordered legend and distribution; `Noul` returns its truth probability without a
fabricated confidence field. Dependent questions belong in later operations.

## Runtime

```text
client = Botpipe(
    workspace=".",
    state_dir=None,
    provider=<omitted>,        # load the configured project default
    provider_config={},       # adapter-only options
    provider_defaults={},     # common profile/grant/scope defaults
    policy=None,
    contract_registry=None,
    max_operations=1000,
    timeout=3600,
)
```

The default state directory is `workspace/.botpipe-v2`. An explicitly selected
unrecognized or pre-2.0 store is rejected before mutation and must be replaced
with a fresh directory.

`contract_registry` maps a recorded type name to a process-local Python type for
restoring non-importable local or generated contracts. The registry is not
journaled, and a candidate type must exactly match the recorded structural
contract before Botpipe uses it.

An unset provider is valid for provider-free workflows and inspection. A
default `Provider()` call fails with `ConfigurationError` if selection remains
unset.

- `run(workflow_or_name, *args, task_id=None, run_id=None, **kwargs)` starts a
  root and returns `RunResult`.
- `arun(...)` is its async equivalent.
- `resume(run_id, *, answers=None, workflow=None, max_operations=None,
  timeout=None)` resumes. `answers` maps operation IDs to values.
- `pending(run_id)` returns every pending human request.
- `answer(run_id, operation_id, value, *, workflow=None, max_operations=None,
  timeout=None)` targets one request and resumes.
- `resolve(run_id, operation_id, *, retry=... , response=...,
  artifact_digests=None)` records an explicit reconciliation decision.
- `cancel(run_id)`, `inspect(run_id)`, and `runs()` operate on durable history.

Explicit `None` is a response value; omission is represented separately.
`resume` distinguishes stored workflow runs from standalone one-operation runs.
Standalone recovery reconstructs the recorded request and never invents a new
prompt or silently dispatches another task.

`RunResult[T].value` is exactly the workflow function's return. Returning
`result.value` yields the application value; intentionally returning a
`Result[T]` preserves that nested result. Run-wide artifact and usage views do
not overwrite versions or count a physical call twice.

## Workflow API

```python
@workflow(name=None, version="1", policy=None)
def workflow_function(...): ...

@activity(retry_safe=True, retries=0, name=None)
def external_operation(...): ...

ask_human(question, *, returns=str)
parallel(*callables, max_workers=None, settle="all")
```

Activity exception retries remain distinct from provider `output_retries` and
operator reconciliation. `retry_safe=True` allows an unfinished activity to run
again after resume; a completed activity always replays its saved value.

`current_run()` exposes the active workspace, scope, journal, limits, policy,
and a memoized `.provider`. Repeated `.provider` access shares one conversation
for that workflow scope. A separately constructed `Provider()` is a separate
conversation.

## Adapter capability boundary

Internal adapters implement small operation capabilities and native recovery.
They must reject unsupported schema, session, timeout, policy, command-grant,
or continuation controls before dispatch. They may not silently drop a field or
route to another provider.

Deterministic fake adapters are appropriate for workflow tests. Claims about
native generate/query/run support require native integration evidence, including
fresh and resumed session cases. Mock results establish API behavior only.
