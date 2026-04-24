# Cycle 11 Implementation Plan

## Scope anchor

- The request's `src/autoloop/...` paths are stale for this repo. Implementation should target the live package-root layout:
  - `docs/architecture.md`
  - `docs/authoring.md`
  - `core/steps.py`
  - `runtime/loader.py`
  - `runtime/runner.py`
  - `runtime/workspace.py`
  - repo-root `workflows/`
- The existing workflow-builder is credible enough to treat as baseline evidence rather than this cycle's primary ship target:
  - `workflows/workflow_idea_to_workflow_package/`
  - `docs/workflows/workflow_idea_to_workflow_package.md`
  - `tests/runtime/test_workflow_builder_package.py`
- Out of scope unless a concrete blocker appears during implementation:
  - `recursive_autoloop/` package-CLI cleanup
  - public CLI or workspace-layout changes
  - `workflow.toml` schema expansion
  - runtime-owned decomposition or promotion automation

## Addition decision

### Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` major refresh | Mandatory builder baseline and still the greenfield authoring path when the repo lacks a credible builder | The current builder already exists in code, docs, and proof, so another builder-first cycle would defer the stronger ecosystem gap | Deferred |
| `workflow_package_to_composable_building_blocks` | Turns explicit portfolio decomposition pressure into reusable extracted building blocks and parent-rewrite guidance | Requires a new decomposition-specific authoring seam and careful candidate publication, but it directly fills the next missing recursive layer | Chosen |
| `company_operation_to_recursive_improvement_cycle` | Long-range operating-system workflow across company work history | Premature while the workflow portfolio still lacks the decomposition layer that governance already identified as next | Deferred |

### Chosen addition summary

- Problem solved: turn one mature workflow package plus explicit decomposition pressure into a candidate decomposition package that extracts reusable building blocks and a parent rewrite without mutating the authoritative workflow in place.
- Why it matters: portfolio governance can now say `decompose`, but the repository still lacks the workflow that turns that pressure into reusable packages, interfaces, docs, tests, and a migration-ready candidate surface.
- Likely sponsors: workflow maintainers, engineering-productivity owners, AI platform teams, recursive portfolio operators, and delivery teams that want reuse instead of repeated monolith workflow growth.
- Classification: reusable workflow building block.
- Why Autoloop fits: decomposition is multi-turn, artifact-heavy, verifier-sensitive, and needs deterministic baseline/candidate separation plus publish-time validation.
- Why one-shot is insufficient: credible decomposition needs selected-workflow structural capture, evidence-backed extraction boundaries, candidate file generation, parent-rewrite planning, validation, and rollback evidence.
- Terminal outcome: a published candidate decomposition package containing a structured decomposition surface, extraction strategy, candidate repo overlay, machine-readable building-block manifest, migration guide, promotion record, rollback plan, and receipt.

## Planned workflow contract

### Objective

Turn one selected workflow package plus optional decomposition-evidence artifacts into a verifier-gated candidate decomposition package that another operator or workflow can validate and promote later.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture authoritative local copies of the selected workflow's decomposition surface and baseline parent workflow surface.
- Keep framing, extraction planning, candidate implementation, evaluation, and publication as separate work items.
- Derive the candidate decomposition manifest deterministically from the published candidate overlay.
- Validate that the candidate overlay stays within the allowed repo boundary and stops at candidate publication rather than hidden promotion.

### Provider-owned cognitive responsibilities

- Interpret the selected workflow's topology, prompts, artifacts, and evidence inputs.
- Decide which reusable units justify extraction and what their interface boundaries should be.
- Author the candidate building-block packages, parent rewrite, docs, and tests inside the candidate overlay.
- Produce migration guidance, verification evidence, and promotion/rollback recommendations.

### Work-item boundary doctrine

