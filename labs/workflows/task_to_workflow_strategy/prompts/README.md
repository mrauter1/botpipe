# Prompt map

- `frame_producer.md` defines the decision boundary and route criteria.
- `select_producer.md` makes the evidence-backed route choice from the child candidate set.
- `package_producer.md` publishes the selected route and an executable handoff.

The runtime supplies inputs, immutable reads, artifact paths, and the typed result schema. Local defects use `needs_rework`; a changed upstream decision uses `needs_replan`; missing prerequisites use `question` or `blocked`.
An `accepted` producer result requires every declared artifact. If a missing prerequisite makes responsible work impossible, `question` or `blocked` may pause without creating all outputs; never manufacture placeholder evidence merely to satisfy destinations.
