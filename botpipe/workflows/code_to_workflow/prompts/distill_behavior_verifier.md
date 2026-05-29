Independently verify the behavior inventory.

Inspect:
- The request and invocation contract.
- `source_manifest.json` and representative source files.
- `trace_corpus.json`.
- `behavior_inventory.json`, `behavior_inventory.md`, and `trace_pattern_notes.md`.
- Prior `behavior_review.md`, if present.

Accept with `behavior_distilled` only if:
- `behavior_inventory.json` has the required schema shape and a non-empty `behaviors` list.
- Behavior ids are stable and unique.
- Required behaviors are externally observable and evidence-backed.
- The inventory covers entrypoints, user-visible operations, data/state effects, and important error modes.
- Trace notes accurately use or dismiss the available trace evidence.

Reject with `needs_rework` if coverage is vague, evidence is missing, source areas were skipped without reason, or behavior is confused with private implementation details.

Always write `behavior_review.md` with the decision. Include exact required rework if rejected.
