# Standalone fix plan — `workflow_run_traces_to_optimization_candidates`

## Scope

Fix the current `workflow_run_traces_to_optimization_candidates` implementation so that it correctly follows the intended optimization architecture.

This plan assumes the current implementation already includes the runtime evidence layer, optimizer workflow package, optimizer docs, contracts, prompts, and test suite. The uploaded implementation tree includes the new optimizer workflow package and runtime evidence files, while the uploaded test tree includes optimizer, runtime tracing/git/static-graph, refinement, architecture, and optimization-helper tests.  

This patch must stay focused on workflow semantics, prompts, docs, and tests. Do **not** modify runtime git tracking, runtime tracing, provider execution, engine execution semantics, or `commit_after_run` behavior.

---

## 1. Required changes

Implement exactly these fixes:

```text
1. Stop deterministically rewriting accepted LLM-authored artifacts.
2. Make deterministic failure-scenario output a separate seed artifact.
3. Implement optimization_depth as prompt/publication behavior.
4. Treat max_candidates_per_pass as soft prompt guidance only.
5. Update tests to cover the corrected behavior.
6. Update docs and report.md.
```

Do **not** implement:

```text
- commit_after_run changes
- runtime git-tracking changes
- runtime tracing changes
- target workflow reruns
- ablation execution
- automatic prompt/source mutation
- deterministic candidate-count enforcement
- new optimization runtime behavior
```

---

## 2. Core invariant

The corrected optimizer must follow this rule:

```text
Deterministic code prepares evidence and seeds.
LLM producers author optimization artifacts.
Verifiers accept or reject those artifacts.
Workflow handlers validate accepted artifacts and update state.
Workflow handlers must not silently replace accepted LLM-authored artifacts.
```

This applies to these LLM-authored artifacts:

```text
workflow_failure_scenarios.json
producer_prompt_optimization_candidates.json
verifier_rubric_optimization_candidates.json
token_optimization_candidates.json
adversarial_case_candidates.json
workflow_level_optimization_candidates.json
```

Deterministic workflow code may still write deterministic runtime/publication artifacts:

```text
workflow_optimization_scope.json
workflow_optimization_trace_corpus.json
excluded_run_report.json
workflow_failure_scenario_seeds.json
step_trace_metrics.json
selected_workflow_source_manifest.json
workflow_optimization_scorecard.json
workflow_refinement_evidence.json
workflow_optimization_packet.md
optimization_publication_receipt.json
```

---

## 3. Files to modify

Primary files:

```text
workflows/workflow_run_traces_to_optimization_candidates/workflow.py
workflows/workflow_run_traces_to_optimization_candidates/contracts.py
workflows/workflow_run_traces_to_optimization_candidates/prompts/README.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/mine_failures_producer.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/mine_failures_verifier.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/optimize_producer_producer.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/optimize_producer_verifier.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/optimize_verifier_rubric_producer.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/optimize_verifier_rubric_verifier.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/optimize_tokens_producer.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/optimize_tokens_verifier.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/adversarial_cases_producer.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/adversarial_cases_verifier.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/workflow_level_producer.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/workflow_level_verifier.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/package_producer.md
workflows/workflow_run_traces_to_optimization_candidates/prompts/package_verifier.md
docs/workflows/workflow_run_traces_to_optimization_candidates.md
tests/runtime/test_workflow_run_traces_to_optimization_candidates.py
tests/unit/test_optimization_helpers.py
report.md
```

Modify this file only if needed to expose deterministic failure seeds cleanly:

```text
stdlib/optimization.py
```

Do not modify runtime git/tracing files for this patch.

---

## 4. Add deterministic failure-scenario seed artifact

### 4.1 Add artifact

Add a deterministic seed artifact:

```text
workflow_failure_scenario_seeds.json
```

Purpose:

```text
Deterministic helper output used as input to the LLM failure-mining pass.
This is not the final failure scenario artifact.
```

Final LLM-authored artifact remains:

```text
workflow_failure_scenarios.json
```

Required separation:

```text
workflow_failure_scenario_seeds.json = deterministic input
workflow_failure_scenarios.json = LLM-authored artifact validated by the workflow
```

### 4.2 Seed schema

Add a schema in `contracts.py`:

