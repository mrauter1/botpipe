# `devloop`

`devloop` is the default packaged Botpipe workflow.
It turns a software task request into an explicit plan, executes each phase, and
verifies the result before moving on.

The workflow is intentionally small and general:

- `plan`: produce and verify a phase plan.
- `implement`: execute the active phase.
- `test`: verify the active phase and either continue or request replanning.

It is installed with the `botpipe` package and is discoverable as:

```bash
botpipe workflows show devloop
botpipe workflows show default
```

