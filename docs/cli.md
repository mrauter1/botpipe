# Command-line reference

Commands emit JSON to stdout and diagnostics to stderr. Workflow references may
be catalog names, `module:function`, or `file.py:function`.

```text
botpipe workflows list [--workspace PATH] [--no-labs]
botpipe workflows show WORKFLOW [--workspace PATH]

botpipe run WORKFLOW [REQUEST] [--input JSON] [--input-file PATH]
    [--arg JSON] [--kw NAME=JSON] [--task-id ID] [--run-id ID]

botpipe pending RUN_ID
botpipe answer RUN_ID OPERATION_ID [ANSWER] [--answer-file PATH]
    [--workflow WORKFLOW]
botpipe resume RUN_ID [--workflow WORKFLOW]

botpipe resolve RUN_ID OPERATION_ID (--retry | --response JSON_OR_TEXT)
    [--artifact-digests JSON] [--workflow WORKFLOW] [--no-resume]

botpipe runs list [--workflow NAME] [--task-id ID] [--status STATUS]
botpipe runs show RUN_ID
botpipe runs logs RUN_ID [--operations]
```

Runtime commands accept `--workspace`, `--config`, `--state-dir`, `--provider`,
`--profile`, `--provider-config`, `--policy`, `--model`, `--effort`,
`--generate-commands`, `--query-read-roots`, `--max-operations`, and `--timeout`.
`--provider-config` is an adapter-specific JSON object.
`--generate-commands` is the complete JSON array of exact argv arrays; `[]`
clears configured generation grants. `--query-read-roots` likewise replaces the
configured read scope, and `[]` disables local discovery.

`REQUEST` is a plain string first argument. `--input` accepts a JSON object as
keyword arguments, an array as positional arguments, or a scalar as one
positional argument. `--arg` and `--kw` add individual typed values.

Human answers always target an operation ID. This remains unambiguous when
parallel branches have multiple pending questions. Valid JSON is decoded;
otherwise `ANSWER` is used as text. A rejected typed value leaves the same
request pending and returns a usage exit status.

`resolve` never treats omission as `None`. `--response null` records an explicit
`None` only after recovery permits manual reconciliation. `--retry` authorizes a
new attempt only after the previous effect is confirmed stopped. Running or
unknown effects remain blocked.

Exit statuses are:

| Code | Meaning |
| ---: | --- |
| 0 | Completed successfully |
| 1 | Failed or exceeded a runtime budget |
| 2 | Invalid configuration, input, or typed answer |
| 3 | Workflow or file not found |
| 4 | Awaiting human input |
| 5 | Interrupted operation requires recovery or reconciliation |
| 130 | Interrupted by the caller |

## Configuration precedence

Botpipe uses one source, in this order:

1. `--config PATH` or the SDK `path=` argument.
2. `BOTPIPE_CONFIG`.
3. One workspace `botpipe.toml`, `botpipe.json`, `botpipe.yaml`, or
   `botpipe.yml` file. Multiple discovered files are an error.
4. `[tool.botpipe]` in `pyproject.toml`.

Explicit CLI values then replace the selected file values. Relative source,
state, and read-root paths resolve from `--workspace`. A profile belongs to one
provider; changing `--provider` does not silently reuse the former provider's
default profile.

Serializable provider settings and policies reject credential-bearing keys and
URLs with embedded user information. Supply credentials through the environment,
a credential-source reference, or an injected live adapter so journals and
configuration snapshots never contain the credential value.

Catalog listing reads Python syntax and `workflow.toml` metadata without
importing arbitrary workflow modules. A workspace catalog entry shadows lower
priority labs and packaged entries. Multiple effective declarations with one
name remain visible and execution reports the ambiguity.
