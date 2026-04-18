# Test Strategy

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: test
- Phase ID: stdlib-and-optional-extensions
- Phase Directory Key: stdlib-and-optional-extensions
- Phase Title: Add Tiny `stdlib` And Optional `extensions`
- Scope: phase-local producer artifact

## Coverage Map

- `stdlib` authoring helpers:
  - `PromptBundle`, `PromptPair`, and `pair_step(...)` compile to plain workflow prompt/step objects.
  - `global_routes(...)`, `merge_transitions(...)`, `pause_on_outcome_tags(...)`, and `event_on_outcome_tags(...)` preserve explicit routing semantics.
  - `SequenceCursor` advances and resets without hidden mutable state.
- Session-path opt-in:
  - `SessionPaths(...)` extraction returns only the declared strategy and rejects duplicate declarations.
- Tracing opt-in:
  - `Tracing(...)` writes a run-relative sidecar JSONL trace when declared.
  - Workflows without `Tracing(...)` still produce generic `events.jsonl` and do not create trace sidecars.
- Git opt-in and repo mechanics:
  - Raw git inspection stays separate from task/workspace filtering.
  - Task-scoped commit selection uses filtered pathspecs without rewriting the raw delta.
  - Empty selected scope does not commit unrelated staged changes.
  - Empty selected scope may still produce an explicit empty commit when `allow_empty=True` and nothing is staged.
  - `GitChange.status` preserves raw two-column porcelain `XY` semantics for staged vs unstaged policy decisions.
  - Workflows without `GitTracking(...)` do not auto-commit just because they run inside a git repository.

## Preserved Invariants

- `stdlib` stays pure authoring sugar and does not import `runtime` or `workflows`.
- Optional extensions remain invisible unless declared through `Workflow.extensions`.
- Tracing never replaces generic `events.jsonl`.
- Git policy remains workflow-owned while generic repo mechanics stay in the extension layer.

## Edge Cases And Failure Paths

- Duplicate `SessionPaths(...)` declarations fail fast.
- Empty git tracking scope with unrelated staged changes no-ops rather than committing out-of-scope work.
- Empty git tracking scope with `allow_empty=True` still supports explicit marker commits.
- Staged-only (`M `) and unstaged-only (` M`) changes remain distinguishable to policy code.

## Reliability Notes

- All git tests use temporary repositories with local user config and no network access.
- Runtime tests use `ScriptedLLMProvider` and on-disk temp workflows/prompts for deterministic execution.
- Assertions target filesystem artifacts and git history directly rather than timing-sensitive side effects.

## Known Gaps

- The suite does not currently cover git porcelain rename/path quoting edge cases because this phase only changed empty-scope and raw-status preservation semantics.
