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
continues one conversation by default, and providers derived from it share that
session unless it is replaced. `session=None` means independent turns.
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
`ask_human(question, returns=Model)` validates, records and replays its typed
answer; a missing answer suspends the run.

The run's `ledger.jsonl` is the durable history. Do not add a second checkpoint,
receipt, or summary file to control replay. Provider attempt prompts, resolved
requests and responses are stored beneath the run's `operations/` directory and
referenced from the ledger.

## Artifacts and worklists

Declare files with `Artifact.json`, `Artifact.md` or another constructor. Pass
`writes=(artifact,)` to `run`, then use `result.artifacts.name` to access the
immutable captured version. Required/optional files, schema validation, digest
checks and versioned capture retain their normal semantics. Capture validates
the current file, including a valid file that existed before the attempt; it
does not prove which concurrent writer produced it. Passing an artifact handle
through `reads` gives the next call the immutable input.

Pure inspection reviews should use `query` with a typed verdict. A reviewer that
must execute tests or builds should use a typed `run`, usually without declared
artifact writes. An empty `writes=()` means there are no durable output artifacts;
it does not forbid ordinary test caches, temporary files, or other incidental
workspace effects. Such a reviewer should report failures for the producer to
repair. If a review file is required, save the validated result in an activity.

For lab workflows, let producer calls return typed stage results directly. Add
a separate reviewer only where rejection changes the next action or protects a
material publication boundary. Avoid a mechanical producer/reviewer pair for
every stage. Bound repair loops in Python and carry typed reviewer feedback into
the next producer call.
Read-only presets cannot declare writes. Repair turns run on the same thread and
count against budgets. A validation failure does not roll back repository edits.
Botpipe does not prepare, move, back up, restore, or roll back workspace files
around an attempt. A retry sees and modifies the repository's current state.

`Worklist.from_artifact(handle, collection="items")` snapshots the selected
items durably. The same original selection is visited on every resume, including
items already completed, so workflow control flow and operations replay in the
same order. `Session.work_item(item)` preserves a conversation for that item
across runs of the same task. Call `items.complete(item)` after its acceptance
condition is satisfied; it publishes a new immutable artifact handle and updates
`items.artifact`. See the packaged `ralph_loop` for the complete plan, review,
implement and review cycle.

## Parallel and nested work

Calling another decorated workflow records a child operation and runs it in a
child scope. A completed child replays as a unit. Child operations share the
parent run's operation budget, timeout defaults and provider budgets. Use
`parallel` or `aparallel` to run independent callables. Each branch needs a
separate session. With distinct sessions, writable branches may run at the same
time in the same canonical workspace. Design prompts and artifact destinations
for the resulting shared-state concurrency, or use separate worktrees when the
edits themselves require isolation.

Read-only calls may observe another writer mid-edit. A read declaration records
its captured input, but does not restrict everything Codex may inspect in the
workspace. Do not use a read-only review as a substitute for source isolation
when a stable tree is required.

## Resume and limits

`runtime.resume(run_id)` replays completed operations before continuing. Prompt,
input, read digest, output schema or effective-configuration changes at a
completed operation fail as a replay mismatch. Workflow callable identity is
source-free; source hashes are provenance evidence, not a resume veto. Source
edits are therefore compatible only when execution still reaches and consumes
the recorded operations in the same scopes and order with matching contracts.
Returning early, inserting an operation before a recorded one, or changing one
of those contracts fails replay.

The run's `max_operations` counts recorded operations across child and parallel
scopes. It may be increased, but not decreased, on resume. The run `timeout` is
the default bound for provider dispatches and session-lock waits, not a
wall-clock deadline for arbitrary workflow Python. Use
`provider_budget(max_seconds=...)` for a durable provider deadline. Nested budget
scopes all apply. Every repair dispatch counts against provider budgets;
adopting a recovered response does not dispatch again.
Recovery adopts `Completed`, retries automatically only after confirmed
`Stopped` when both recorded and current policy allow it, makes a bounded
targeted interrupt attempt for `Running`, and leaves `Unknown` unresolved until
operator resolution. Cancellation ends the current invocation without
redispatch; a later explicit resume may retry within policy and limits. Because
parallel turns can share one app-server process, cancellation escalation may
interrupt siblings; recovery reconciles every affected operation as
`Completed`, `Stopped`, or `Unknown`. Botpipe does not promise independent
cancellation. Opt-in remote tools should use `retry_safe=False` when their
effects cannot safely be repeated.