```json
{
  "schema": "autoloop.workflow_optimization.failure_scenario_seeds/v1",
  "selected_workflow": "<selected_workflow>",
  "seeds": [
    {
      "seed_id": "assessment-needs-rework-loop",
      "step_name": "assessment",
      "seed_kind": "producer_failed_verifier",
      "observation_ids": ["task-123/run-456:000003:assessment"],
      "summary": "Assessment repeatedly selected needs_rework after verifier rejection.",
      "suggested_failure_kind": "producer_failed_verifier"
    }
  ]
}
```

Keep this schema permissive enough for deterministic helper evolution. Required top-level fields:

```text
schema
selected_workflow
seeds
```

`seeds` must be a list. Individual seed fields may be lightly validated but should not over-constrain text.

### 4.3 Write seeds before `mine_failures`

Where deterministic failure scenarios are currently built, change the destination from:

```text
workflow_failure_scenarios.json
```

to:

```text
workflow_failure_scenario_seeds.json
```

The `mine_failures` producer prompt must read the seed artifact and author the final `workflow_failure_scenarios.json`.

---

## 5. Fix `on_mine_failures`

### 5.1 Current bug

The current `on_mine_failures` handler must not overwrite `workflow_failure_scenarios.json` after the LLM pass.

Remove any code path that writes deterministic content to:

```text
workflow_failure_scenarios.json
```

after the producer/verifier pair has completed with an accepted route.

### 5.2 Correct behavior

Implement this behavior:

```text
If route == failure_scenarios_mined:
  - read workflow_failure_scenarios.json
  - validate JSON shape
  - validate schema value
  - validate selected_workflow
  - validate failure_scenarios is a list
  - update state counts/status
  - do not rewrite the file

If route == no_failure_scenarios:
  - if workflow_failure_scenarios.json exists and is valid, leave it in place
  - if it is missing, write a minimal empty fallback artifact
  - update state counts/status

If route == needs_rework:
  - do not overwrite workflow_failure_scenarios.json
  - preserve whatever artifact the producer wrote for repair
  - route according to normal rework behavior

If route == failed:
  - do not overwrite workflow_failure_scenarios.json
  - route according to normal failure behavior
```

### 5.3 Invalid artifact behavior

Use this exact rule:

```text
If verifier route is failure_scenarios_mined but workflow_failure_scenarios.json is missing, malformed, schema-mismatched, or selected_workflow-mismatched:
  raise or return the same invalid-output-artifact failure path used elsewhere for provider-authored invalid artifacts.

If verifier route is no_failure_scenarios and workflow_failure_scenarios.json is missing:
  write a minimal valid empty artifact.

If verifier route is needs_rework:
  do not rewrite the artifact, even if malformed.
```

Do not deterministically replace invalid LLM-authored scenarios with generated scenarios.

### 5.4 Minimal empty fallback

Only for `no_failure_scenarios` when the final artifact is absent, write:

```json
{
  "schema": "autoloop.workflow_optimization.failure_scenarios/v1",
  "selected_workflow": "<selected_workflow>",
  "failure_scenarios": []
}
```

---

## 6. Audit other handlers for deterministic rewrites

In `workflow.py`, audit these handlers:

```text
on_rank_targets
on_mine_failures
on_optimize_producer
on_optimize_verifier_rubric
on_optimize_tokens
on_adversarial_cases
on_workflow_level
on_package
```

### 6.1 Candidate handlers

For these artifacts, handlers may validate and update state, but must not replace accepted provider-authored content:

```text
producer_prompt_optimization_candidates.json
verifier_rubric_optimization_candidates.json
token_optimization_candidates.json
adversarial_case_candidates.json
workflow_level_optimization_candidates.json
```

Allowed behavior:

```text
- read artifact
- validate schema and selected_workflow
- count candidates
- compute state/publication metadata
- leave artifact content unchanged
```

Forbidden behavior:

```text
- regenerating candidates deterministically after verifier acceptance
- truncating candidates deterministically
- normalizing/re-serializing the artifact just to enforce formatting
- replacing provider-authored rationale or candidate content
```

### 6.2 Not-applicable routes

For not-applicable routes, minimal empty artifacts are allowed if missing:

```text
producer_pass_not_applicable
verifier_rubric_pass_not_applicable
token_pass_not_applicable
adversarial_generation_skipped
workflow_level_pass_not_applicable
```

Examples:

