# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: provider-turn-and-route-finalization
- Phase Directory Key: provider-turn-and-route-finalization
- Phase Title: Provider Turn Adapters
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — [botlane/core/engine_collaborators.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/engine_collaborators.py:170) and [botlane/core/engine_collaborators.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/engine_collaborators.py:184): `_prompt_step_plan_for_execution()` and `_pair_step_plan_for_execution()` catch every exception from `step_plan_from_compiled_step(...)` and silently return `None`, which drops execution back to the legacy compiled-step path with no signal. That means a real adapter bug or future regression in route/IO conversion will quietly disable the new `ProviderTurnPlan` bridge while the runtime still appears to work, so AC-1 is no longer trustworthy and the new tests will keep passing on the happy path. Narrow the fallback to explicit, known parity gaps only, or surface unexpected adapter failures; centralize that allowlisted fallback policy in one helper instead of blanket `except Exception`.