- `capture_decomposition_context`: deterministic evidence capture only.
- `frame_decomposition_request`: why decompose now, what must remain stable, and what success looks like.
- `design_decomposition_plan`: extraction boundaries, interface contracts, parent rewrite plan, and regression guardrails.
- `implement_candidate_decomposition`: candidate repo overlay, machine-readable manifests, and build evidence only.
- `evaluate_candidate_decomposition`: verification package, migration guide, promotion record, and rollback plan only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the selected workflow, decomposition boundary, artifact graph, or acceptance surface changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_decomposition_context`
- `workflow decomposition framer` / `decomposition-request verifier`
- `workflow decomposition strategist` / `decomposition-plan verifier`
- `workflow decomposer` / `decomposition-build verifier`
- `workflow decomposition evaluator` / `decomposition-release verifier`
- deterministic `publish_candidate_decomposition`

### Planned control flow

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

### Runtime-injected control contract

The runtime must inject or enforce only:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `DecompositionRequestFramingPayload`
- `DecompositionPlanPayload`
- `CandidateDecompositionBuildPayload`
- `CandidateDecompositionEvaluationPayload`

### Planned artifact contract

| Step | Required reads | Required writes | Notes |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_decomposition_context` | request, invocation contract, selected workflow, optional evidence paths | `selected_workflow_decomposition_surface.json`, `baseline_parent_workflow_surface/`, `baseline_parent_manifest.json`, `decomposition_evidence_manifest.json` | authoritative input bundle and immutable baseline copy |
| `frame_decomposition_request` | request, invocation contract, decomposition surface, baseline manifest, evidence manifest, framework docs | `decomposition_request_brief.md`, `decomposition_acceptance_criteria.md` | authoritative framing package |
| `design_decomposition_plan` | captured context, framing artifacts | `extraction_strategy.md`, `building_block_interface_contracts.json`, `parent_rewrite_plan.md`, `regression_guardrails.md` | authoritative extraction boundary and interface contract |
| `implement_candidate_decomposition` | captured context, planning artifacts, baseline parent surface | `candidate_decomposition_surface/`, `candidate_decomposition_manifest.json`, `candidate_building_block_index.json`, `decomposition_build_report.md`, `candidate_diff_summary.md` | candidate repo overlay and deterministic manifest |
| `evaluate_candidate_decomposition` | candidate overlay, candidate manifest, captured context, planning artifacts | `decomposition_verification_report.md`, `composition_migration_guide.md`, `promotion_record.md`, `rollback_plan.md` | authoritative verification and migration package |
| `publish_candidate_decomposition` | selected-workflow snapshots, baseline manifest, candidate manifest, evaluation artifacts | `workflow_decomposition_receipt.json` | deterministic receipt proving the candidate package is explicit and publication-ready |

### Planned prompt templates

- `prompts/frame_producer.md`: names the framing role, decomposition trigger, required reads, required writes, evidence rules, route guidance, and forbidden hidden execution.
- `prompts/frame_verifier.md`: checks that decomposition scope, non-goals, and acceptance criteria are explicit enough for extraction planning.
- `prompts/design_producer.md`: designs building-block boundaries, interface contracts, parent rewrite, and regression guardrails.
- `prompts/design_verifier.md`: validates that the decomposition plan is concrete, composable, and still within the selected workflow boundary.
- `prompts/implement_producer.md`: creates the candidate overlay under workflow-local storage without mutating the authoritative repo.
- `prompts/implement_verifier.md`: checks that the candidate overlay and manifest are explicit enough for deterministic evaluation and publication.
- `prompts/evaluate_producer.md`: writes the verification report, migration guide, promotion record, and rollback plan.
- `prompts/evaluate_verifier.md`: confirms the candidate package is publication-ready and still stops before promotion.

### Workflow parameters

- `selected_workflow` required
- `task_title` required
- `evidence_paths` optional and repeatable
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable
- `target_test_command` optional, default `pytest -q`
- `max_candidate_building_blocks` optional, default `3`

### Verification and evidence contract

- Workflow discovery must prove the package is discoverable by canonical name and alias and compiles with explicit pair-step control contracts.
- `capture_decomposition_context` must always write `decomposition_evidence_manifest.json`:
  - when `evidence_paths` are supplied, the manifest must list the copied evidence artifacts and their source paths
  - when no `evidence_paths` are supplied, the manifest must record `request.md` as the fallback authoritative context
  - when a supplied evidence path cannot be read, the step must route to `blocked` rather than silently dropping the missing evidence
- `implement_candidate_decomposition` must produce a candidate overlay that includes:
  - a rewritten parent workflow surface
  - at least one extracted building-block package
  - the associated docs/test footprint captured by `candidate_decomposition_manifest.json` and `candidate_building_block_index.json`
- `evaluate_candidate_decomposition` must produce `decomposition_verification_report.md`, `composition_migration_guide.md`, `promotion_record.md`, and `rollback_plan.md` before `publish_candidate_decomposition` can issue the receipt.
- Overlay validation should stay local to this workflow by default. Only extract a minimal shared helper if duplication proves unavoidable, and if that happens rerun `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py` alongside the primary targeted suite.

