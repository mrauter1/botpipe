# `workflow_package_to_composable_building_blocks`

`workflow_package_to_composable_building_blocks` is a reusable decomposition building block that turns one selected workflow package plus explicit decomposition pressure into a baseline parent snapshot, a workflow-local candidate decomposition overlay, explicit migration and verification artifacts, and a deterministic decomposition receipt. It stops before promotion so later adoption remains explicit and inspectable.

## Problem and value

- Problem solved: convert explicit decomposition pressure into a candidate parent rewrite plus extracted building-block packages instead of leaving decomposition as portfolio-governance prose.
- Why it matters: once portfolio governance can recommend `decompose`, the repository still needs a reusable workflow that turns that recommendation into package interfaces, candidate files, migration guidance, and promotion or rollback evidence.
- Likely sponsors: workflow maintainers, engineering-productivity owners, AI platform teams, recursive portfolio operators, and delivery teams trying to reduce repeated monolith workflow growth.
- Classification: reusable workflow building block.
- Why Autoloop fits: decomposition is artifact-heavy, verifier-sensitive, multi-turn work that needs durable baseline and candidate surfaces plus deterministic publication checks.
- Why one-shot is insufficient: credible decomposition needs selected-workflow capture, accepted extraction boundaries, candidate package authoring, migration planning, verification, and publication-side validation that the authoritative parent workflow stayed untouched.

## Invocation

- Package path: `workflows/workflow_package_to_composable_building_blocks/`
- Discovery: `autoloop workflows show workflow_package_to_composable_building_blocks`
- Direct run:

```bash
autoloop run workflow_package_to_composable_building_blocks <task-id> \
  --message "Decompose the release workflow into reusable building blocks." \
  -wf selected_workflow release_candidate_to_go_no_go \
  -wf task_title "Release workflow decomposition candidate" \
  -wf evidence_paths .autoloop/signals/release_decomposition_pressure.md \
  -wf sponsor_role "engineering productivity" \
  -wf desired_outcome "Publish a candidate decomposition overlay, migration guide, and decomposition receipt for the selected workflow." \
  -wf constraints "Keep runtime control narrow and stop before promotion." \
  -wf constraints "Reject hidden execution and boundary drift during publication." \
  -wf target_test_command "pytest -q tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_release_decision_evidence_pack.py" \
  -wf max_candidate_building_blocks 2
```

Params:

