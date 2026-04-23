# Cycle 4 Implementation Plan

## Scope considered

- Authoritative request snapshot plus the current raw phase log. No clarifications have been appended for this run beyond the initial runtime state.
- Current repo-root architecture and workflow surfaces, not the retired `src/autoloop/...` layout referenced in older recursive templates.
- Mandatory/current-equivalent inspection completed across:
  - `docs/architecture.md`
  - `docs/authoring.md`
  - `core/steps.py`
  - `core/compiler.py`
  - `core/engine.py`
  - `core/context.py`
  - `runtime/loader.py`
  - `runtime/cli.py`
  - `stdlib/composition.py`
  - current workflow packages under `workflows/`
  - standing recursive memory under `.autoloop_recursive/`

## Repository findings

- `workflow_idea_to_workflow_package` is already a credible workflow-builder with docs and runtime proof in `tests/runtime/test_workflow_builder_package.py`.
- The current portfolio now contains:
  - a credible builder
  - two standalone domain workflows
  - one reusable evidence-building block
  - one production consumer of that building block
- The clearest missing capability is still the portfolio front door: there is no explicit workflow that decides whether an arbitrary task should run an existing workflow, compose several, adapt one, or trigger creation of a new workflow.
- The request snapshot still names `docs/autoloop_workflow_framework_prd.md`, `docs/autoloop_workflow_framework_adr.md`, and `src/autoloop/...`, but the live repo intentionally replaced those with `docs/architecture.md`, `docs/authoring.md`, and the repo-root `core/`, `runtime/`, `workflow/`, and `workflows/` packages. Tests already enforce the retired paths stay absent.

## Part 1 decision: new workflow addition

### Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline and still the foundation for new workflow authoring | Already credible; repeating another builder-first cycle would delay the now higher-value portfolio-routing gap | Deferred |
| `task_to_candidate_workflow_set` | Valuable reusable discovery building block for workflow retrieval and fit-gap comparison | Too narrow for this cycle because it does not reach the required terminal decision among run, compose, adapt, or create-new | Deferred |
| `task_to_workflow_strategy` | Gives Autoloop a real front door that converts an arbitrary task into an explicit workflow strategy and next-action package | Requires reusable portfolio discovery support and careful artifact design so the strategy stays inspectable instead of turning into hidden runtime routing | Chosen |

### Chosen addition

- Addition: `task_to_workflow_strategy`
- Classification: end-to-end workflow
- Problem solved: turn an arbitrary software-work request into a concrete workflow strategy with one explicit recommendation:
  - run an existing workflow as-is
  - compose existing workflows
  - adapt an existing workflow for this task
  - create a new workflow because the portfolio is insufficient
- Why it matters: the current portfolio is strong enough to reuse, but Autoloop still lacks a deterministic front door that makes reuse-over-rebuild decisions explicit and durable.
- Likely sponsors: engineering productivity, platform, TPM, delivery leadership, consulting delivery teams, or recursive portfolio owners.
- Why Autoloop fits: the job requires durable portfolio inspection, explicit fit-gap analysis, strategy packaging, and verifier-gated local repair across multiple artifacts.
- Why one-shot is insufficient: the strategy must survive inspection and downstream handoff; it needs authoritative artifacts, machine-readable summary state, and bounded rework versus replan behavior.
- Terminal outcome: a strategy package that another operator or workflow can use immediately, with an explicit selected route, rationale, and next-action handoff artifact.

## Part 2 decision: framework improvement

### Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Shared workflow-catalog seam plus workflow-local portfolio snapshot helper | Gives strategy-style workflows a reusable, inspectable way to discover the current portfolio and publish a stable snapshot artifact without hiding control flow in the runtime | Requires a small shared discovery module and additive authoring helper/docs/tests | Chosen |
| Expand `workflow.toml` with richer strategy metadata | Improves machine-readable routing precision | Raises the public manifest surface, forces repo-wide metadata backfill, and is a larger compatibility surface than cycle 4 needs | Deferred |
| Runtime-owned automatic router / selector | Could make front-door execution terse | Hides portfolio policy in framework logic and violates the requirement to keep workflow semantics visible | Rejected |

### Chosen framework improvement

