# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: implement
- Phase ID: compiler-resume-schema-docs
- Phase Directory Key: compiler-resume-schema-docs
- Phase Title: Compiler Resume Schema And Docs
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [`autoloop/runtime/runner.py:_load_saved_run_topology_payload`](autoloop/runtime/runner.py): the `topology.json` path validates and migrates schema ids, but the fallback path that reads `run.json["topology"]` returns any mapping without calling `validate_persisted_schema(...)`. That contradicts the phase requirement that persisted readers validate schemas consistently and keep legacy compatibility behind explicit migration-or-fail hooks. Concrete failure: a resumed run without `topology.json` but with a stale or unsupported embedded topology payload will silently bypass schema gating and still drive resume mismatch logic. Minimal fix: centralize topology fallback loading through one helper that validates the embedded topology mapping with the same `WORKFLOW_TOPOLOGY_SCHEMA` + explicit legacy migrator used for `topology.json`.
- `IMP-002` `blocking` [`docs/authoring.md`](docs/authoring.md), [`docs/workflows/security_finding_to_verified_remediation.md`](docs/workflows/security_finding_to_verified_remediation.md), [`docs/workflows/incident_to_hardening_program.md`](docs/workflows/incident_to_hardening_program.md), [`docs/workflows/investigation_request_to_evidence_pack.md`](docs/workflows/investigation_request_to_evidence_pack.md), [`docs/workflows/release_candidate_to_go_no_go.md`](docs/workflows/release_candidate_to_go_no_go.md), [`docs/workflows/workflow_idea_to_workflow_package.md`](docs/workflows/workflow_idea_to_workflow_package.md): the phase objective explicitly required public docs/examples to move to the final `autoloop` public surface and vocabulary, but `docs/authoring.md` still presents `autoloop.simple` as the active authoring surface and multiple public workflow docs still use the removed `system step` term. Concrete failure: authors following the current docs are instructed toward the wrong import surface and legacy terminology that the request said should be removed from public documentation. Minimal fix: update public authoring examples to import from `autoloop`, and scrub remaining user-facing `system step` wording to `python_step` in the maintained workflow docs/examples covered by this phase.

- Cycle 2 verification: `IMP-001` and `IMP-002` are resolved in the current diff. No new findings.