- `selected_workflow` required
- `task_title` required
- `evidence_paths` optional and repeatable
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable
- `target_test_command` optional, default `pytest -q`
- `max_candidate_building_blocks` optional, default `3`

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` major refresh | Mandatory builder baseline and still the greenfield authoring path when the repo lacks a credible builder | The current builder already exists in code, docs, and proof, so another builder-first cycle would defer the stronger ecosystem gap | Deferred |
| `workflow_package_to_composable_building_blocks` | Turns explicit portfolio decomposition pressure into reusable extracted building blocks and parent-rewrite guidance | Requires a decomposition-specific authoring seam and careful candidate publication, but it directly fills the next missing recursive layer | Chosen and shipped in cycle 11 |
| `company_operation_to_recursive_improvement_cycle` | Long-range operating-system workflow across company work history | Premature while the portfolio still lacked the decomposition layer that governance identified as the next missing consumer | Deferred |

The workflow-builder was explicitly reconsidered and not selected because the repository already has a credible baseline in `workflow_idea_to_workflow_package`, `docs/workflows/workflow_idea_to_workflow_package.md`, and `tests/runtime/test_workflow_builder_package.py`.

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive authoring-only decomposition surface helper | Gives decomposition workflows one structured artifact that combines selected-workflow identity, authoring-surface paths, and compiled route topology without widening runtime behavior | Adds one focused stdlib seam plus docs/tests, but keeps decomposition policy visible in workflow code and prompts | Chosen in the paired framework slice and consumed here |
| Expand the existing refinement authoring-surface helper | Reuses an existing helper name and may reduce helper count | Blurs editable-surface capture with decomposition-specific compiled topology capture, making later workflow pressure harder to read | Rejected |
| Runtime-owned decomposition metadata or `workflow.toml` composability fields | Could reduce workflow-local file inspection | Widens runtime or manifest semantics, hides workflow meaning, and violates the workflow-owned SOP doctrine | Rejected |

## Meaningful design decisions

### 1. Publication boundary

- Alternatives considered:
- mutate the selected workflow package in place
- stop at prose-only extraction guidance
- publish a workflow-local candidate decomposition overlay plus receipt
- Selected: publish a workflow-local candidate overlay plus receipt
- Why: it keeps promotion explicit, preserves the authoritative parent workflow package, and still produces a terminal artifact set another operator or workflow can adopt later.

### 2. Evidence boundary

- Alternatives considered:
- auto-discover decomposition pressure from portfolio-governance history
- require only the selected workflow and let the provider infer the rest
- capture explicit evidence paths and fall back to `request.md` only when no evidence paths are supplied
- Selected: explicit evidence paths with `request.md` fallback
- Why: it keeps the workflow inspectable, deterministic, and usable even when the calling context only has the current request snapshot.

### 3. Hidden-execution discipline

- Alternatives considered:
- trust the provider-authored candidate overlay without a declared package index
- let publication infer new package boundaries only from `candidate_decomposition_surface/`
- require an explicit `candidate_building_block_index.json` and reject non-`candidate_only` publication modes or undeclared package roots
- Selected: explicit building-block index plus publish-time rejection of hidden execution
- Why: decomposition introduces new runnable packages, docs, and tests; those need an explicit declared boundary instead of implicit discovery at publication time.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc repo scraping | Build the decomposition package directly and let workflow code discover selected-workflow files manually | Smallest initial diff, but duplicates selected-workflow discovery logic and weakens inspectability | Rejected |
| Shared decomposition seam plus dedicated workflow package plus local publish-time validation | Reuse the decomposition surface helper, build the workflow package on top of it, and keep overlay validation local to decomposition | Slightly broader change set, but the clearest reusable and inspectable design | Selected |
| Runtime-owned decomposition or promotion automation | Centralize package extraction and publication behavior in the runtime | Hides workflow meaning in framework code and widens runtime semantics prematurely | Rejected |

## Workflow contract

### Objective

Turn one selected workflow package plus explicit decomposition evidence into a candidate decomposition package without mutating the authoritative selected workflow package and without hiding promotion or rollback policy in runtime code.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture one selected workflow decomposition surface plus a copied baseline parent workflow surface and manifest.
- Capture authoritative decomposition evidence, falling back to `request.md` only when no explicit evidence paths are supplied.
- Keep framing, planning, implementation, evaluation, and publication as separate work items.
- Derive `candidate_decomposition_manifest.json` deterministically from `candidate_decomposition_surface/` plus `candidate_building_block_index.json`.
- Validate candidate-only publication, selected-workflow identity, declared building-block boundaries, and overlay test proof before publishing the receipt.

### Provider-owned cognitive responsibilities

- Interpret the selected workflow’s topology, artifacts, and evidence bundle.
- Decide which reusable building blocks justify extraction and how the parent workflow should change after extraction.
- Author the candidate parent rewrite and extracted building-block packages inside the candidate overlay.
- Produce migration, promotion, and rollback guidance.

### Work-item boundary doctrine

- `capture_decomposition_context`: deterministic baseline and evidence capture only.
- `frame_decomposition_request`: why decompose now, what must remain stable, and what success looks like.
- `design_decomposition_plan`: extraction boundaries, interface contracts, parent rewrite plan, and regression guardrails only.
- `implement_candidate_decomposition`: candidate overlay, declared building-block index, and build evidence only.
- `evaluate_candidate_decomposition`: verification package, migration guide, promotion record, and rollback plan only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the selected workflow, extracted package set, or acceptance surface changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_decomposition_context`
- `workflow decomposition framer` / `decomposition-request verifier`
- `workflow decomposition strategist` / `decomposition-plan verifier`
- `workflow decomposer` / `decomposition-build verifier`
- `workflow decomposition evaluator` / `decomposition-release verifier`
- deterministic `publish_candidate_decomposition`

### Control flow

1. `bootstrap`
2. `capture_decomposition_context`
3. `frame_decomposition_request`
4. `design_decomposition_plan`
5. `implement_candidate_decomposition`
6. `evaluate_candidate_decomposition`
7. `publish_candidate_decomposition`

