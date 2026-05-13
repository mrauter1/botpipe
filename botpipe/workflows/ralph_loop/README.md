# `ralph_loop`

`ralph_loop` is a minimal packaged implementation workflow for repository work.
It plans a requested change into durable work items, then runs an implementation
and verification loop for each item.

The workflow has two provider-backed steps:

- `plan`: writes `work.json` with ordered implementation items and verifies the plan.
- `implement`: runs once per work item, edits the repository, and verifies the actual implementation.

It is installed with the `botpipe` package and is discoverable as:

```bash
botpipe workflows show ralph_loop
botpipe workflows show ralph
```
