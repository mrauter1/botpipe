# Command line

`botpipe doctor` reports the installed Codex version, required and optional
capabilities, probe identity, and preset availability. A missing required
capability exits nonzero with its name. Include this output in compatibility
bug reports. Probing does not need a model turn or credentials.

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

A second process executing the same run receives `RunBusy`. An unresolved
workspace fence names the run that must be resolved before other runs write
that root. Query and generation remain available.

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
interrupt_grace_seconds = 10
```

Codex is the only provider in 2.0. Model names are passed through. There is no
version allowlist. Existing 1.x journals are rejected untouched; choose a new
`--state-dir` for 2.0 work.
