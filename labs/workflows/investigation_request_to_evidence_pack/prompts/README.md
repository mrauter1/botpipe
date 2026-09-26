# Prompt map

- `frame_producer.md` defines the evidence question, boundary, and intake plan.
- `evidence_producer.md` builds a provenance-aware evidence pack and typed summary.
- `evidence_reviewer.md` independently gates traceability, contradictions, gaps, and downstream readiness.

The runtime injects inputs, prior immutable artifacts, output destinations, and schemas. The reviewer is retained because evidence integrity is the workflow's material decision gate.

Declared paths arrive as `evidence_intake` records and immutable read handles. Prompts preserve unavailable reasons and identify additional live discoveries separately.
An `accepted` producer result requires every declared artifact. If a missing prerequisite makes responsible work impossible, `question` or `blocked` may pause without creating all outputs; never manufacture placeholder evidence merely to satisfy destinations.
