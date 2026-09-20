# Produce one bounded CandidateSet

Treat `workflow_optimization_evidence.json` as immutable fact and `baseline_surface_manifest.json` as the exact editable boundary. Propose at most `max_candidates` total candidates across enabled kinds. Cite only captured observation IDs and use repository-relative target paths inside the boundary. Effects are hypotheses, never measured improvement.

Write `workflow_optimization_candidates.json` with schema `botpipe.workflow_optimization.candidate_set/v2`. Construct a draft without either hash ID, call `finalize_candidate_set_payload(draft)` from `botpipe_optimizer.recommendations`, then serialize with `model_dump(mode="json", by_alias=True)`. Publication rejects rather than repairs output. The complete one-candidate draft shape is:

```json
{"schema":"botpipe.workflow_optimization.candidate_set/v2","selected_workflow":"<exact selected workflow>","evidence_snapshot_id":"<copy>","baseline_surface_manifest_id":"<copy>","candidates":[{"kind":"producer_prompt","title":"<title>","targets":["<repo-relative path>"],"cited_observation_ids":["<copied observation_id>"],"proposed_change":"<change>","expected_effect":"<hypothesis>","risks":["<risk>"],"validation_plan":{"description":"<plan>","checks":["<check>"],"falsification":"<failure condition>"},"payload":{"prompt_paths":["<path>"],"replacement_strategy":"<strategy>"}}],"next_action":"implement_candidate","no_candidate_reason":null}
```

Kind payloads are: `producer_prompt` → `prompt_paths`, `replacement_strategy`; `verifier_rubric` → `rubric_paths`, `acceptance_change`; `tokens` → `target_paths`, `compression_change`, `semantic_invariants`; `workflow` → `target_paths`, `workflow_change`; `evaluation_case` → `suite_target`, `case_descriptions`. All listed values except `suite_target`/change strings are arrays of non-empty strings. `CandidateSet.model_json_schema()` is authoritative. A valid empty set uses `candidates: []`, `collect_evidence` or `no_change`, and a non-empty `no_candidate_reason`.

You may also write `workflow_optimization_supporting.md` when useful. It is optional, preserved byte-for-byte, and shares the total output-byte cap.

Do not edit evidence, manifests, checkpoints, counters, or source files.
