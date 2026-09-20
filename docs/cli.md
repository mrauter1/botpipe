# Command-line reference

All commands emit JSON to standard output and errors to standard error.
Workflow references accept a catalog name, `module:function`, or
`file.py:function`.

```text
botpipe workflows list [--workspace PATH] [--no-labs]
botpipe workflows show WORKFLOW [--workspace PATH]

botpipe run WORKFLOW [REQUEST] [--input JSON] [--input-file PATH]
    [--arg JSON] [--kw NAME=JSON] [--task-id ID] [--run-id ID]

botpipe resume RUN_ID [--answer JSON|TEXT] [--answer-file PATH]
    [--workflow WORKFLOW]
botpipe answer RUN_ID JSON_OR_TEXT [--workflow WORKFLOW]

botpipe resolve RUN_ID OPERATION_ID (--retry | --response JSON_OR_TEXT)
    [--workflow WORKFLOW] [--no-resume]

botpipe runs list [--workflow NAME] [--task-id ID] [--status STATUS]
botpipe runs show RUN_ID
botpipe runs logs RUN_ID [--operations]
```

Run, resume, resolve, and run-inspection commands accept `--workspace`,
`--config`, `--state-dir`, `--provider`, `--provider-config`, `--policy`,
`--model`, `--effort`, `--max-operations`, and `--timeout`. `--policy` accepts
a JSON object or a JSON/TOML file; `--policy-file` and `--model-effort` remain
accepted aliases. Explicit options override config-file values.

`REQUEST` is a convenient plain string first argument. `--input` accepts a JSON
object as keyword arguments, an array as positional arguments, or a scalar as
one positional argument. `--arg` and `--kw` add individual typed values.

`resume --answer` parses valid JSON and otherwise uses the text verbatim. A
paused run can therefore accept `yes`, `42`, a model object, or a collection.
On resume, an explicit `--max-operations` may increase the recorded operation
budget and `--timeout` updates its positive time limit; omitting them preserves
the original limits.

`workflows list` includes packaged workflows, installed labs, and workspace
workflows under `.botpipe/workflows/`. A workspace workflow with the same name
shadows the other catalog entries.

`resolve` is intentionally explicit. `--retry` authorizes a new attempt only
after recovery confirms the previous attempt stopped. `--response` records what
the operator observed externally under the same condition. A completed provider
receipt takes precedence; running or unknown attempts remain blocked.
For example, `--response null` records an explicit `None` activity result.
Unless `--no-resume` is passed, the command resumes the run after resolution.