### Rework / replan / block / fail policy

- `needs_rework`: use when the selected workflow, extracted building-block set, and accepted decomposition boundary still hold, but the current framing, plan, overlay, or verification artifacts need local repair.
- `needs_replan`: use when the selected workflow, extraction boundary, parent-rewrite strategy, package set, artifact graph, or acceptance surface changed materially enough that the current work item no longer fits.
- `blocked`: use when required inputs cannot be captured or validated without external intervention, including unreadable `evidence_paths`, an unresolved selected-workflow reference, or a missing baseline artifact needed to preserve the candidate-only boundary.
- `failed`: use when the workflow reaches an irreconcilable contradiction that local repair cannot address, such as a candidate overlay that cannot satisfy the declared decomposition boundary without violating the preserved invariants.

### Recursive self-improvement policy

- The workflow may propose extracted building blocks, parent rewrites, and follow-on framework changes, but they must stay inside the candidate overlay plus evaluation artifacts for this run.
- The authoritative selected workflow package must remain unchanged during this workflow; promotion stays explicit and evidence-gated through `promotion_record.md`, `rollback_plan.md`, and `workflow_decomposition_receipt.json`.
- Any follow-on shared abstraction beyond the chosen decomposition-surface helper must remain minimal, justified by demonstrated duplication, and paired with regression proof against the existing refinement workflow before adoption.

## Framework improvement decision

### Framework improvement candidates considered

| Candidate | Benefits | Trade-off | Decision |
| --- | --- | --- | --- |
| Additive authoring-only decomposition surface helper | Gives decomposition workflows one structured artifact that combines selected-workflow topology, prompt paths, artifact contracts, and editable package surface without widening runtime behavior | Adds one focused stdlib seam plus docs/tests, but keeps decomposition policy visible in workflow code and prompts | Chosen |
| Expand `write_selected_workflow_authoring_surface(...)` to include compiled step and route metadata | Reuses an existing helper name and avoids a new file | Blurs compiled contract capture with editable-surface capture, making the authoring boundary less legible | Rejected |
| Runtime-owned decomposition metadata or `workflow.toml` composability fields | Could reduce workflow-local file inspection | Widens runtime or manifest semantics, pushes dynamic decomposition policy into framework code, and violates the workflow-owned SOP doctrine | Rejected |

### Chosen framework slice

- Add `stdlib/decomposition.py` with `write_selected_workflow_decomposition_surface(ctx, workflow, relative_path="selected_workflow_decomposition_surface.json")`.
- The helper must compose existing discovery/compiler seams instead of scraping workflow files ad hoc.
- The helper output should include:
  - selected workflow identity and package paths
  - authoring surface paths (`workflow.py`, `workflow.toml`, prompts, assets, docs, runtime test, optional params/contracts)
  - compiled step topology, session names, prompt paths, required/provided artifacts, available routes, and route contracts
  - repo-root-relative path metadata suitable for later baseline/candidate validation
- Export the helper from `stdlib/__init__.py`.
- Document the helper boundary in `docs/authoring.md`.
- Add unit coverage and baseline-doc assertions for the new helper.

## Meaningful design decisions

### 1. Publication boundary

- Alternatives considered:
- mutate the selected workflow package in place
- stop at prose-only extraction guidance
- publish a workflow-local candidate overlay plus receipt
- Selected: publish a workflow-local candidate overlay plus receipt
- Why: it preserves explicit baseline/candidate separation, keeps rollback straightforward, and matches the existing evidence-gated refinement doctrine.

### 2. Candidate artifact layout

- Alternatives considered:
- separate parent and child candidate folders with no shared overlay manifest
- recursive composition around `workflow_idea_to_workflow_package` for every extracted block
- one repo-relative `candidate_decomposition_surface/` plus deterministic manifest and building-block index
- Selected: one repo-relative candidate overlay plus deterministic manifest and index
- Why: it gives publish-time validation one authoritative surface, keeps package discovery/test proof simple, and makes migration diffs inspectable.

### 3. Decomposition context capture

