# Prompt contract

Each phase has one producer prompt. The producer writes the declared artifacts and returns the phase-specific typed domain result used by Python control flow. The runtime appends the input payload, artifact destinations, and JSON schema.

Evidence-quality, security, release, and other phases where independent judgment changes the result also have a reviewer prompt. A reviewer reads immutable artifacts, returns only its acceptance or rework decision and findings, and does not reconstruct the producer's domain facts.

`accepted` advances. `needs_rework` repeats the phase with feedback and prior snapshots. `needs_replan` returns to an explicit Python loop. `question` and `blocked` collect a human prerequisite; `failed` stops the workflow.