```json
{
  "schema": "autoloop.workflow_optimization.producer_candidates/v1",
  "selected_workflow": "<selected_workflow>",
  "target_steps": [],
  "candidates": []
}
```

Do not replace a valid provider-authored artifact even on not-applicable routes.

### 6.3 `rank_targets`

Clarify the ownership of ranking artifacts:

```text
step_trace_metrics.json:
  deterministic artifact; may be written by workflow code.

step_optimization_priority_report.json:
  if producer-authored in current design, validate it and do not rewrite it.
  if intentionally deterministic in current implementation, document it as deterministic.
```

Do not accidentally weaken deterministic metrics/ranking seed computation.

---

## 7. Implement `optimization_depth`

### 7.1 No hidden execution

`optimization_depth` must never execute target workflows, ablations, refinement, or repo patches.

For all values:

```text
target workflow reruns: no
ablation execution: no
refinement execution: no
source mutation: no
```

### 7.2 Required scorecard fields

Add these required fields to `workflow_optimization_scorecard.json`:

```json
{
  "optimization_depth": "cheap",
  "ablation_executed": false
}
```

`optimization_depth` must equal the normalized parameter value:

```text
cheap
standard
ablation
```

`ablation_executed` must always be `false` in this workflow.

If `workflow_optimization_scorecard` currently uses a Pydantic model, make these fields required.

### 7.3 Depth semantics

Implement the behavior as prompt/publication behavior.

```text
cheap:
  - existing traces only
  - concise candidate generation
  - avoid speculative expansion

standard:
  - existing traces only
  - deeper LLM cross-checking across trace corpus, priority report, selected workflow surfaces, and existing candidate artifacts
  - lower confidence when evidence is thin
  - no reruns

ablation:
  - ablation planning mode only
  - no ablation execution
  - mark candidates that should be ablated before promotion
  - scorecard and packet must state no ablation was executed
```

### 7.4 Propagate depth in prompts

Every producer prompt should explicitly read:

```text
workflow_optimization_scope.json
```

and apply:

```text
optimization_depth
```

Update these prompts:

```text
rank_targets_producer.md
mine_failures_producer.md
optimize_producer_producer.md
optimize_verifier_rubric_producer.md
optimize_tokens_producer.md
adversarial_cases_producer.md
workflow_level_producer.md
package_producer.md
```

Add shared language to `prompts/README.md`:

```markdown
## Optimization depth

- `cheap`: Use existing traces only. Produce concise, high-leverage candidates. Avoid speculative expansion.
- `standard`: Use existing traces only. Perform deeper cross-checking across trace corpus, selected workflow surfaces, priority report, and candidate artifacts. Lower confidence when evidence is thin.
- `ablation`: Do not run ablations. Treat this as ablation-planning mode only. Mark candidates that should be ablated before promotion and include ablation-oriented rationale where useful.
```

### 7.5 Packet section

Ensure `workflow_optimization_packet.md` includes:

```markdown
## Optimization Depth

Requested depth: `<cheap|standard|ablation>`

Target workflow reruns executed: no  
Ablations executed: no  
Refinement executed: no
```

For `ablation` depth, include:

```markdown
Ablation mode produced ablation recommendations only. It did not execute ablation runs.
```

This section may be appended deterministically by the package handler if the LLM-authored packet omits it. `workflow_optimization_packet.md` is a publication artifact, so deterministic completion is allowed.

### 7.6 Candidate ablation flags

Do not add a separate ablation workflow.

Do ensure candidate schemas support:

```text
requires_ablation
```

for:

```text
producer candidates
verifier/rubric candidates
token candidates
workflow-level candidates
```

For adversarial cases, continue using:

```text
recommended_for_eval_suite
```

### 7.7 Scorecard ablation summary

In package logic, compute:

```text
requires_ablation_before_promotion = true
```

when any candidate artifact contains a candidate with:

```text
requires_ablation == true
```

Otherwise:

```text
requires_ablation_before_promotion = false
```

Do not run anything.

---

## 8. Keep `max_candidates_per_pass` prompt-only

### 8.1 No deterministic enforcement

Do not add:

```text
- Pydantic max-length validation
- deterministic truncation
- package-step rejection
- verifier hard failure solely for candidate count
```

A candidate artifact with more than `max_candidates_per_pass` candidates must be able to pass if the verifier accepts it.

### 8.2 Scope artifact

Ensure `workflow_optimization_scope.json` contains:

