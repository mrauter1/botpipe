# Migrating to the durable-functions API

This release replaces the graph compiler, routes, mutable workflow state, step
classes, and the filesystem runner with one durable Python runtime. It is a major
API break; existing workflows should be ported rather than wrapped.

The durable API retains the behaviors that matter: provider policy and sessions,
typed outputs, immutable artifacts, worklists, human input, nested workflows,
deterministic concurrency, configuration, CLI history, runtime inspection, and
observation-based optimization. Graph-only topology, route-reporting, compiler,
mutable-state, and checkpoint-repair APIs are retired. Their structural tests
are replaced by behavioral tests at the workflow, interruption, replay,
artifact, and CLI boundaries.

## Authoring changes

| Earlier API | Durable-functions API |
| --- | --- |
| `class Flow(Workflow)` | `@workflow def flow(...):` |
| `step`, `python_step`, `produce_verify_step` | `Session.run` and `@activity` |
| `Route`, `Goto`, `FINISH`, `SELF` | Python `if`, `for`, `while`, calls, returns |
| `ctx.state`, `StateVar`, params classes | local variables and typed arguments |
| workflow artifacts with Jinja paths | `Artifact.*` paths relative to the run folder |
| step transitions and compiled topology | observed operations and runtime scopes |
| input handlers | `ask(..., returns=...)` and `resume(answer=...)` |
| runtime filesystem checkpoint repair | SQLite ledger replay and explicit resolution |

The porting rule is: Python owns control flow, while every material observation
or external effect crosses a recorded operation boundary.

```python
# before
class Review(Workflow):
    draft = produce_verify_step(...)
    transitions = {draft: Route("accepted", FINISH), ...}

# after
@workflow(version="1")
def review(request: Request) -> Report:
    session = Session.task("draft")
    while True:
        draft = session.run("Draft the report.", input=request, returns=Report)
        verdict = Session.fresh().run("Review independently.", input=draft.value, returns=Verdict)
        if verdict.value.accepted:
            return draft.value
```

## Runtime changes

`Botpipe.run()` now accepts the callable (or a discovered name) and its ordinary
arguments. It returns `RunResult`; run history is available through `runs()` and
`inspect()` on the same client. `resume()` uses a run ID, with an optional
workflow only for non-importable local callables.

Provider calls and custom activities are not assumed exactly once. A started
unsafe operation without a committed result becomes `interrupted`. Inspect the
operation, then call `resolve(..., retry=True)` or
`resolve(..., response=observed_value)`.

For providers, both resolutions require recovery evidence. A completed receipt
takes precedence; running or unknown attempts remain blocked. Custom providers
should return explicit outcomes from `botpipe.recovery`. Returning `None` no
longer authorizes replacement of an uncertain provider response.

## Discovery and CLI changes

Catalog names remain supported. Direct references now point to Python functions:
`package.module:function` or `path.py:function`. `workflow.toml` is optional
metadata, not executable topology.

Run inspection distinguishes a declared callable contract from an observed
runtime graph. There is no complete static graph for arbitrary Python control
flow.

Task-based run lookup was replaced by direct run IDs:

```bash
botpipe run ralph_loop "Implement the change" --task-id change-42
botpipe runs show RUN_ID
botpipe resume RUN_ID --answer yes
```

## Persistence compatibility

Old graph-runtime checkpoints are not replayed by the new ledger. Finish old
runs with the earlier major version or start new durable-function runs. Workflow
source changes during a run are rejected rather than automatically migrated.
Automatic source fingerprints follow referenced Python helpers, but they cannot
freeze provider installations, external packages, environment values, or config
semantics. Bump the workflow version when those dependencies change behavior.

Early durable-function snapshots that stored unversioned Pydantic/dataclass
JSON are also incompatible with the validated-state codec. Their omitted state
cannot be reconstructed reliably. Finish those runs using their original code
or start new runs; the decoder refuses silent revalidation as a migration.

Provider checkpoint storage still uses the existing operation response records.
Valid historical states remain readable; unknown or contradictory combinations
are rejected instead of guessing whether a provider can be dispatched again.
This does not override a workflow or operation source mismatch.

Parallel records now include each branch's complete workflow identity. Earlier
parallel records with only a function hash cannot be safely upgraded during
replay. Recorded application exceptions likewise require concrete type and slot
owner source evidence; source-free built-in exceptions retain their explicit
legacy decoding path.

New operation ownership locators are relative to the supplied workflow's source
boundary. Unchanged code can move while preserving that relative layout. Legacy
absolute owner records remain usable at their original locations, but do not
gain relocation support retroactively. Missing owners, changed boundary kinds,
and symlink redirects within relative owner locators are rejected rather than
silently selecting different code. The root anchor uses the supplied workflow's
canonical source location and its separately verified executable identity.
