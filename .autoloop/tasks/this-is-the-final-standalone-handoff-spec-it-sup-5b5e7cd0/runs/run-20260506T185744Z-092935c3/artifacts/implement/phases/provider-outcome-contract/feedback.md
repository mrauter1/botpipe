# Implement ↔ Code Reviewer Feedback

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: implement
- Phase ID: provider-outcome-contract
- Phase Directory Key: provider-outcome-contract
- Phase Title: Canonical Provider Outcomes
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [autoloop/core/providers/parsing.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/providers/parsing.py): `parse_outcome_json()` still seeds `Outcome.reason` from the legacy top-level `reason` field even when a canonical `outcome.route_fields` object is present. If a provider returns `{"outcome":{"tag":"question","payload":{},"route_fields":{"questions":["Q"],"reason":null}},"reason":"legacy"}`, the parsed `Outcome.reason` remains `"legacy"` because `Outcome.__post_init__` only overwrites it when `route_fields.reason` is a string. That contradicts the phase contract and tests’ intended migration rule that canonical `route_fields` must win whenever both canonical and legacy fields are present. Fix by centralizing canonical-envelope normalization in `parse_outcome_json()` (or one shared helper) so top-level `question` / `reason` are ignored once `outcome` exists and compatibility projections are derived strictly from canonical `route_fields`; add a regression test for canonical `reason: null` plus legacy top-level `reason`.