```json
{
  "max_candidates_per_pass": 3
}
```

This likely already exists. Preserve it.

### 8.3 Prompt guidance

Update `prompts/README.md`:

```markdown
## Candidate budget

`workflow_optimization_scope.max_candidates_per_pass` is a soft authoring budget. Try to keep each candidate-producing pass within that number. This is not a hard schema limit. Use judgment if additional candidates are necessary, but explain why.
```

Update these producer prompts:

```text
optimize_producer_producer.md
optimize_verifier_rubric_producer.md
optimize_tokens_producer.md
adversarial_cases_producer.md
workflow_level_producer.md
```

Add:

```markdown
Read `workflow_optimization_scope.max_candidates_per_pass` and treat it as a soft candidate budget for this pass. Prefer the highest-leverage candidates. Do not pad the list. If you exceed the budget, explain why in the candidate rationale or summary.
```

Update these verifier prompts:

```text
optimize_producer_verifier.md
optimize_verifier_rubric_verifier.md
optimize_tokens_verifier.md
adversarial_cases_verifier.md
workflow_level_verifier.md
package_verifier.md
```

Add:

```markdown
Do not reject solely because the candidate count exceeds `max_candidates_per_pass`. Treat over-budget output as a quality concern only when it makes the artifact unfocused, duplicative, or ungrounded.
```

---

## 9. Contract changes

Modify:

```text
workflows/workflow_run_traces_to_optimization_candidates/contracts.py
```

### 9.1 Add failure seed contract

Add constants/models for:

```text
workflow_failure_scenario_seeds.json
autoloop.workflow_optimization.failure_scenario_seeds/v1
```

The model should require:

```text
schema
selected_workflow
seeds
```

### 9.2 Scorecard fields

Make scorecard fields required:

```text
optimization_depth
ablation_executed
```

Use strict values if the project already uses `Literal`; otherwise use a string field plus a validator.

Valid values:

```text
cheap
standard
ablation
```

`ablation_executed` must be boolean and must be `false` in this workflow.

### 9.3 Candidate count

Do not add any max-candidate validators.

Do not reject candidate lists based on `max_candidates_per_pass`.

### 9.4 Evidence references

Do not add evidence-reference minimum validators.

Evidence fields may exist, but missing evidence references must not invalidate artifacts.

---

## 10. Workflow changes

Modify:

```text
workflows/workflow_run_traces_to_optimization_candidates/workflow.py
```

### 10.1 Frame / deterministic preparation

During or before the failure-mining phase, write:

```text
workflow_failure_scenario_seeds.json
```

using deterministic helper output.

Do not write deterministic scenarios to:

```text
workflow_failure_scenarios.json
```

except the minimal empty no-scenarios fallback.

### 10.2 `on_mine_failures`

Replace deterministic rewrite with validation-only behavior.

Pseudo-logic:

```python
def on_mine_failures(state, outcome, artifacts):
    route = outcome.tag

    if route == "failure_scenarios_mined":
        payload = _load_failure_scenarios_artifact(
            artifacts.workflow_failure_scenarios.path,
            selected_workflow_name=state.selected_workflow_name,
        )
        return state_with_counts(payload)

    if route == "no_failure_scenarios":
        if not artifacts.workflow_failure_scenarios.path.exists():
            _write_empty_failure_scenarios(
                artifacts.workflow_failure_scenarios.path,
                selected_workflow_name=state.selected_workflow_name,
            )
        else:
            _load_failure_scenarios_artifact(
                artifacts.workflow_failure_scenarios.path,
                selected_workflow_name=state.selected_workflow_name,
            )
        return state_with_zero_or_existing_counts()

    if route == "needs_rework":
        return state

    if route == "failed":
        return state

    return state
```

Use actual project conventions for state updates and events.

### 10.3 Validation helper

Add or reuse a helper:

```python
def _load_failure_scenarios_artifact(path: Path, *, selected_workflow_name: str) -> dict[str, Any]:
    ...
```

It must check:

```text
- file exists
- valid JSON object
- schema == autoloop.workflow_optimization.failure_scenarios/v1
- selected_workflow == selected_workflow_name
- failure_scenarios is a list
```

It must not require evidence refs.

### 10.4 Empty fallback helper

Add or reuse:

```python
def _write_empty_failure_scenarios(path: Path, *, selected_workflow_name: str) -> None:
    ...
```

