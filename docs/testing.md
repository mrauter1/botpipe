# Testing

Install the test tools with `python -m pip install -e '.[test]'`.

Run the deterministic suite as CI does:

```sh
python -m pytest -q -n 2 --dist worksteal --durations=30 -o faulthandler_timeout=60
```

For debugging, omit `-n 2 --dist worksteal` or select an individual test.
Parallelism is explicit rather than a default pytest option. Two workers bound
resource use because some tests start their own child processes. Work stealing
balances the longer workflow and recovery scenarios. Each test owns its temporary
workspace and state root; durable ledger writes and process containment stay enabled.

CI runs the full suite on Linux, macOS and Windows with Python 3.12 and 3.13.
Native Codex contracts run separately and serially on each platform. Dependency
downloads are cached; installed environments, test results and Codex binaries are
not cached. Codex contract jobs resolve the floating `@openai/codex@latest` tag
on each job; record the installed version when diagnosing a failure.

Prefer observable contracts: validated values and captured artifacts, replay
without repeated effects, refused unsafe recovery, concurrent writers with
distinct sessions, same-session serialization, per-operation reconciliation,
operation-scoped server disposal, completed-result retention when disposal
fails, process termination, and working installed packages. Exercise real
persistence and real child processes where those are the behavior under test.
Use controlled clocks for deadline arithmetic rather than short sleeps.

Lab scenarios are individual parametrized tests. Discovery must match the
scenario inventory so a new lab cannot silently miss behavioral coverage. Labs
return typed producer values and use reviewers only at material decision gates.
Reviews that claim to run checks use `run`; inspection-only reviews use `query`.

Use CI's slowest-test timings to guide further changes. Do not disable `fsync`,
weaken ledger durability, or drop a platform to make the suite appear faster.
