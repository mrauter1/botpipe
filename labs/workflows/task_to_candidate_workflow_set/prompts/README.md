# Prompt map

- `frame_producer.md` defines task-specific fit criteria.
- `analyze_producer.md` compares credible catalog candidates and determines portfolio posture.
- `package_producer.md` publishes the ranked set for strategy selection.

The runtime injects authoritative inputs, reads, destinations, and result schemas. The workflow discovers and packages candidates; it neither pads the set to a fixed size nor selects or executes the final route.
An `accepted` producer result requires every declared artifact. If a missing prerequisite makes responsible work impossible, `question` or `blocked` may pause without creating all outputs; never manufacture placeholder evidence merely to satisfy destinations.