Only call this for `no_failure_scenarios` when the final artifact is missing.

### 10.5 Candidate handlers

Ensure these handlers validate but do not rewrite accepted artifacts:

```text
on_optimize_producer
on_optimize_verifier_rubric
on_optimize_tokens
on_adversarial_cases
on_workflow_level
```

They may write minimal empty artifacts only for skip/not-applicable routes and only when the artifact is absent.

### 10.6 Package

Update package logic to include in scorecard:

```json
{
  "optimization_depth": "<depth>",
  "ablation_executed": false
}
```

Update packet generation to include the Optimization Depth section.

Ensure package step still validates selected workflow source was not mutated.

---

## 11. Prompt changes

### 11.1 `prompts/README.md`

Add sections:

```markdown
## LLM-authored artifact ownership

Deterministic helpers may prepare trace corpora, metrics, rankings, and failure-scenario seeds. Once a producer writes a candidate or failure artifact and the verifier accepts it, workflow handlers validate and publish that artifact; they do not deterministically rewrite it.

## Failure scenario seeds

`workflow_failure_scenario_seeds.json` is deterministic input. `workflow_failure_scenarios.json` is the producer-authored final failure-scenario artifact.

## Optimization depth

- `cheap`: Use existing traces only. Produce concise, high-leverage candidates. Avoid speculative expansion.
- `standard`: Use existing traces only. Perform deeper cross-checking across trace corpus, selected workflow surfaces, priority report, and candidate artifacts. Lower confidence when evidence is thin.
- `ablation`: Do not run ablations. Treat this as ablation-planning mode only. Mark candidates that should be ablated before promotion and include ablation-oriented rationale where useful.

## Candidate budget

`workflow_optimization_scope.max_candidates_per_pass` is a soft authoring budget. Try to keep each candidate-producing pass within that number. This is not a hard schema limit. Use judgment if additional candidates are necessary, but explain why.
```

### 11.2 `mine_failures_producer.md`

Update to say:

```markdown
Read `workflow_failure_scenario_seeds.json` as deterministic input. You own the final `workflow_failure_scenarios.json` artifact. The workflow will validate your artifact but will not deterministically rewrite it.

Use the seeds, trace corpus, raw-output references, priority report, and selected workflow surfaces to author the final failure scenarios.

Do not simply copy seeds mechanically. Refine, merge, split, or discard seeds based on the evidence.
```

### 11.3 `mine_failures_verifier.md`

Update to say:

```markdown
Validate the producer-authored `workflow_failure_scenarios.json`.

`workflow_failure_scenario_seeds.json` is input evidence, not the authoritative final artifact.

Reject invented evidence, invalid schema, wrong selected workflow, or invalid failure kinds.

Do not reject solely because evidence-reference arrays are absent.
```

### 11.4 Candidate producer prompts

For each candidate-producing prompt, add:

```markdown
Read `workflow_optimization_scope.json`.

Apply `optimization_depth`.

Treat `max_candidates_per_pass` as a soft candidate budget.

Do not mutate source files. Write only the required candidate artifact.
```

### 11.5 Candidate verifier prompts

For each candidate verifier prompt, add:

```markdown
Do not reject solely because candidate count exceeds `max_candidates_per_pass`.

Reject direct source mutation, hidden execution claims, invented rerun/ablation claims, invalid schema, wrong selected workflow, or collapsed optimization surfaces.
```

---

## 12. Documentation changes

Modify:

```text
docs/workflows/workflow_run_traces_to_optimization_candidates.md
```

Add or revise sections:

### 12.1 Artifact ownership

```markdown
## Artifact Ownership

The optimizer uses deterministic helpers to prepare trace corpora, step metrics, source manifests, and failure-scenario seeds. LLM producers author failure and candidate artifacts. Workflow handlers validate accepted LLM-authored artifacts and leave them in place; they do not deterministically rewrite them.
```

### 12.2 Failure scenario seeds

```markdown
`workflow_failure_scenario_seeds.json` is deterministic input. `workflow_failure_scenarios.json` is the final producer-authored failure-scenario artifact.
```

### 12.3 Optimization depth

```markdown
- `cheap`: existing traces only; concise candidate generation.
- `standard`: existing traces only; deeper LLM cross-checking; no reruns.
- `ablation`: ablation planning mode only; no ablation execution.
```