- Improvement: add a shared workflow-catalog discovery seam plus an additive authoring helper that writes a workflow-local portfolio snapshot artifact.
- Why this is the best fit:
  - it directly supports `task_to_workflow_strategy`
  - it generalizes to later candidates such as `task_to_candidate_workflow_set`, `candidate_workflow_to_adapted_execution_plan`, and `workflow_portfolio_to_operating_system`
  - it keeps routing policy in workflow definitions and prompts rather than runtime-owned branches
  - it avoids expanding the manifest contract before the portfolio proves richer machine-readable metadata is necessary

## Meaningful design decisions

### 1. Front-door boundary

- Alternatives considered:
  - ship a narrower discovery building block only
  - auto-run the selected workflow from the front-door workflow
  - stop at an execution-ready strategy package
- Selected: stop at an execution-ready strategy package
- Why: the workflow should make the portfolio decision explicit and auditable, not hide downstream execution policy inside the front door.

### 2. Portfolio discovery boundary

- Alternatives considered:
  - let prompts scrape the repo ad hoc with no shared snapshot artifact
  - widen `workflow.toml` immediately with richer routing metadata
  - add a shared catalog seam plus a workflow-local snapshot artifact
- Selected: shared catalog seam plus workflow-local snapshot artifact
- Why: this keeps the framework improvement additive, reusable, inspectable, and compatible with the current metadata-only manifest doctrine.

### 3. Strategy package shape

- Alternatives considered:
  - route-specific terminal artifacts only
  - one monolithic summary file only
  - one human-facing strategy package, one machine-readable summary, and one normalized next-action artifact
- Selected: human-facing package + machine-readable summary + normalized next-action artifact
- Why: it gives downstream humans and later workflows a stable terminal contract without inventing separate publish semantics for each selected route.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Runtime-owned selector | Add runtime routing or automatic workflow invocation in `runtime/runner.py` or `runtime/cli.py` | Fastest apparent execution path, but highest doctrine and regression risk | Rejected |
| Workflow-only implementation with ad hoc repo scraping | Implement `task_to_workflow_strategy` directly and let prompts/workflow code discover workflows ad hoc | Smaller diff, but repeats discovery logic and leaves a clear portfolio seam unaddressed | Rejected |
| Add a shared catalog seam, then implement the strategy workflow on top of it | Slightly broader change set, but reusable and keeps semantics visible in workflow code and docs | Selected |

## Planned implementation shape

### Phase 1: shared workflow-catalog seam

Target files:

- `core/workflow_catalog.py` or equivalent shared pure discovery module
- `runtime/loader.py`
- `stdlib/portfolio.py`
- `stdlib/__init__.py`
- `docs/authoring.md`
- `tests/unit/test_stdlib_and_extensions.py`

Planned interfaces:

- `WorkflowCatalogEntry`
  - fields should cover at least `workflow_name`, `package_name`, `title`, `description`, `aliases`, `package_dir`, `manifest_path`, `workflow_path`, `params_path`, and `doc_path` when present
- `discover_workflow_catalog(root: str | Path) -> tuple[WorkflowCatalogEntry, ...]`
  - shared pure helper for portfolio discovery
- `write_workflow_portfolio_snapshot(ctx, relative_path: str | Path = "workflow_portfolio_snapshot.json") -> Path`
  - additive authoring helper that writes a workflow-local JSON snapshot using the shared catalog seam

Constraints:

- Keep the manifest contract metadata-only; do not add new `workflow.toml` fields in cycle 4.
- Keep `stdlib/` pure authoring support; no runtime-owned routing logic or workflow-specific imports.
- Keep the runtime/provider boundary unchanged: no new runtime-injected prompt metadata beyond `expected_output_schema`, `available_routes`, and `route_contracts`.

### Phase 2: `task_to_workflow_strategy` workflow package

Target files:

- `workflows/task_to_workflow_strategy/__init__.py`
- `workflows/task_to_workflow_strategy/workflow.toml`
- `workflows/task_to_workflow_strategy/params.py`
- `workflows/task_to_workflow_strategy/contracts.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/task_to_workflow_strategy/prompts/*.md`
- `workflows/task_to_workflow_strategy/assets/*`
- `docs/workflows/task_to_workflow_strategy.md`
- `tests/runtime/test_task_to_workflow_strategy.py`

Planned workflow shape:

- system step `bootstrap`
  - writes `invocation_contract.json`
- system step `capture_workflow_portfolio`
  - writes `workflow_portfolio_snapshot.json` via the new helper
- pair step `frame_task`
  - outputs `task_strategy_brief.md` and `workflow_selection_criteria.md`
