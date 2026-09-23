# Command line

`botpipe doctor` reports the installed Codex version, required and optional
capabilities, probe identity, preset availability, and the selected workspace's
fence state. A missing required capability exits nonzero with its name. Include
this output in compatibility bug reports. Probing does not need a model turn or
credentials. Use `--workspace PATH` to inspect the exact workspace in question.

```bash
botpipe doctor --workspace .
botpipe workflows list
botpipe workflows show ralph_loop
botpipe run ralph_loop "Add CSV export with tests" --workspace .
```

Workflow references can be catalog names, `package.module:function`, or
`path/to/file.py:function`. Supply typed invocation data with `--input JSON`,
`--input-file FILE`, `--arg JSON` or `--kw NAME=JSON`. Use `--task-id` to group
related executions.

```bash
botpipe runs list --status suspended
botpipe runs show RUN_ID
botpipe runs logs RUN_ID
botpipe runs logs RUN_ID --operations
botpipe resume RUN_ID
botpipe resume RUN_ID --answer 'true'
```

Direct Provider calls appear in the same run list and use the same recovery
commands. Completed operations replay without Codex. A local non-importable
workflow may require `resume --workflow path/to/file.py:function`.

## Resolve uncertain work

```bash
# The operator authorizes another attempt, acknowledging prior effects.
botpipe resolve RUN_ID OPERATION_ID --retry
# Adopt current declared output files after validation.
botpipe resolve RUN_ID OPERATION_ID --accept
# End the operation and run as failed.
botpipe resolve RUN_ID OPERATION_ID --fail
```

`--no-resume` records a resolution without continuing execution. For an activity
with an externally observed return value, use `--response JSON_OR_TEXT`; JSON
`null` is a valid value. Artifact reconciliation can supply an explicit
`--artifact-digests` JSON object when required.

`--accept` captures declared artifacts immediately, before releasing the workspace
fence. Later edits cannot change the accepted versions. If an interrupted turn
has no answer, string results become an empty string; typed results require an
explicit provider response whose `text` matches the recorded output schema,
for example `--response '{"text":"{\"ok\":true}"}'`.

A second process executing the same run receives `RunBusy`. An unresolved
workspace fence names the run that must be resolved before other runs write
that root. Query and generation remain available.

If the owner journal is gone and normal resolution is impossible, the operator
can explicitly abandon the matching fence after independently confirming that
the old work has stopped:

```bash
botpipe resolve RUN_ID OPERATION_ID --clear-fence --workspace PATH
```

`--clear-fence` is the operator's assertion that the abandoned work is stopped.
It does not create or open a runtime journal. Under the workspace mutex, Botpipe
requires the exact workspace, run, and operation identifiers; refuses an
existing or unverifiable owner journal; and atomically archives the fence as a
timestamped `.cleared.*.json` receipt beside it. The JSON output records the
workspace, owner identifiers, journal and fence paths, receipt path, cleared
status, and operator assertion. A missing owner journal never clears a fence
automatically.

## Configuration

`--workspace`, `--config`, `--state-dir`, `--model`, `--effort`,
`--max-operations` and `--timeout` select execution settings. Configuration can
come from `botpipe.toml`, `.botpipe.toml`, `botpipe.json` or `[tool.botpipe]`.
`BOTPIPE_CONFIG` selects an explicit file. Workspace-relative paths use the
chosen workspace. A relative `[codex].path` containing a directory component
uses the configuration file's directory; a bare `codex` is located on `PATH`.

```toml
default_provider = "codex"
max_operations = 500
timeout = 1800

[codex]
path = "codex"
model = "gpt-5.4"
effort = "high"
sandbox = "workspace-write"
network = false
retry_safe = true
interrupt_grace_seconds = 10
```

Codex is the only provider in 2.0. Model names are passed through. There is no
version allowlist. Existing 1.x journals are rejected untouched; choose a new
`--state-dir` for 2.0 work.