### 12.4 Candidate budget

```markdown
`max_candidates_per_pass` is a soft prompt budget. It is not a schema limit and is not deterministically enforced. Verifiers may treat over-budget output as a focus concern, but the workflow does not reject solely on candidate count.
```

### 12.5 No git change

Do not document any change to `commit_after_run` semantics in this patch.

---

## 13. Test changes

Update:

```text
tests/runtime/test_workflow_run_traces_to_optimization_candidates.py
tests/unit/test_optimization_helpers.py
```

### 13.1 Failure mining preserves LLM artifact

Add:

```text
test_mine_failures_preserves_provider_authored_failure_scenarios
```

Test requirements:

```text
1. Seed eligible Plan-1 observability run artifacts.
2. Run optimizer through mine_failures.
3. Script producer to write workflow_failure_scenarios.json with distinctive provider-authored content.
4. Script verifier to return failure_scenarios_mined.
5. Assert workflow_failure_scenarios.json still contains the distinctive content.
6. Assert deterministic seed content did not replace it.
```

### 13.2 Empty fallback only for no scenarios

Add:

```text
test_mine_failures_writes_empty_artifact_only_for_no_failure_scenarios_when_missing
```

Expected:

```text
- route == no_failure_scenarios
- workflow_failure_scenarios.json missing before handler
- handler writes minimal empty valid artifact
```

### 13.3 Malformed artifact is not replaced

Add:

```text
test_mine_failures_malformed_artifact_is_not_replaced
```

Expected:

```text
- provider writes malformed or selected_workflow-mismatched workflow_failure_scenarios.json
- verifier route == failure_scenarios_mined
- workflow does not replace artifact with deterministic generated content
- run fails or follows existing invalid-output behavior
```

### 13.4 Seeds are separate from final scenarios

Add:

```text
test_failure_scenario_seeds_are_written_separately_from_failure_scenarios
```

Expected:

```text
- workflow_failure_scenario_seeds.json exists
- workflow_failure_scenarios.json is LLM-authored or empty fallback
- files have different schema IDs
```

### 13.5 Optimization depth tests

Add:

```text
test_optimization_depth_standard_is_recorded_and_no_reruns_execute
test_optimization_depth_ablation_records_planning_mode_without_executing_ablation
```

Assertions:

```text
- workflow_optimization_scope.json contains requested optimization_depth
- workflow_optimization_scorecard.json contains optimization_depth
- workflow_optimization_scorecard.json contains ablation_executed=false
- workflow_optimization_packet.md says no target workflow reruns were executed
- workflow_optimization_packet.md says no ablations were executed
- no extra target-workflow run is created by optimizer
```

### 13.6 Candidate budget prompt-only test

Add:

```text
test_max_candidates_per_pass_is_prompt_guidance_not_schema_limit
```

Test requirements:

```text
1. Set max_candidates_per_pass=1.
2. Script provider to write two candidates in one candidate artifact.
3. Script verifier to accept.
4. Assert workflow does not fail solely because two candidates exist.
5. Assert workflow_optimization_scope.json contains max_candidates_per_pass=1.
6. Assert both candidates remain in the final artifact.
```

Do not require rendered prompt capture for this test. Prompt capture may be added as an optional extra assertion if already easy.

### 13.7 Update existing tests

If any existing test expects deterministic failure scenarios to be written into `workflow_failure_scenarios.json`, update it to expect:

```text
deterministic seeds -> workflow_failure_scenario_seeds.json
LLM-authored final scenarios -> workflow_failure_scenarios.json
```

---

## 14. Report update

Replace minimal `report.md` with:

```markdown
# Implementation Report

## Summary

Fixed workflow optimization semantics so accepted LLM-authored artifacts are validated and left in place rather than deterministically rewritten. Added deterministic failure-scenario seeds as a separate artifact. Implemented `optimization_depth` as prompt/publication behavior without hidden reruns or ablation execution. Clarified `max_candidates_per_pass` as prompt-only guidance.

## Changed Files

- workflows/workflow_run_traces_to_optimization_candidates/workflow.py
- workflows/workflow_run_traces_to_optimization_candidates/contracts.py
- workflows/workflow_run_traces_to_optimization_candidates/prompts/README.md
- workflows/workflow_run_traces_to_optimization_candidates/prompts/mine_failures_producer.md
- workflows/workflow_run_traces_to_optimization_candidates/prompts/mine_failures_verifier.md
- workflows/workflow_run_traces_to_optimization_candidates/prompts/...
- docs/workflows/workflow_run_traces_to_optimization_candidates.md
- tests/runtime/test_workflow_run_traces_to_optimization_candidates.py
- tests/unit/test_optimization_helpers.py

## Boundaries Preserved

- No runtime git changes.
- No `commit_after_run` changes.
- No target workflow reruns.
- No ablation execution.
- No source mutation.
- No deterministic max-candidate hard gate.

## Tests

List exact pytest commands run and results.
```