- pair step `select_strategy`
  - outputs `workflow_candidate_matrix.md`, `workflow_gap_analysis.md`, and `strategy_decision.md`
- pair step `package_strategy`
  - outputs `workflow_strategy_package.md`, `strategy_summary.json`, and `strategy_next_action.md`
- system step `publish_strategy`
  - validates the package and summary, then writes `strategy_receipt.json`

Planned route grammar:

- Reserved:
  - `question`
  - `blocked`
  - `failed`
- Application:
  - `inputs_prepared`
  - `portfolio_snapshotted`
  - `task_framed`
  - `strategy_selected`
  - `strategy_package_ready`
  - `needs_rework`
  - `needs_replan`
  - `strategy_published`

Planned machine-readable payloads:

- `TaskFramingPayload`
- `StrategySelectionPayload`
- `StrategyPackagePayload`

Expected strategy summary fields:

- selected route: `run_existing`, `compose`, `adapt`, or `create_new`
- recommended workflow names and aliases
- authoritative artifacts for the chosen strategy package
- explicit next action
- notes on why the rejected routes lost

Prompt-template requirements:

- Every prompt must explicitly name:
  - role
  - current work item and objective
  - required reads
  - required writes with overwrite/update expectations
  - legal routes
  - evidence requirements
  - in-scope/out-of-scope behavior
  - forbidden actions
- The selection and packaging prompts must explicitly tell the provider to:
  - include the builder in the candidate comparison baseline
  - prefer reuse/composition/adaptation before create-new when the portfolio already fits
  - justify create-new only when the fit gap is real and material

### Phase 3: closeout docs, recursive memory, and validation

Target files:

- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `tests/test_architecture_baseline_docs.py`

Required closeout content:

- cycle-4 decision record showing the builder stayed credible and `task_to_workflow_strategy` was chosen anyway
- cycle-4 framework-gap updates describing the new catalog/snapshot seam and why manifest expansion/runtime routing were not chosen
- roadmap updates that make the front-door strategy workflow part of the standing portfolio baseline
- candidate-ledger updates that record the compared workflow options and the new deferred set after cycle 4
- architecture-baseline test updates so the recursive memory changes are protected

## Compatibility and regression notes

- No CLI syntax change is planned.
- No public manifest-schema change is planned.
- No existing workflow package should change behavior in cycle 4 except where shared discovery logic is factored under the hood.
- Existing builder, evidence-pack, and security-workflow tests remain regression gates because the new workflow depends on the same doctrine and because the catalog seam touches portfolio discovery.
- The front-door workflow must not silently execute or mutate existing workflows; it publishes strategy artifacts only.

## Validation plan

Targeted regression command set:

```bash
.venv/bin/pytest -q \
  tests/unit/test_stdlib_and_extensions.py \
  tests/runtime/test_package_cli.py \
  tests/runtime/test_workflow_builder_package.py \
  tests/runtime/test_investigation_request_to_evidence_pack.py \
  tests/runtime/test_security_finding_to_verified_remediation.py \
  tests/runtime/test_task_to_workflow_strategy.py \
  tests/test_architecture_baseline_docs.py
```

The implementation should also add any new focused unit coverage needed for the shared catalog seam if it is split out of `runtime/loader.py`.

## Risk register

1. Risk: the front-door workflow drifts into automatic runtime routing.
   - Mitigation: keep the terminal contract as published strategy artifacts only; no automatic child execution.
2. Risk: portfolio discovery logic duplicates or diverges from existing workflow discovery.
   - Mitigation: factor shared discovery into one reusable pure seam and have both runtime and authoring helpers use it.
3. Risk: route-specific strategy outputs become inconsistent and hard to validate.
   - Mitigation: normalize the terminal package to `workflow_strategy_package.md`, `strategy_summary.json`, and `strategy_next_action.md` for every selected route.
4. Risk: recursive memory and baseline-doc tests drift from the new cycle-4 portfolio baseline.
   - Mitigation: treat recursive memory and `tests/test_architecture_baseline_docs.py` as part of the same required change set.

## Rollback posture

- If the shared catalog seam proves unstable, roll back to the existing `runtime/loader.py` discovery path and remove the new helper without touching existing workflow packages.
- If the new workflow package is incomplete, do not publish it partially; revert the new package, docs, and tests as one unit.
- Do not broaden rollback into `recursive_autoloop/` wrapper/template cleanup, existing workflow migrations, or manifest-schema changes, because those are explicitly out of scope for cycle 4.
