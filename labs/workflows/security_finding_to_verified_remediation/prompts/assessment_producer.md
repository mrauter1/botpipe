# Assess the security finding

Adopt the validated investigation pack, then determine what is actually exposed and what remediation must achieve.

The investigation pack and `evidence_intake` share one immutable capture of declared sources. Treat later live discovery as additional time-bound evidence, not as a replacement for an unavailable or older declared source.

- `security_assessment` separates confirmed behavior, credible exploit paths, uncertain claims, affected assets, preconditions, impact, existing controls, and evidence gaps.
- `threat_scenario` describes attacker capability, entry point, trust boundaries, attack sequence, observable signals, and plausible variants without adding unsupported exploit detail.
- `remediation_acceptance_criteria` defines the security property to restore, regression coverage, rollout controls, closure evidence, and residual-risk approval needs.
- Return exploitability as `confirmed`, `credible`, or `uncertain` and identify a preferred remediation option only when evidence supports one.

Accept when the assessment is proportionate to evidence and safe enough to plan against. Rework local reasoning; replan when the adopted evidence pack or affected boundary must change. Never downgrade missing evidence into safety or claim exploitability solely from severity labels.