---

## 15. Implementation order

Follow this order:

```text
1. Inspect workflow.py for all writes to workflow_failure_scenarios.json.
2. Add workflow_failure_scenario_seeds.json contract/schema/artifact.
3. Redirect deterministic failure-seed generation to workflow_failure_scenario_seeds.json.
4. Change on_mine_failures to validate workflow_failure_scenarios.json instead of rewriting it.
5. Add no_failure_scenarios empty fallback only when final artifact is missing.
6. Audit candidate handlers and remove deterministic rewrites of accepted LLM-authored candidate artifacts.
7. Add required scorecard fields optimization_depth and ablation_executed.
8. Implement package output for optimization_depth and ablation_executed=false.
9. Update packet generation with Optimization Depth section.
10. Update prompts for validation-only ownership, failure seeds, optimization_depth, and soft candidate budget.
11. Update docs.
12. Add/update tests.
13. Update report.md.
14. Run targeted tests.
15. Run full pytest if feasible.
```

---

## 16. Required test commands

At minimum run:

```bash
pytest tests/runtime/test_workflow_run_traces_to_optimization_candidates.py
pytest tests/unit/test_optimization_helpers.py
pytest tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py
pytest tests/test_architecture_baseline_docs.py
```

Then run:

```bash
pytest
```

when feasible.

---

## 17. Acceptance criteria

The patch is complete when all are true:

```text
1. workflow_failure_scenario_seeds.json exists as the deterministic seed artifact.
2. workflow_failure_scenarios.json remains the LLM-authored final failure-scenario artifact.
3. on_mine_failures no longer overwrites valid LLM-authored workflow_failure_scenarios.json.
4. Deterministic failure-scenario output is seed/fallback only.
5. If failure_scenarios_mined is selected with malformed/missing final artifact, the workflow does not silently replace it.
6. If no_failure_scenarios is selected and the final artifact is missing, the workflow writes a minimal empty artifact.
7. Candidate handlers validate accepted artifacts and leave them in place.
8. Not-applicable routes may write minimal empty artifacts only when absent.
9. workflow_optimization_scorecard.json includes optimization_depth.
10. workflow_optimization_scorecard.json includes ablation_executed=false.
11. optimization_depth=standard is reflected in scope, scorecard, and packet.
12. optimization_depth=ablation is reflected as planning mode only.
13. No ablation execution occurs in this workflow.
14. No target workflow reruns occur in this workflow.
15. max_candidates_per_pass is present in workflow_optimization_scope.json.
16. max_candidates_per_pass is described in prompts as a soft budget only.
17. Candidate artifacts are not rejected solely for exceeding max_candidates_per_pass.
18. Tests cover LLM artifact preservation.
19. Tests cover separate failure-scenario seeds.
20. Tests cover optimization_depth.
21. Tests cover max_candidates_per_pass prompt-only behavior.
22. Docs describe validation-only artifact ownership.
23. report.md contains a real implementation report.
24. No runtime git or commit_after_run code is changed.
```

---

## 18. Final boundary

After this patch:

```text
Runtime evidence layer remains unchanged.

Optimizer deterministic code prepares:
  trace corpus
  excluded-run report
  source manifest
  step metrics
  failure-scenario seeds
  scorecard
  refinement evidence
  publication receipt

LLM producers author:
  final failure scenarios
  producer candidates
  verifier/rubric candidates
  token candidates
  adversarial cases
  workflow-level candidates

Workflow handlers:
  validate accepted artifacts
  update state
  publish references
  do not rewrite accepted LLM-authored artifacts

optimization_depth:
  changes prompt/publication semantics only

max_candidates_per_pass:
  soft prompt guidance only

commit_after_run:
  unchanged
```
