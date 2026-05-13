# Goal: SDK / CLI Parity

## Objective

Make the Botpipe Python SDK a complete superset of the CLI for durable runtime operations, so Python users do not need to shell out for resume, run browsing, event browsing, trace browsing, or SDK task cleanup.

## Required SDK API

Add structured SDK namespaces on `Botpipe`:

- `client.runs.list(...)`
- `client.runs.show(...)`
- `client.runs.resume(...)`
- `client.runs.events(...)`
- `client.runs.trace(...)`
- `client.tasks.list(...)`
- `client.tasks.cleanup(...)`

Preserve existing public SDK behavior:

- Do not break `client.run(...)`.
- Do not break `client.step(...)`.
- Do not break `client.cleanup(...)`.
- Keep `client.cleanup(...)` working as a compatibility-preserving wrapper around `client.tasks.cleanup(...)` unless there is a strong reason not to.

## Run API Requirements

- `client.runs.list(...)` must cover CLI `botpipe runs list` behavior:
  - workflow filter
  - task id filter
  - status filter
  - stable return type suitable for Python callers
- `client.runs.show(workflow, task_id, *, run_id=None)` must cover CLI `botpipe runs show`.
- `client.runs.resume(workflow, task_id, *, run_id=None, ...)` must cover CLI `botpipe resume`.
- Run selection must be deterministic:
  - use the same `latest`, `latest_resumable`, and `latest_paused` semantics as current CLI where appropriate
  - raise clear SDK errors for missing, non-resumable, or ambiguous runs
- Do not duplicate durable resume logic between CLI and SDK.

## Events And Trace Requirements

- `client.runs.events(...)` must expose run events as an async iterator.
- `client.runs.trace(...)` must expose trace records as an async iterator.
- Support existing completed-file browsing and tail-style live inspection.
- Yield parsed JSON records by default.
- Handle empty or missing files, partial lines, malformed JSON, and run completion predictably.
- Avoid busy waiting; provide a polling interval for follow mode.
- Provide enough selector arguments to avoid ambiguous task-only lookup:
  - at minimum support workflow, task id, and optional run id
  - optionally support ergonomic task-first overloads if ambiguity is handled safely

## Task API Requirements

- `client.tasks.list(...)` must list durable task records from `.botpipe/tasks`.
- `client.tasks.cleanup(...)` must perform the current SDK cleanup behavior safely.
- Cleanup must continue to delete only SDK-managed task directories identified by the Botpipe SDK sentinel.
- Cleanup must preserve `dry_run`, `older_than`, and `include_failed` behavior.

## CLI Parity Requirement

Refactor CLI handlers so Botpipe CLI becomes argparse plus formatter over SDK calls.

Examples:

- `botpipe runs list ...` delegates to `client.runs.list(...)`
- `botpipe runs show review task-42` delegates to `client.runs.show("review", "task-42", ...)`
- `botpipe resume review task-42` delegates to `client.runs.resume("review", "task-42", ...)`
- `botpipe logs --events ...` delegates to `client.runs.events(...)` or the same SDK-backed read helper
- `botpipe logs --trace ...` delegates to `client.runs.trace(...)` or the same SDK-backed read helper

Do not leave parallel implementations in CLI and SDK.

## Architectural Constraints

- SDK must not import CLI.
- CLI may import and use the Botpipe SDK.
- Shared lower-level helpers may remain in `botpipe.runtime.workspace` and `botpipe.runtime.inspection`.
- Keep data models small and stable; prefer dataclasses or existing runtime record types where appropriate.
- Do not introduce compatibility shims for old names or old package identities.
- Preserve behavior except for the intentional addition of SDK capabilities and CLI delegation.

## Testing Requirements

Add or update tests proving:

1. `client.runs.list(...)` returns the same run set as CLI `runs list`.
2. `client.runs.show(...)` returns the same run metadata as CLI `runs show`.
3. `client.runs.resume(...)` resumes the same run the CLI would resume.
4. Non-resumable and missing runs raise SDK errors with useful messages.
5. `client.runs.events(...)` can iterate existing events from `events.jsonl`.
6. `client.runs.events(..., follow=True)` observes appended events without busy looping.
7. `client.runs.trace(...)` can iterate existing trace records.
8. Missing or empty event and trace files behave predictably.
9. `client.tasks.list(...)` lists durable task records.
10. `client.tasks.cleanup(...)` preserves current cleanup behavior.
11. Existing `client.cleanup(...)` still works.
12. CLI handlers delegate to SDK methods or otherwise share the exact implementation path.
13. Existing CLI behavior and JSON output remain compatible.
14. Full test suite passes.

## Suggested Validation Commands

Run at minimum:

```bash
.venv/bin/python -m pytest tests/unit/test_sdk_facade.py
.venv/bin/python -m pytest tests/runtime/test_package_cli.py
.venv/bin/python -m pytest tests/runtime/test_workspace_and_context.py
.venv/bin/python -m pytest
```

## Completion Audit

Before marking complete:

- Inspect `botpipe/sdk.py`, `botpipe/runtime/cli.py`, `botpipe/runtime/inspection.py`, and `botpipe/runtime/workspace.py`.
- Confirm the SDK exposes all requested methods.
- Confirm CLI run/task/log handlers delegate to SDK or shared SDK-backed helpers.
- Confirm no duplicate resume, event, trace, or task cleanup implementation remains in CLI.
- Confirm tests cover both SDK and CLI surfaces.
- Confirm all tests pass.
- Confirm package/import smoke still works for `botpipe` and `botpipe-v3-surface`.