- Alternatives considered:
- let the workflow stitch together `selected_workflow_capability.json` and `selected_workflow_authoring_surface.json` locally every time
- widen `workflow.toml` with extraction metadata
- add a dedicated decomposition-surface helper that combines compiled and editable workflow structure
- Selected: dedicated decomposition-surface helper
- Why: decomposition needs a structured snapshot of step topology plus editable files, and that is a reusable authoring seam without turning decomposition policy into runtime logic.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc repo scraping and direct mutation | New workflow package reads raw files and rewrites the authoritative selected workflow directly | Smallest initial diff, but highest regression risk and weakest publication boundary | Rejected |
| Decomposition helper + dedicated workflow package + candidate overlay publication | Add a narrow authoring seam, publish a workflow-local candidate overlay, validate it deterministically, and stop before promotion | Slightly broader change set, but it is the clearest reusable and inspectable design | Selected |
| Invoke `workflow_idea_to_workflow_package` repeatedly for each extracted block and patch the parent afterward | Reuses the builder as a child workflow for package creation | Hides the decomposition boundary behind nested authoring flows and complicates parent/child candidate consistency | Rejected |

## Milestones

### Phase 1: decomposition-surface-seam

- Add `stdlib/decomposition.py` and export `write_selected_workflow_decomposition_surface(...)`.
- Update `docs/authoring.md` with the helper boundary and keep `docs/architecture.md` unchanged unless implementation exposes a public-architecture gap.
- Extend `tests/unit/test_stdlib_and_extensions.py` and `tests/test_architecture_baseline_docs.py` for the helper contract.

### Phase 2: workflow-package-to-building-blocks

- Create `workflows/workflow_package_to_composable_building_blocks/` with:
  - `__init__.py`
  - `params.py`
  - `contracts.py`
  - `workflow.py`
  - `workflow.toml`
  - prompt templates and prompt `README.md`
  - checklist asset
- Create `docs/workflows/workflow_package_to_composable_building_blocks.md`.
- Create `tests/runtime/test_workflow_package_to_composable_building_blocks.py`.
- Keep overlay validation local to the new workflow by default; only extract a minimal shared helper if duplication proves unavoidable, and rerun refinement regression proof if that happens.

### Phase 3: recursive-memory-and-validation

- Update:
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
- Extend `tests/test_architecture_baseline_docs.py` for the cycle-11 baseline.
- Run targeted validation and record closeout evidence.

## Compatibility, regression, and rollback notes

- No public CLI, config, workflow-discovery, or workspace-layout changes are planned.
- Keep runtime/provider boundary unchanged: no new runtime-injected control surfaces beyond `expected_output_schema`, `available_routes`, and `route_contracts`.
- Prefer no edits to `core/steps.py`, `runtime/loader.py`, `runtime/runner.py`, or `runtime/workspace.py` unless implementation uncovers a strict bug or a reusable read-only helper need.
- The new helper must remain authoring-only and read-only with respect to selected workflow packages.
- The new workflow must publish a candidate overlay and receipt only; it must not auto-promote, auto-run downstream workflows, or mutate the authoritative selected workflow in place.
- Rollback path:
  - remove the new stdlib helper/export/doc/test additions
  - remove the new workflow package, workflow doc, and runtime test
  - revert cycle-11 recursive-memory updates as one coherent block

## Validation plan

- Primary targeted suite:
  - `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py`
- Conditional regression suite if implementation extracts or shares overlay-validation logic with the refinement workflow:
  - `.venv/bin/pytest -q tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- Publish-step validation expectations:
  - candidate overlay stays within allowed repo-relative boundaries
  - selected workflow and candidate manifest identities match
  - at least one extracted building-block package is present and discoverable in the candidate overlay
  - parent rewrite remains explicit
  - `request.md` becomes the authoritative fallback context when no `evidence_paths` are supplied, and unreadable evidence paths route to `blocked`
  - hidden downstream execution or promotion language is rejected

## Risk register

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| The helper duplicates existing refinement snapshot logic without adding real reuse | Could create technical debt instead of a clean new seam | Build the helper by composing existing discovery/compiler surfaces and keep baseline-copy logic local to the new workflow |
| Candidate overlay validation drifts from the refinement publication discipline | Could allow broken multi-package candidate surfaces to publish | Reuse the refinement workflow's validation invariants and add conditional regression coverage if shared logic is extracted |
| The workflow slips into plan-only output instead of producing candidate packages | Would fail the end-state requirement for reusable extracted building blocks | Make candidate overlay, manifest, building-block index, and receipt required artifacts on the implementation and publication path |
| The workflow starts acting like runtime-owned automation | Would violate the workflow-owned SOP doctrine | Keep decomposition policy in prompts and workflow code; reject runtime-owned auto-decomposition, auto-promotion, or `workflow.toml` expansion |
