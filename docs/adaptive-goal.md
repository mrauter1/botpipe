# Adaptive goal runtime

Botpipe's normal SOP model keeps global procedure deterministic while the
provider is autonomous inside a coherent step. `adaptive_goal` adds a second
authoring pattern for environments where the destination can be specified much
more reliably than the sequence of work required to reach it.

## Two graphs

The **static control graph** is small and framework-owned:

```text
ORCHESTRATE → VALIDATE → DISPATCH → RECONCILE → ORCHESTRATE
                                      │
                                      └→ FINAL AUDIT → FINISH / REOPEN
```

The **dynamic action graph** is the historical sequence of registered
capabilities, verifiers, and bounded ad-hoc operations selected at runtime. It is
data/evidence, not dynamically imported Python.

## Verification is not synonymous with scoring

The runtime deliberately distinguishes three verification modes:

- **judgment**: a designated verifier LLM evaluates an operator-authored
  descriptive rubric and returns a qualitative verdict, detailed reasoning,
  rubric findings, evidence and recommended remediation;
- **deterministic**: a verifier supplies objective observations and trusted
  runtime code applies genuinely mechanical hard rules;
- **hybrid**: a qualitative judgment is required together with mechanical hard
  checks.

For judgment criteria, an optional `rating` (1-5) and confidence label may be
included for diagnosis, comparison or telemetry. They do not determine PASS.
The substantive verifier reasoning is more authoritative than an invented scalar.

## Trust boundaries

Trusted operator-authored code/data:

- Botpipe runtime;
- `adaptive_goal`;
- capability workflows;
- designated verifier workflows;
- capability registry;
- mission definition and rubrics.

Provider-generated behavior:

- action selection;
- capability implementation work inside provider sandboxes;
- ad-hoc workspace operations;
- qualitative verifier judgments and findings;
- objective observations emitted by verifier workflows.

Runtime-owned governance:

- action legality;
- designated-verifier authority;
- rubric coverage/coherence checks;
- deterministic hard-rule evaluation when applicable;
- PASS/FAIL/BLOCKED/STALE state transitions;
- freshness invalidation;
- max-action/no-progress limits;
- terminal-unsatisfied handling;
- final terminal state.

The parent does **not** try to independently calculate subjective quality from a
verifier-produced score. Instead, it validates that the authorized verifier
actually evaluated the complete authored rubric and that the output is internally
coherent. For example, an overall `satisfied` verdict cannot coexist with an
unsatisfied rubric item marked `importance="gate"`.

## Verifier result shape

For a judgment criterion, the durable receipt contains:

- overall `satisfied | not_satisfied | insufficient_evidence` verdict;
- concise summary;
- substantive reasoning;
- one finding for every rubric item;
- evidence attached to findings;
- optional 1-5 rating;
- optional low/medium/high confidence;
- recommended corrective actions.

This structure makes failure feedback directly useful to the next orchestration
turn. The orchestrator sees concrete deficiencies rather than merely `78/100`.

## Freshness

A verifier receipt may observe local paths such as `site/**`. On PASS, the parent
hashes those files and records the digest. After every action, current PASS
criteria are re-fingerprinted. A mismatch changes PASS → STALE before completion
can be considered. This mechanism does not depend on optional Git tracking.

For external state, define `ttl_seconds` so an old receipt automatically becomes
stale.

## Security

Do not use dynamic generation/import of Botpipe Python as the ad-hoc mechanism.
Botpipe Python handlers are trusted local code and are not provider-sandboxed.
The pre-authored `ad_hoc_executor` keeps arbitrary work inside the provider
sandbox.

Capabilities with external side effects are rejected unless explicitly
preapproved in `AdaptiveGoalInput.preapproved_capabilities`. The capability's own
Botpipe policy remains responsible for constraining its provider execution.

## Completion semantics

A judgment criterion can become current PASS only when:

1. the designated verifier produced a `satisfied` judgment;
2. every authored rubric item has exactly one finding;
3. every `gate` rubric item is explicitly satisfied;
4. the judgment is structurally coherent and evidence-bearing;
5. its filesystem subject fingerprint still matches, if applicable;
6. its TTL has not expired, if applicable.

A deterministic criterion instead requires all authored hard rules to pass. A
hybrid criterion requires both the qualitative judgment conditions and the hard
rules.

All required criteria must be current PASS before global audit. The global audit
reads the reasoning/evidence—not just status labels—and may reopen existing
criteria, but cannot invent requirements or weaken the mission.
