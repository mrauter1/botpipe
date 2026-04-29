# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: implement
- Phase ID: hook-state-session-and-topology-metadata
- Phase Directory Key: hook-state-session-and-topology-metadata
- Phase Title: Hook state session and topology metadata
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` [core/engine.py:_finalize_step_result]: Route hooks do not refresh resolved artifact bindings between `on_route` and route-level `on_taken`. `finalized_artifacts` is computed once before the first hook, then passed unchanged into both hook executions, and only re-resolved afterward. If `on_route` mutates workflow or step state that changes a state-derived artifact path, `on_taken` still sees stale `ctx.artifacts` and can heal or write the old location. Final required-write validation then re-resolves against the new path and fails with the artifact missing or invalid. Minimal fix: centralize the route-hook lifecycle in `_finalize_step_result` so artifacts are re-resolved and rebound on the context after each successful route hook before the next hook runs.
