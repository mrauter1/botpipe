# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c5
- Pair: implement
- Phase ID: older-domain-prompt-surface-migration
- Phase Directory Key: older-domain-prompt-surface-migration
- Phase Title: Migrate Older Domain Prompt Families
- Scope: phase-local producer artifact

## Audit

- Cycle mode: `authoring-surface`
- Most relevant existing workflows/helpers checked:
  - `workflows/task_to_workflow_strategy/prompts/` as the compact prompt-contract reference
  - `workflows/release_candidate_to_go_no_go/prompts/`
  - `workflows/security_finding_to_verified_remediation/prompts/`
- Repeated patterns found:
  - older domain prompt bodies still used legacy `Read these artifacts` / `Write these artifacts` scaffolding
  - older domain README files lacked the shared README contract sections
  - older domain runtime suites did not pin compact prompt markers explicitly
- Simplification opportunity: migrate the four older domain prompt families onto the shared README-plus-step-contract shape already used by the newer workflow family
- New workflow necessity: none
- Change decision: change and standardize prompt markdown plus prompt-facing tests only; no workflow/runtime/provider changes

## Files Changed

- Prompt READMEs and prompt bodies under:
  - `workflows/release_candidate_to_go_no_go/prompts/`
  - `workflows/investigation_request_to_evidence_pack/prompts/`
  - `workflows/security_finding_to_verified_remediation/prompts/`
  - `workflows/incident_to_hardening_program/prompts/`
- Prompt-facing tests:
  - `tests/runtime/test_release_candidate_to_go_no_go.py`
  - `tests/runtime/test_investigation_request_to_evidence_pack.py`
  - `tests/runtime/test_security_finding_to_verified_remediation.py`
  - `tests/runtime/test_incident_to_hardening_program.py`
  - `tests/test_architecture_baseline_docs.py`
- Recursive memory:
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`
- Shared decision ledger:
  - `.autoloop/tasks/recursive-framework-evolution-20260424t163807-c5/decisions.txt`

## Symbols Touched

- Prompt-facing symbols only:
  - `COMMON_PROMPT_CONTRACT_MARKERS`
  - `LEGACY_PROMPT_SCAFFOLDING_MARKERS`
  - `_assert_compact_prompt_contract(...)`
  - prompt README contract sections and compact prompt headings

## Checklist Mapping

- Milestone 1: completed
  - rewrote the four older-domain `prompts/README.md` files to the shared contract shape
  - rewrote all 26 older-domain prompt bodies to the compact section contract
  - added prompt-shape assertions to the four targeted runtime suites
- Milestone 2: completed
  - extended `tests/test_architecture_baseline_docs.py` to include the older-domain README set
  - updated recursive-memory files with no-doctrine-change closeout notes
  - ran the targeted prompt-facing proof

## Preserved Invariants

- Prompt file paths unchanged
- Step names unchanged
- Artifact names unchanged
- Route names unchanged
- Expected output schemas unchanged
- Workflow topology unchanged
- CLI/runtime/provider boundaries unchanged
- `ctx.invoke_workflow(...)` behavior unchanged

## Intended Behavior Changes

- Provider-facing prompt markdown now uses the compact README boundary plus `Step Contract` / `Artifact Contract` / `Output Requirements` / `Evidence` / `Routes` / `Forbidden` sections across the four older domain families.
- Runtime tests now fail if those prompt families regress to the older scaffold or lose the shared README contract sections.

## Known Non-Changes

- No CLI changes
- No runtime changes
- No provider adapter changes
- No workflow Python logic changes
- No new helper seam, serializer, workflow, or `workflow.toml` field

## Expected Side Effects

- Prompt authoring is shorter and more uniform across the full workflow portfolio.
- The composition-aware security family now documents its system-step boundary explicitly in the README without adding prompt files or runtime behavior.

## Validation Performed

- `rg -n "Read these artifacts|Write these artifacts" workflows/release_candidate_to_go_no_go/prompts workflows/investigation_request_to_evidence_pack/prompts workflows/security_finding_to_verified_remediation/prompts workflows/incident_to_hardening_program/prompts tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_incident_to_hardening_program.py tests/test_architecture_baseline_docs.py`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_incident_to_hardening_program.py tests/test_architecture_baseline_docs.py`
- Result: `98 passed`

## Deduplication / Centralization Decisions

- Kept family-wide prompt reminders in each package `prompts/README.md` and moved prompt bodies to step-local contract sections instead of introducing any runtime prompt abstraction.
- Reused the existing compact prompt test pattern from the newer workflow family rather than adding a new prompt-validation helper module.

## Boilerplate / Clarity Budget

- Files added: `0`
- Files deleted: `0`
- Net line change across the targeted diff: `+1180` (`1770` added, `590` deleted)
- Why the added surface is acceptable: most of the net increase comes from prompt-shape assertions in four runtime suites plus required recursive-memory and phase notes; production workflow/runtime code stayed unchanged, and the prompt-family surface now converges on one explicit contract instead of two competing prompt idioms
- Repeated validation idioms removed: `0` in Python code this phase
- Repeated prompt sections removed or shortened:
  - removed legacy `Read these artifacts` scaffolding from all 26 older-domain prompt bodies
  - removed legacy `Write these artifacts` scaffolding from the 13 producer prompts in that family
  - replaced ad hoc README summaries in all 4 touched packages with one shared README contract shape
- Workflows changed to use shared helpers: `0`
- New helper functions introduced: test-local `_assert_compact_prompt_contract(...)` copies in the four touched runtime suites only; no production helper seam added
- Old workflow-local validation blocks replaced: `0`
- Core flow readability before/after:
  - before: mixed legacy prose scaffolding in the older domain family forced authors to remember a second prompt idiom
  - after: all four families now expose the same step-local headings, artifact tables, README boundary, and prompt-facing regression checks as the newer workflow family
