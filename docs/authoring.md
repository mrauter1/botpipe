# Authoring durable workflows

A workflow is an ordinary Python function decorated with `@workflow`. Call it
through `Botpipe.run` or the CLI to create a durable execution. Its ordinary
loops and conditionals decide what happens next.

```python
from pydantic import BaseModel
from botpipe import Botpipe, Provider, workflow

class Verdict(BaseModel):
    accepted: bool
    notes: str = ""

@workflow
def improve(request: str):
    coder = Provider()
    notes = ""
    while True:
        coder.run("Implement the request.", input={"request": request, "notes": notes})
        review = coder.query("Review the implementation.", returns=Verdict)
        if review.value.accepted:
            return review.value
        notes = review.value.notes
```

Provider construction binds lazily to the active runtime. Use `with_config` for
role instructions, models, recovery policy and session choices. A provider
continues one conversation by default; `session=None` means independent turns.
`retry_safe` can be set at construction, with `with_config`, per call, or in the
`[codex]` configuration table.

## Effects and human input

Every material effect or observation belongs in a provider call, activity,
human input operation or nested workflow. Code outside those boundaries reruns
on resume.

```python
from pathlib import Path
from botpipe import activity, ask_human

@activity
def save_review(path: str, text: str) -> str:
    Path(path).write_text(text, encoding="utf-8")
    return path

@activity(retry_safe=False)
def charge_customer(customer: str) -> str:
    # Call a service with application-specific reconciliation.
    raise NotImplementedError
```

Activities and provider turns default to `retry_safe=True`. This permits another
attempt after Botpipe confirms that the interrupted attempt stopped; it is not
proof of idempotence. Use `retry_safe=False` for nonrepeatable effects. That
setting suppresses new automatic recovery attempts and provider output-repair
turns, while a response already completed by an earlier repair can still replay.
Completed operations replay. An interrupted unsafe operation requires resolution.
Activities still default to zero declared exception retries.
`ask_human(question, returns=Model)` validates, journals and replays its typed
answer; a missing answer suspends the run.

## Artifacts and worklists

Declare files with `Artifact.json`, `Artifact.md` or another constructor. Pass
`writes=(artifact,)` to `run`, then use `result.artifacts.name` to access the
immutable captured version. Required/optional files, schema validation, digest
checks and versioned capture retain their normal semantics. Passing an artifact
handle through `reads` gives the next call the immutable input.

Pure inspection reviews should use `query` with a typed verdict. A verifier that
must execute tests or builds should use a typed `run`, usually without declared
artifact writes. An empty `writes=()` means there are no durable output artifacts;
it does not forbid ordinary test caches, temporary files, or other incidental
workspace effects. Such a verifier should report failures for the producer to
repair. If a review file is required, save the validated result in an activity.
Read-only presets cannot declare writes. Repair turns run on the same thread and
count against budgets. A validation failure does not roll back repository edits.

`Worklist.from_artifact(handle, collection="items")` produces durable items.
`Session.work_item(item)` preserves a conversation for that item across resume.
Call `items.complete(item)` after its acceptance condition is satisfied. See the
packaged `ralph_loop` for the complete plan, review, implement and review cycle.

## Parallel and nested work

Calling another decorated workflow creates a journaled child scope. Use
`parallel` or `aparallel` to run independent callables. Each branch needs a
separate session. Writers using the same canonical workspace serialize; use
separate worktrees for independent parallel edits.

Read-only calls may observe another writer mid-edit. A read declaration records
its captured input, but does not restrict everything Codex may inspect in the
workspace. Do not use a read-only review as a substitute for source isolation
when a stable tree is required.

## Resume and limits

`runtime.resume(run_id)` replays completed operations before continuing. Prompt,
input, read digest, output schema or effective-configuration changes at a
completed operation fail as a replay mismatch. Compatible source-edit checks
allow changes that do not alter already committed operation contracts.

Budget scopes, operation limits and deadlines apply during execution. Every
repair dispatch counts; adopting a recovered response does not dispatch again.
Recovery adopts `Completed`, retries automatically only after confirmed
`Stopped` when both recorded and current policy allow it, makes a bounded
targeted interrupt attempt for `Running`, and leaves `Unknown` unresolved until
operator resolution. Cancellation ends the current invocation without
redispatch; a later explicit resume may retry within policy and limits. Opt-in
remote tools should use `retry_safe=False` when their effects cannot safely be
repeated.
