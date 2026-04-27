# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: implement
- Phase ID: provider-and-engine-contract
- Phase Directory Key: provider-and-engine-contract
- Phase Title: Provider and engine contract
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [core/providers/parsing.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/providers/parsing.py:18): `parse_outcome_json()` still treats `reason` as optional, so provider responses such as `{"tag":"done"}` or `{"tag":"accepted","payload":{}}` are accepted and executed for non-`blocked`/`failed` routes. That contradicts the new rendered contract, which now instructs providers to return the exact `{tag, reason, payload}` control object, and it leaves runtime validation weaker than the prompt surface in AC-1. Minimal fix: centralize the required-field rule in `parse_outcome_json()` so control responses must include a string `reason` for every route, then cover the omission case in provider/rendering contract tests so the renderer, parser, and engine stay aligned.

- Re-review `cycle-2`: `IMP-001` is resolved in the current diff. `parse_outcome_json()` now requires a non-empty top-level `reason`, and the focused provider-boundary tests cover the omission case plus the updated rendered-provider fixtures. No new phase-local findings.
