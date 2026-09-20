# Produce one bounded CandidateSet

Treat `workflow_optimization_evidence.json` as immutable fact and `baseline_surface_manifest.json` as the exact editable boundary. Propose at most `max_candidates` total candidates across enabled kinds. Cite only captured observation IDs and use repository-relative target paths inside the boundary. Effects are hypotheses, never measured improvement.

Write only `workflow_optimization_candidates.json` with schema `botpipe.workflow_optimization.candidate_set/v2`. A valid empty set uses `collect_evidence` or `no_change` and explains why. Construct a draft, call `finalize_candidate_set_payload(draft)` from `botpipe_optimizer.recommendations`, then serialize with `model_dump(mode="json", by_alias=True)`. Publication rejects rather than repairs output.

You may also write `workflow_optimization_supporting.md` when useful. It is optional, preserved byte-for-byte, and shares the total output-byte cap.

Do not edit evidence, manifests, checkpoints, counters, or source files.