### Route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `decomposition_context_captured`
- `decomposition_request_framed`
- `decomposition_plan_designed`
- `candidate_decomposition_built`
- `candidate_decomposition_evaluated`
- `candidate_decomposition_published`
- `needs_rework`
- `needs_replan`

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_decomposition_context` | request, invocation contract, selected-workflow reference, optional evidence paths | `selected_workflow_decomposition_surface.json`, `baseline_parent_workflow_surface/`, `baseline_parent_manifest.json`, `decomposition_evidence_manifest.json` | authoritative parent-workflow and evidence bundle |
| `frame_decomposition_request` | request, invocation contract, captured parent surface, evidence manifest, framework docs | `decomposition_request_brief.md`, `decomposition_acceptance_criteria.md` | authoritative decomposition framing package |
| `design_decomposition_plan` | request, invocation contract, captured context, framing artifacts | `extraction_strategy.md`, `building_block_interface_contracts.json`, `parent_rewrite_plan.md`, `regression_guardrails.md` | authoritative extraction plan and interface boundary |
| `implement_candidate_decomposition` | captured context, accepted plan, baseline parent workflow surface | `candidate_decomposition_surface/`, `candidate_building_block_index.json`, `decomposition_build_report.md`, `candidate_diff_summary.md`, deterministic `candidate_decomposition_manifest.json` | authoritative candidate overlay plus declared package boundary |
| `evaluate_candidate_decomposition` | candidate overlay, deterministic manifest, building-block index, captured context, plan artifacts | `decomposition_verification_report.md`, `composition_migration_guide.md`, `promotion_record.md`, `rollback_plan.md` | authoritative verification, migration, and promotion or rollback package |
| `publish_candidate_decomposition` | selected-workflow decomposition surface, baseline manifest, evidence manifest, candidate manifest, building-block index, evaluation artifacts | `workflow_decomposition_receipt.json` | deterministic terminal receipt proving the candidate package is explicit and publication-ready |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `DecompositionRequestFramingPayload`
- `DecompositionPlanPayload`
- `CandidateDecompositionBuildPayload`
- `CandidateDecompositionEvaluationPayload`

### Prompt templates

- `prompts/frame_producer.md`: role `workflow decomposition framer`; frames the selected parent workflow and evidence bundle without designing package changes yet.
- `prompts/frame_verifier.md`: role `decomposition-request verifier`; checks that the selected workflow, evidence bundle, and acceptance boundary are explicit enough for planning.
- `prompts/design_producer.md`: role `workflow decomposition strategist`; designs the extraction strategy, interface contracts, parent rewrite plan, and regression guardrails.
- `prompts/design_verifier.md`: role `decomposition-plan verifier`; checks that the plan is concrete, bounded, and still candidate-only.
- `prompts/implement_producer.md`: role `workflow decomposer`; creates `candidate_decomposition_surface/` and the declared building-block index without mutating the authoritative parent workflow package.
- `prompts/implement_verifier.md`: role `decomposition-build verifier`; checks that the candidate surface is explicit enough for deterministic manifest derivation and later evaluation.
- `prompts/evaluate_producer.md`: role `workflow decomposition evaluator`; writes the verification report, migration guide, promotion record, and rollback plan.
- `prompts/evaluate_verifier.md`: role `decomposition-release verifier`; checks that the evaluation package is publication-ready and still stops before promotion.

## Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose typed route metadata and payload schemas for the four pair steps.
- `capture_decomposition_context` must always write `decomposition_evidence_manifest.json`:
- when `evidence_paths` are supplied, the manifest must list the copied evidence artifacts and their source paths
- when no `evidence_paths` are supplied, the manifest must record `request.md` as the fallback authoritative context
- when a supplied evidence path cannot be read, the workflow must route to `blocked` during context capture instead of silently dropping the missing evidence
- `implement_candidate_decomposition` must produce:
- `candidate_decomposition_surface/`
- `candidate_building_block_index.json`
- deterministic `candidate_decomposition_manifest.json`
- `decomposition_build_report.md`
- `candidate_diff_summary.md`
- `evaluate_candidate_decomposition` must produce `decomposition_verification_report.md`, `composition_migration_guide.md`, `promotion_record.md`, and `rollback_plan.md` before publication can issue the receipt.
- Publish-time validation rejects:
- hidden execution through non-`candidate_only` building-block publication modes
- selected-workflow identity drift
- candidate-manifest drift from the actual `candidate_decomposition_surface/` file set
- missing declared building-block docs or runtime tests
- candidate files outside the declared repo-relative boundary
- candidate-manifest or building-block-index drift
- overlay validation failures against the declared test command

## Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, planning, implementation, or evaluation boundary.
- `needs_replan`: the selected workflow, extracted package set, accepted boundary, or migration posture changed materially enough that earlier work must be revisited.
- `blocked`: a required input cannot be captured or validated without external intervention, including unreadable evidence paths or missing baseline files needed to preserve the candidate-only boundary.
- `failed`: irreconcilable contradictions make the current decomposition package non-credible.

## Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring path and was reconsidered before choosing this narrower decomposition layer.
- `workflow_portfolio_to_operating_system` remains the standing portfolio-governance workflow; this package consumes explicit decomposition pressure instead of re-deriving governance locally.
- Promotion remains evidence-gated by the decomposition surface snapshot, baseline manifest, evidence manifest, candidate manifest, declared building-block index, evaluation package, and deterministic receipt.
- The paired framework improvement remains additive and authoring-only: `write_selected_workflow_decomposition_surface(...)` gives decomposition workflows one selected-workflow capture surface without widening runtime-owned behavior.

## Evidence

- Package implementation: `workflows/workflow_package_to_composable_building_blocks/`
- Shared decomposition seam consumed: `stdlib/decomposition.py`
- Workflow asset: `workflows/workflow_package_to_composable_building_blocks/assets/decomposition_package_checklist.md`
- Workflow-specific proof: `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- The scripted tests prove workflow discovery, compilation, prompt contract markers, terminal candidate publication, fallback evidence capture, blocked unreadable evidence paths, and publish-side rejection of hidden execution, identity drift, and boundary escapes.
