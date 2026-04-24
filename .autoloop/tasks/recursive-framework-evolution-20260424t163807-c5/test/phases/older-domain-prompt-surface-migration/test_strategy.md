# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c5
- Pair: test
- Phase ID: older-domain-prompt-surface-migration
- Phase Directory Key: older-domain-prompt-surface-migration
- Phase Title: Migrate Older Domain Prompt Families
- Scope: phase-local producer artifact

## Behaviors Covered

- `release_candidate_to_go_no_go` prompt README exposes the shared README boundary, step surface, route surface, verifier payloads, and route reminders.
- `investigation_request_to_evidence_pack` prompt README exposes the same shared README contract sections.
- `security_finding_to_verified_remediation` prompt README exposes the shared contract sections and keeps `compose_evidence_pack` explicit as a system step with no prompt files.
- `incident_to_hardening_program` prompt README exposes the shared contract sections.
- All 26 older-domain prompt bodies keep the compact contract markers:
  - `Step Contract`
  - `Artifact Contract`
  - `Output Requirements`
  - `Routes`
  - `Forbidden`
- All 26 older-domain prompt bodies reject the legacy `Read these artifacts` / `Write these artifacts` scaffold.
- The older-domain README set is included in `tests/test_architecture_baseline_docs.py` so shared README table/route/payload coverage applies repo-wide.

## Preserved Invariants Checked

- Prompt file paths remain the expected package-local markdown files for each touched workflow family.
- Artifact names referenced in prompt assertions remain the existing workflow artifact names.
- Route names referenced in prompt assertions remain the existing workflow route names.
- The migration stays prompt-local; runtime workflow compilation and behavior tests in the same suites remain untouched and still run.

## Edge Cases

- Security-family README covers the composition edge case where one workflow step is a system composition step rather than a prompt pair.
- Prompt inventory tests fail if a package silently gains or loses a prompt markdown file after the migration.

## Failure Paths

- README tests fail if a touched package drops any required shared README section or route/payload table marker.
- Prompt-body tests fail if a touched prompt drops a required compact-contract heading, loses a required step-local marker, or reintroduces the legacy scaffold.
- Baseline docs tests fail if the older-domain README files drift away from the shared README contract enforced across the newer workflow family.

## Validation Run

- Command:
  - `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_incident_to_hardening_program.py tests/test_architecture_baseline_docs.py`
- Result:
  - `102 passed`

## Known Gaps

- No full-text snapshotting of prompt prose; coverage intentionally pins contract markers, prompt inventory, artifact/route markers, and README tables instead of brittle exact wording.
- No CLI/runtime/provider behavior testing added here because those surfaces are explicitly out of scope for this phase.
