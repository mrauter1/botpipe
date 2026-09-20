# Durable phase prompts

Each phase has a producer and verifier prompt. Python workflow code declares their order, immutable reads, and exact artifact writes. The runtime appends the input payload, artifact destinations, and typed JSON schema.

The producer writes every declared artifact and returns a `LabPhaseDraft` with a summary, evidence notes, and any stable candidate identifiers. The verifier reads immutable artifact snapshots and returns `LabPhaseOutcome`:

- `accepted` when the phase-specific success condition is met;
- `needs_rework` when the same phase can repair its artifacts;
- `blocked` when a required prerequisite is absent.

Names such as `release_framed` or `strategy_selected` in older domain guidance describe the positive success condition. They are descriptive success conditions, not runtime control values. The verifier cites only artifacts supplied by the runtime. Provider output and artifact validation failures may receive bounded repair feedback through a new journaled turn.
