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

For an authored workflow, use `FakeProvider` to exercise outcomes rather than a
single exact model path. Cover the useful success path and material rejection,
bounded exhaustion, human pause/resume, or uncertain-effect paths. Assert typed
domain results, artifact contents, routing, budgets, permissions, and absence of
new provider calls on replay. Avoid assertions on exact prompt prose, private
reasoning, incidental call counts, or one tool sequence unless that detail is
itself the public contract. A schema-valid fake response tests orchestration and
shape; it does not establish the semantic quality of a live provider result.

Test the connections that make evidence-based decisions possible. For example,
a rejected draft's reason and captured bytes must remain accessible to the next
investigator or repair step, even after a replacement exists. Exercise a
correctable reference error followed by a valid answer, bounded exhaustion, and
an integrity violation that must not be retried as a model mistake.

When a workflow claims measured improvement, test that both real entry points
execute on the declared cases and that captured outputs reach the evaluation
step. Include a worse or unchanged candidate, not only a success fixture. Check
fixed inputs/criteria, judge isolation where promised, comparable limits,
unavailable evidence, and replay without repeated completed trials or judgments.
Distinguish a workflow failure under a valid case from a broken evaluation.
Controlled fixtures test this contract; they do not prove a live judge's accuracy.

Keep bundled authoring guides synchronized with their canonical docs using the
existing parity check. Test executable examples and installed-package dependency
boundaries, not the presence of preferred sentences in prompts. Disabling labs
discovery is not proof that a shipped workflow can import without labs.

Lab scenarios are individual parametrized tests. Discovery must match the
scenario inventory so a new lab cannot silently miss behavioral coverage. Labs
return typed producer values and use reviewers only at material decision gates.
Reviews that claim to run checks use `run`; inspection-only reviews use `query`.
For workflows using the shared artifact-only phase helper, also verify that
producer attempts use distinct run-owned workspaces, destinations cannot escape
those workspaces, source inspection does not write to the source workspace,
control outcomes need no complete artifact set, and acceptance does.

Use CI's slowest-test timings to guide further changes. Do not disable `fsync`,
weaken ledger durability, or drop a platform to make the suite appear faster.
