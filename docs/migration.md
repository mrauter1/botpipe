# Migrating from 1.x to 2.0

Version 2.0 retains ordinary Python workflows and the durable journal model,
while making providers the objects that perform work.

| 1.x | 2.0 |
| --- | --- |
| `Session().run(prompt)` | `Provider().run(prompt)` |
| `session = Session(); session.run(...)` | `provider = Provider(session=Session()); provider.run(...)` |
| `ask(question)` | `ask_human(question)` |
| Read-only policy on a provider turn | `provider.query(prompt)` |
| A turn requiring no tools | `provider.generate(prompt)` |
| A provider-specific CLI command | Installed Codex, located by `PATH` or `[codex].path` |
| Claude or other provider | Codex only in 2.0 |

Use `with_config` for roles. It shares the provider's session unless you pass a
new `Session()`; `session=None` makes calls independent. Use `Session.task(key)`
or `Session.work_item(item)` where continuity must have a durable scoped identity.

`query` and `generate` cannot declare writes. Return a typed review and save it
through an activity when a workflow needs a review file. Use a typed `run`
without declared artifacts when verification must execute tests or builds;
`writes=()` does not promise that test caches or temporary files are absent.
Typed returns and artifacts are locally validated with bounded repairs. Invalid
outputs do not roll back arbitrary workspace changes.

In `botpipe.toml`, use `default_provider = "codex"` and a `[codex]` table with
`path`, `model`, `effort`, `sandbox`, `network`, `retry_safe` and
`interrupt_grace_seconds`. `retry_safe` is also available at provider
construction, through `with_config`, per call, and on every async form. Run
`botpipe doctor --workspace PATH` to inspect installed capabilities and the
workspace fence. Codex is not pinned: 0.156.0 is a recorded measured reference,
not a minimum, while CI tests the floating `@openai/codex@latest` resolved by
each job. A real credentialed smoke test is still required to establish live
model behavior for a release.

**1.x journals cannot be opened by 2.0.** They are rejected untouched; there is
no migration. Finish existing work with 1.x or start in a new state directory.
Completed 2.0 operations replay without Codex. Interrupted `run` operations need
reconciliation just like read-only presets. All presets default to
`retry_safe=True`: Botpipe retries only after confirmed `Stopped`, adopts
`Completed`, tries a targeted bounded interrupt for `Running`, and leaves
`Unknown` unresolved. The flag permits repetition rather than proving
idempotence; use `False` for nonrepeatable external effects. It also suppresses
new output-repair dispatches, while an already completed repair still replays.

If an unresolved workspace fence outlives a missing owner journal, it is never
cleared automatically. After independently confirming the old work stopped, use
`botpipe resolve RUN OP --clear-fence --workspace PATH` to assert abandonment
and archive a receipt under the workspace lock.

The provider-first experimental API's `decide`, streaming iterators, exact argv
grants and non-Codex constructors are not included. Progress uses `on_event`.

CLI run inspection is now keyed by one `RUN_ID`:

```bash
botpipe runs show RUN_ID
botpipe runs logs RUN_ID          # one JSON event per line
botpipe runs logs RUN_ID --operations
botpipe resume RUN_ID --answer-file answer.json
```

`botpipe logs RUN_ID` remains an alias for `botpipe runs logs RUN_ID`, and
`botpipe answer RUN_ID VALUE` is the scalar-answer spelling of resume. For a
non-importable file workflow, add `--workflow path/to/file.py:function` when
resuming or resolving it.
