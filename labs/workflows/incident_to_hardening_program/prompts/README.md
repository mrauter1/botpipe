# Prompt map

- `frame_producer.md` establishes the incident boundary and response objectives.
- `evidence_producer.md` builds the timeline, impact view, and gap register; `evidence_reviewer.md` gates evidentiary integrity.
- `analysis_producer.md` ranks falsifiable hypotheses and selects a safe posture; `analysis_reviewer.md` independently challenges causality and mitigation safety.
- `program_producer.md` packages accepted analysis into owned, testable hardening work.

Final packaging has no separate reviewer because it must preserve already-reviewed evidence and analysis; deterministic publication validation checks its cross-artifact contract.

Declared incident sources are frozen before framing. Later source discovery remains allowed but must be identified as live, time-bound evidence rather than substituted for an unavailable declaration.
An `accepted` producer result requires every declared artifact. If a missing prerequisite makes responsible work impossible, `question` or `blocked` may pause without creating all outputs; never manufacture placeholder evidence merely to satisfy destinations.
