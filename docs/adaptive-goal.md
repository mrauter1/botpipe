# Adaptive goal runtime

Botpipe's normal SOP model keeps global procedure deterministic while the
provider is autonomous inside a coherent step. `adaptive_goal` adds a second
authoring pattern for environments where the destination can be specified much
more reliably than the sequence of work required to reach it.

## Two graphs

The **static control graph** is small and framework-owned:

```text
ORCHESTRATE → DISPATCH → RECONCILE → ORCHESTRATE
                              │
                              └→ FINAL AUDIT → FINISH / REOPEN
```

The **dynamic action graph** is the historical sequence of registered
capabilities, verifiers, and bounded ad-hoc operations selected at runtime. It is
data/evidence, not dynamically imported Python.

## Trust boundaries

Trusted operator-authored code:

- Botpipe runtime;
- `adaptive_goal`;
- capability workflows;
- verifier workflows;
- capability registry;
- mission definition.

Untrusted/provider-generated behavior:

- action selection;
- capability implementation work inside provider sandboxes;
- ad-hoc workspace operations;
- verifier metric observations.

Runtime-owned decisions:

- action legality;
- preapproval enforcement;
- metric acceptance rules;
- PASS/FAIL/STALE transitions;
- freshness invalidation;
- max-action/no-progress limits;
- terminal-unsatisfied handling;
- final terminal state.

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

A criterion is current PASS only when:

1. its designated verifier produced valid observations;
2. the parent runtime applied every deterministic acceptance rule successfully;
3. its filesystem subject fingerprint still matches, if applicable;
4. its TTL has not expired, if applicable.

All required criteria must be current PASS before global audit. The global audit
may reopen existing criteria but cannot invent requirements or change thresholds.
