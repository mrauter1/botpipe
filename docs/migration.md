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
through an activity when a workflow needs a review file. Typed returns and
artifacts are locally validated with bounded repairs. Invalid outputs do not
roll back arbitrary workspace changes.

In `botpipe.toml`, use `default_provider = "codex"` and a `[codex]` table with
`path`, `model`, `effort`, `sandbox`, `network` and `interrupt_grace_seconds`.
Run `botpipe doctor` to inspect installed capabilities. Codex is not pinned.

**1.x journals cannot be opened by 2.0.** They are rejected untouched; there is
no migration. Finish existing work with 1.x or start in a new state directory.
Completed 2.0 operations replay without Codex. Interrupted `run` operations need
recovery or `resolve --retry`, `--accept` or `--fail`; read-only presets retry.

The provider-first experimental API's `decide`, streaming iterators, exact argv
grants and non-Codex constructors are not included. Progress uses `on_event`.
