# Command line

`botpipe doctor` prints JSON containing the resolved Codex executable and
version, probe hash, methods and feature inventory, derived capability flags,
preset availability, the canonical workspace, and its fence state. A probe
failure still prints the workspace and fence plus `codex.available: false`, then
exits 1. An unavailable `run` preset also exits 1; unavailable optional presets
remain visible without making doctor fail. Include the JSON and stderr in a
compatibility report. Probing runs `codex --version`, `codex features list`, and
app-server schema generation; it does not start a model turn or require model
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
# Equivalent spelling for a scalar answer:
botpipe answer RUN_ID 'true'
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

Exactly one of `--retry`, `--accept`, `--fail`, `--response` and
`--clear-fence` can be supplied. With none of the first four, `resolve` performs
the normal recovery decision. `--no-resume` records a resolution without
continuing execution. For an activity
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

Commands that construct a runtime accept `--workspace`, `--config`,
`--state-dir`, `--provider`, `--provider-config JSON`, `--policy JSON_OR_FILE`,
`--model`, `--effort`, `--max-operations` and `--timeout`. `--model` and
`--effort` are policy overrides. `--policy` accepts a JSON object or a JSON/TOML
file; `--provider-config` accepts a JSON object. Botpipe 2.0 rejects any provider
other than `codex`.

Configuration can come from `botpipe.toml`, `.botpipe.toml`, `botpipe.json`, or
`[tool.botpipe]` in `pyproject.toml`. `BOTPIPE_CONFIG` selects an explicit file.
A relative `state_dir` is resolved from the chosen workspace. A relative
`[codex].path` containing a directory component is resolved from the
configuration file's directory; a bare `codex` is located on `PATH`.

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

The `[codex]` table also accepts `instructions`, `tools`, `timeout`,
`output_retries`, `name`, and non-secret `settings`. CLI execution limits
(`max_operations` and the top-level `timeout`) are distinct from
`[codex].timeout`, which limits a provider call.

Codex is the only provider in 2.0. Model names are passed through. There is no
version allowlist. Existing 1.x journals are rejected untouched; choose a new
`--state-dir` for 2.0 work.
