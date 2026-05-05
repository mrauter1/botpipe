# Implement ↔ Code Reviewer Feedback

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: core-selector-semantics
- Phase Directory Key: core-selector-semantics
- Phase Title: Extend generic worklist selectors
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [autoloop/stdlib/worklists.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/stdlib/worklists.py:237): `ProgressJsonCollectionSource.save()` calls `_read_existing_payload()`, and that helper replaces the on-disk payload with `validated.model_dump(mode="json")` whenever a Pydantic model is configured. That violates the requested save contract to "update only `status` fields" and "do not mutate non-status payload fields": any defaulted or coerced model field gets written back even when the caller only advances status. Concrete failure: if a workflow item model adds `acceptance_criteria: list[str] = []` and the artifact omits that field, saving `completed` will silently add `acceptance_criteria: []` to the artifact. Minimal fix: split load/save handling so save validates against the model without replacing the raw payload, then mutate only `status` in the original item objects before the final validation pass.
- `IMP-002` `blocking` [autoloop/stdlib/worklists.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/stdlib/worklists.py:342): progress worklist items are created without `dir_key`, unlike the existing generic item builders in [autoloop/core/worklists.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/worklists.py:825). That makes `progress_artifact_worklist(...)` behave differently from other worklists under scoped runtime features that depend on stable per-item directories. Concrete failure: a workflow that writes `Artifact.md("{workflow_folder}/reports/{item.dir_key}.md")` under a progress worklist gets `None` instead of the canonical fallback key, and any continuity/path logic expecting the default `dir_key` contract will drift. Minimal fix: assign `dir_key` from payload `dir_key` when present, otherwise derive the same default key as the core worklist sources, ideally by centralizing the mapping-to-`WorkItem` construction path instead of duplicating it.

Cycle 2 review note: `IMP-001` and `IMP-002` no longer reproduce after the save-path split and progress-item `dir_key` backfill. Fresh verifier reruns passed for the focused selector/progress suites and the direct artifact-backed engine contract subset.
