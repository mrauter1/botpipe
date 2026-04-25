# Authoring

Use the strict root `workflow` shim when authoring workflows:

```python
from workflow import (
    Workflow,
    Context,
    Session,
    Artifact,
    Prompt,
    RouteContract,
    PairStep,
    LLMStep,
    SystemStep,
    SUCCESS,
    PAUSE,
    FAIL,
    GLOBAL,
)
from workflow.primitives import Event, Outcome, Checkpoint, ResolvedArtifacts
```

Keep the root surface strict: do not import engine internals, compiler helpers, or compatibility modules from `workflow`.

## Workflow Shapes

Workflows commonly live under repo-root `workflows/`, but the runtime no longer requires one folder shape.

Supported authoring forms:

- single Python file such as `workflows/release_review.py`
- flow-first package such as `workflows/release_review/flow.py` plus optional `specs.py`
- mature package such as `workflows/release_review/flow.py` or `workflow.py` plus optional `workflow.toml`, `prompts/`, `assets/`, docs, and tests

Recommended serious-workflow shape:

```text
workflows/
  release_review/
    flow.py
    specs.py
```

`flow.py` plus `specs.py` is the recommended serious-workflow shape, but it is not required.

Single-file workflow:

```text
workflows/
  release_review.py
```

Compatible mature package:

```text
workflows/
  release_review/
    __init__.py
    flow.py or workflow.py
    specs.py
    workflow.toml
    prompts/
    assets/
```

`specs.py` is ordinary Python, not a runtime convention. Use it to keep `flow.py` readable when the workflow grows. The runtime does not enforce one folder structure beyond resolving the workflow reference you asked it to run.

When a package uses `__init__.py`, it should re-export the main workflow class:

```python
from .flow import ChildWorkflow

__all__ = ["ChildWorkflow"]
```

Legacy packages may continue to re-export from `.workflow` instead. If the workflow defines workflow-specific parameters, the package may also re-export `Parameters`.

## Workflow Parameters

Top-level CLI runs pass workflow-specific parameters through repeatable `-wf` pairs:

```bash
autoloop run review task-42 \
  --message "Review this implementation" \
  -wf mode strict \
  -wf reviewer security
```

If a workflow supports parameters, expose a `Parameters` model through one of the supported resolution points. Resolution order is:

1. `Workflow.Parameters`
2. module-level `Parameters` in the executable flow module
3. package-exported `Parameters`
4. legacy package conventions such as `params.py`

The runtime validates and coerces `-wf` values through that model before execution starts. `specs.py` is never scanned specially; if you want it involved, import from it explicitly.

## Step Control Contracts

Provider-owned steps may declare narrow machine-readable control contracts directly on `PairStep` and `LLMStep`.

```python
from pydantic import BaseModel


class ReviewPayload(BaseModel):
    summary: str


review = PairStep(
    name="review",
    producer="prompts/review_producer.md",
    verifier="prompts/review_verifier.md",
    expected_output_schema=ReviewPayload,
    route_contracts={
        "review_complete": RouteContract(
            summary="Review artifacts and verdict are complete.",
            required_artifacts=["review_report"],
            work_item_effect="Advances the review package to the next declared step.",
        )
    },
)
```

Runtime behavior:

- `expected_output_schema` defines the JSON-schema-like contract for `Outcome.payload`
- `available_routes` is derived mechanically from the declared workflow transitions plus reserved routes
- `route_contracts` is optional step-owned metadata for legal application routes only
- route contracts normalize to `summary`, `required_artifacts`, and `work_item_effect`
- mapping-style declarations remain valid; legacy `state_effect` values normalize to `work_item_effect`

Authoring rules:

- keep provider-facing operational guidance in the prompt templates, not in runtime-only metadata
- reserve runtime-injected control data for `expected_output_schema`, `available_routes`, and `route_contracts`
- continue using `Outcome.tag` as the route carrier
- use `needs_rework` when the current work-item boundary still holds and `needs_replan` when the boundary changed materially
- do not declare `expected_output_schema` or `route_contracts` on `SystemStep`

## Runtime Config And Provider Selection

Workflow code does not construct providers directly. Operators select the built-in runtime backend through typed config and generic CLI flags.

Typed config lives in `autoloop.yaml` or `autoloop.config` and uses the runtime-owned provider schema:

```yaml
provider:
  name: codex
  model: gpt-5.4
  model_effort: medium
runtime:
  max_steps: 100
```

`provider.name` selects the built-in backend. Generic `provider.model` and `provider.model_effort` overrides target that selected provider.

Public CLI overrides stay generic:

```bash
autoloop run review task-42 \
  --provider claude \
  --model claude-opus \
  --model-effort max \
  --message "Review this implementation"
```

If a workflow or template documents operational usage, keep it on this typed surface. Do not document ad-hoc backend construction or out-of-band provider injection.

Concrete runtime adapters live under `runtime/providers/`, but that package is framework-owned implementation detail. Workflow authors should target the typed runtime config surface and the generic CLI flags rather than importing provider adapters or describing non-public factory hooks.

For `PairStep` verifiers and `LLMStep` prompts, treat the provider-facing completion contract as strict JSON. The runtime now validates verifier and single-LLM outcomes locally, so prompts should ask for one JSON object matching the declared routes and payload contract rather than free-form prose.

## Compact Prompt Contract Style

Keep prompt families explicit without repeating the same boilerplate in every file.

Use `prompts/README.md` once per workflow package for the family-wide contract:

- the shared runtime/provider boundary reminder
- reserved-route baseline and any family-wide route summary
- a compact step-to-artifact map
- verifier payload model names
- family-wide publication-boundary reminders that apply to every prompt in the package

Keep each prompt file focused on the current step:

- step role and purpose
- current work-item boundary
- exact artifacts to read, write, or leave untouched
- step-specific evidence requirements
- step-specific route reminders and forbidden actions

Prompt files should not re-explain family-wide notes when the same wording already lives in `prompts/README.md`.

Prompt-style rules:

- keep provider-facing operational guidance in prompt files, not runtime-only metadata
- keep the runtime-injected contract narrow; the runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`
- The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
- prefer compact artifact tables when they shorten the prompt materially, such as `Artifact | Read/Write | Purpose | Handling`
- keep route guidance concise and local to the decision the current step must justify
- do not restate machine-readable route contracts verbatim when the runtime already injects them
- do not introduce a prompt template engine, shared runtime prompt renderer, or hidden prompt abstraction just to remove repeated prose

`prompts/README.md` is a workflow-local documentation seam, not a runtime input. Shared prompt text belongs there before it belongs in runtime behavior.

## Prompt And Artifact Resolution

Relative prompts and bundled assets resolve from the executable workflow container, never from the current working directory.

```python
Prompt("prompts/ask.md")
Artifact("{run_folder}/request.md")
Artifact("{workflow_folder}/notes.md")
Artifact("{package_folder}/assets/template.txt")
```

`package_folder` means:

- the parent directory of a single-file workflow
- the containing directory of `flow.py`
- the containing directory of `workflow.py`

Available runtime placeholders include:

- `task_folder`
- `workflow_folder`
- `run_folder`
- `package_folder`
- `workflow_name`
- `state.*`

`package_folder` is read-only workflow-adjacent source content. Mutable artifacts must never be written into the workflow source directory.

## Message Model

New runs are message-first:

- `autoloop run ... --message "..."` starts a new run
- `autoloop answer ... --answer "..."` resumes a paused run with an explicit answer

`message` and `answer` are distinct concepts. Resume and diagnostics do not accept a replacement message.

## Sessions And Resumability

The runtime persists resumability through an opaque `session_id` plus optional `provider_metadata`. Workflow code should treat session continuity as opaque runtime state and use the `Session` / context APIs rather than depending on persisted payload details.

Implications for authors:

- do not assume provider-specific naming for the continuation handle
- do not read or write session JSON directly from workflow logic
- keep provider-specific behavior inside provider adapters or provider-specific prompts, not workflow contracts
- do not document or depend on any legacy provider-specific continuation alias outside the canonical `session_id` contract

## Optional Lifecycle Helpers

`stdlib/lifecycle.py` provides a small opt-in helper seam for deterministic authoring tasks such as opening declared sessions and writing workflow-local JSON artifacts like invocation contracts and publication receipts.

```python
from autoloop_v3.stdlib import (
    open_workflow_sessions,
    write_invocation_contract,
    write_publication_receipt,
)
```

Use it only as authoring support inside explicit workflow hooks such as `on_bootstrap(...)` or `on_publish_* (...)`.

- these helpers do not create hidden runtime sequencing or automatic system steps
- they only operate on the workflow-owned `ctx` surface and `ctx.workflow_folder`
- they do not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- publication-artifact validation and any workflow-specific receipt semantics still belong in workflow code

## Optional Validation Helpers

`stdlib/validation.py` provides a small opt-in helper seam for generic workflow-local JSON, string, list, mapping, non-negative-int, and positive-int validation.

```python
from autoloop_v3.stdlib import (
    normalize_optional_string,
    normalize_unique_strings,
    read_json_object,
    require_mapping,
    require_mapping_list,
    require_non_negative_int,
    require_non_empty_string,
    require_positive_int,
    require_string_list,
)
```

Validation helper boundary:

- generic validation belongs in stdlib rather than copied workflow-local helper tails
- use these helpers for shared JSON-object reads, non-empty string checks, string-list normalization, mapping checks, duplicate guards, non-negative-int validation, and positive-int validation
- use the selected-workflow snapshot validators in the same module when multiple workflows need the same capability, authoring-surface, decomposition-surface, or cross-artifact selected-workflow-name checks
  - `validate_selected_workflow_artifact_alignment(...)` handles top-level `selected_workflow_name` alignment across artifacts
  - `validate_selected_workflow_capability_and_authoring_snapshots(...)` validates the paired capability and authoring surfaces without repeating local cross-check code
- keep workflow-specific publication assertions, domain allow-lists, and artifact-family invariants in workflow code
- the helpers only validate explicit workflow-local inputs and artifacts; they do not add runtime-owned routing, publication policy, or hidden execution

For workflow `Parameters` models, reuse the shared Pydantic validator factories instead of copying the same `field_validator(...)` bodies into every `params.py`.

```python
from autoloop_v3.stdlib import (
    deduped_string_list_fields,
    optional_text_fields,
    positive_int_fields,
    required_text_fields,
)


class Parameters(BaseModel):
    task_title: str
    selected_workflow: str
    sponsor_role: str | None = None
    constraints: list[str] = Field(default_factory=list)
    max_runs: int = 25

    _required_text = required_text_fields(
        "task_title",
        "selected_workflow",
        error_message="value must be non-empty",
    )
    _optional_text = optional_text_fields("sponsor_role")
    _repeatable_strings = deduped_string_list_fields("constraints")
    _positive_int = positive_int_fields("max_runs", error_message="max_runs must be a positive integer")
```

Parameter-model helper boundary:

- generic `params.py` mechanics belong in stdlib rather than repeated local `field_validator(...)` loops
- keep field lists explicit in the `Parameters` model so required, optional, repeatable, and bounded fields stay easy to read
- keep workflow-specific identifier rules, literal pre-normalization, and order-sensitive output local when the shared seam would hide intent
- these helpers do not change runtime-owned parameter coercion; `runtime/loader.py` still owns workflow-parameter validation and error surfacing

## Optional Portfolio Snapshot Helpers

`stdlib/portfolio.py` provides a small opt-in helper seam for portfolio-routing workflows that need an inspectable snapshot of the current workflow library.

```python
from autoloop_v3.stdlib import (
    write_workflow_portfolio_health_snapshot,
    write_workflow_portfolio_snapshot,
)

write_workflow_portfolio_snapshot(ctx)
write_workflow_portfolio_health_snapshot(ctx, statuses=["paused", "failed"], max_runs_per_workflow=5)
```

Portfolio snapshot boundary:

- the helper writes `workflow_portfolio_snapshot.json` under `ctx.workflow_folder` by default
- it uses the shared workflow catalog seam to capture manifest metadata plus inferred source paths such as `flow.py`, `workflow.py`, top-level single-file workflows, optional `specs.py`, prompts, assets, docs, and tests when present
- it does not add new `workflow.toml` fields and preserves the metadata-only manifest doctrine
- it does not auto-rank, auto-select, auto-adapt, or auto-run workflows
- it does not import runtime-owned routing behavior into workflow packages; portfolio-routing workflows still own ranking, selection, adaptation, create-new policy, and prompt semantics

Portfolio health snapshot boundary:

- `write_workflow_portfolio_health_snapshot` writes `workflow_portfolio_health_snapshot.json` under `ctx.workflow_folder` by default
- it reuses the shared workflow resolution and read-only run discovery seams to publish grouped per-workflow run counts, status counts, and recent-run excerpts
- it supports deterministic status filtering and `max_runs_per_workflow` bounds
- it does not mutate `.autoloop` run state or workflow packages
- it keeps the health surface lightweight: identifying workflow metadata, normalized recent-run excerpts, and summary counts rather than full event logs or runtime-owned lifecycle scoring
- it does not add CLI flags, new `workflow.toml` fields, runtime-owned governance scoring, automatic recommendations, or hidden downstream execution
- workflow code and prompt templates still own governance framing, lifecycle interpretation, recommendation policy, publication gating, and any downstream follow-through
- it does not auto-rank workflows, auto-select actions, auto-cluster failure modes, or impose runtime-owned portfolio policy

## Optional Company Operation Snapshot Helpers

`stdlib/company.py` provides a narrow authoring-only seam for workflows that need one bounded snapshot of repo-local company operation history.

```python
from autoloop_v3.stdlib import write_company_operation_snapshot

write_company_operation_snapshot(
    ctx,
    task_ids=("recursive-framework-evolution-20260423t173132-c12",),
    workflows=("workflow_portfolio_to_operating_system", "workflow_idea_to_workflow_package"),
    statuses=("success", "paused"),
    max_tasks=10,
    max_runs_per_workflow=5,
    max_messages_per_task=3,
)
```

Company operation snapshot boundary:

- `write_company_operation_snapshot` writes `company_operation_snapshot.json` under `ctx.workflow_folder` by default
- it captures repo-local `.autoloop` task history plus read-only workflow telemetry; it is not an external business-system integration seam
- it publishes bounded task summaries, recent message excerpts, per-task workflow telemetry, and authoritative source paths
- it supports deterministic `task_ids`, workflow, and status filtering plus `max_tasks`, `max_runs_per_workflow`, and `max_messages_per_task` bounds
- it writes only workflow-local JSON artifacts under `ctx.workflow_folder`
- it does not mutate `.autoloop` task or run state, workflow packages, or external business systems
- it does not add CLI flags, runtime-owned company scoring, automatic prioritization, or hidden downstream execution
- it does not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- workflow code and prompt templates still own company framing, recursive-improvement analysis, prioritization policy, publication gating, and next-cycle recommendations
- it does not auto-rank tasks, auto-select improvements, auto-run downstream workflows, or imply external CRM, incident, or ticketing integration

## Optional Selected-Workflow Adaptation Helpers

`stdlib/adaptation.py` provides a small additive seam for workflows that need to inspect one already-selected workflow and publish a validated parameter artifact for that choice.

```python
from autoloop_v3.stdlib import (
    write_selected_workflow_capability_snapshot,
    write_validated_workflow_parameters,
)

write_selected_workflow_capability_snapshot(ctx, "release_candidate_to_go_no_go")
write_validated_workflow_parameters(
    ctx,
    "release_candidate_to_go_no_go",
    {"mode": "strict", "reviewers": ["ops", "qa"]},
)
```

Adaptation helper boundary:

- the helpers write only workflow-local JSON artifacts under `ctx.workflow_folder`
- they reuse the existing workflow discovery, resolution, and parameter coercion seams instead of re-implementing schema logic
- they accept the same workflow references the shared loader resolves, including canonical names, aliases, and main workflow classes
- they are authoring-only support for explicit workflow code; they do not add CLI syntax, manifest fields, runtime-owned adaptation, or automatic downstream execution
- they do not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- portfolio-routing workflows still own ranking, selection, adaptation, create-new policy, and prompt semantics in workflow code and prompt templates
- the helper does not import runtime-owned routing behavior into workflow packages; it only writes a workflow-local artifact

## Optional Refinement Surface Helpers

`stdlib/refinement.py` provides a narrow authoring-only seam for workflows that need a workflow-local snapshot of one selected workflow's editable authoring surface.

```python
from autoloop_v3.stdlib import write_selected_workflow_authoring_surface

write_selected_workflow_authoring_surface(ctx, "release_candidate_to_go_no_go")
```

Refinement helper boundary:

- the helper writes only workflow-local JSON artifacts under `ctx.workflow_folder`
- it reuses the shared workflow resolution and catalog seams instead of ad hoc repo scraping or `workflow.toml` expansion
- it writes the authoritative selected-workflow authoring-surface payload built in `core/workflow_capabilities.py`, so later helpers and workflows consume one canonical editable-surface shape
- it keeps the compiled selected-workflow contract separate from the editable selected-workflow surface; workflows that need both should call `write_selected_workflow_capability_snapshot(...)` and `write_selected_workflow_authoring_surface(...)` explicitly
- it captures the selected workflow's primary source file (`flow.py`, `workflow.py`, or a single-file workflow), optional `__init__.py`, optional `workflow.toml`, optional `specs.py`, optional legacy support files such as `params.py` and `contracts.py`, prompt files, asset files, linked workflow doc paths, and inferred test paths when present
- it writes the canonical result to `selected_workflow_authoring_surface.json` by default
- it does not mutate, auto-run, auto-adapt, auto-refine, or auto-promote the selected workflow
- it does not add CLI flags, new `workflow.toml` fields, or runtime-owned refinement automation
- it does not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- prompt templates and workflow code still own refinement policy, baseline/candidate strategy, file copying, verification evidence, and promotion/rollback decisions

## Optional Decomposition Surface Helpers

`stdlib/decomposition.py` provides a narrow authoring-only seam for workflows that need one additive, read-only artifact combining a selected workflow's identity, editable authoring surface, and compiled step/route topology.

```python
from autoloop_v3.stdlib import write_selected_workflow_decomposition_surface

write_selected_workflow_decomposition_surface(ctx, "release_candidate_to_go_no_go")
```

Decomposition helper boundary:

- the helper writes only workflow-local JSON artifacts under `ctx.workflow_folder`
- it is additive and read-only: it snapshots existing workflow/compiler data and does not mutate selected workflow files
- it reuses the shared workflow resolution, catalog, and compiler seams instead of ad hoc repo scraping or `workflow.toml` expansion
- it writes the authoritative selected-workflow decomposition payload built in `core/workflow_capabilities.py`, so authoring-surface and compiled-surface fields stay synchronized across decomposition consumers
- it combines selected workflow identity, editable authoring surface paths, repo-root-relative path metadata, and compiled step/route topology in one artifact
- it captures the selected workflow's primary source file (`flow.py`, `workflow.py`, or a single-file workflow), optional `__init__.py`, optional `workflow.toml`, optional `specs.py`, optional legacy support files such as `params.py` and `contracts.py`, prompt files, asset files, linked workflow doc paths, and inferred test paths when present
- compiled step summaries include session names, required/provided/log artifacts, available routes, route contracts, local route targets, and package-relative plus repo-relative prompt paths
- it writes the canonical result to `selected_workflow_decomposition_surface.json` by default
- it does not mutate, auto-decompose, auto-run, auto-adapt, auto-refine, or auto-promote the selected workflow
- it does not add CLI flags, new `workflow.toml` fields, runtime-owned decomposition automation, or hidden downstream routing
- it does not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- workflow code and prompt templates still own decomposition policy, baseline/candidate strategy, building-block extraction boundaries, verification evidence, and promotion/rollback decisions

## Optional Candidate-Surface Publication Helpers

`stdlib/candidate_surfaces.py` provides a narrow authoring-only seam for workflows that need the repeated mechanical parts of candidate-only publication for one selected workflow surface.

```python
from autoloop_v3.stdlib import (
    derive_candidate_surface_manifest,
    materialize_baseline_surface,
    normalize_candidate_surface_overlay_result,
    normalize_candidate_surface_boundary,
    validate_baseline_surface_manifest,
    validate_authoritative_surface_sources_unchanged,
    validate_candidate_surface_manifest,
    validate_candidate_surface_overlay,
)
```

Candidate-surface helper boundary:

- the helpers own only the mechanical baseline/candidate publication operations: repo-relative boundary normalization, baseline surface materialization, candidate-manifest diff derivation, baseline/candidate manifest validation, authoritative-source drift rejection, isolated overlay validation, and overlay-result normalization
- they reuse the shared selected-workflow surface artifacts and repo-relative path hardening instead of ad hoc workflow-local copy, digest, and traversal checks
- manifest validators cover shared mechanics such as `repo_root` and `surface_kind` alignment, boundary-field comparison, `relative_paths` versus `files` consistency, copied-surface digest checks, and caller-supplied added-path allow-lists
- callers still own workflow-specific boundary policy, optional boundary-field wiring, domain-specific error wording, and any post-validation receipt semantics
- they write only workflow-local surface folders and manifest metadata under `ctx.workflow_folder`
- overlay validation still runs against an isolated repo copy with the same runnable-root fallback used by the workflow-local publication path
- overlay-result normalization only validates the mechanical compile/test receipt shape, including whether the caller expects one compiled workflow or many
- they do not own refinement-specific evaluation alignment, decomposition-specific evidence capture, building-block extraction policy, or publication receipt shaping
- they do not mutate, auto-promote, auto-decompose, auto-refine, or auto-run the selected workflow
- they do not add CLI flags, new `workflow.toml` fields, runtime-owned publication automation, or hidden downstream routing
- they do not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- workflow code and prompt templates still own domain-specific publication policy, evidence requirements, allowed-path rules, and promotion or rollback decisions

## Optional Diagnostic Snapshot Helpers

`stdlib/diagnostics.py` provides a narrow authoring-only seam for workflows that need a workflow-local snapshot of one selected workflow's historical run evidence.

```python
from autoloop_v3.stdlib import write_selected_workflow_run_history_snapshot

write_selected_workflow_run_history_snapshot(
    ctx,
    "release_candidate_to_go_no_go",
    statuses=("failed", "paused"),
    max_runs=25,
)
```

Diagnostic helper boundary:

- the helper writes only workflow-local JSON artifacts under `ctx.workflow_folder`
- it reuses the shared workflow resolution and read-only run discovery seams instead of ad hoc `.autoloop` scraping
- it captures normalized run metadata, request text, parsed `events.jsonl` entries, parsed `children.jsonl` entries, parsed `parent.json` metadata when present, and authoritative source paths
- it supports deterministic status filtering and `max_runs` bounds while keeping the selected history set explicit in `selected_workflow_run_history.json`
- it does not mutate `.autoloop` run state or selected workflow files
- it does not add CLI flags, new `workflow.toml` fields, runtime-owned diagnostics automation, or hidden downstream routing
- it does not auto-cluster failure modes, auto-rank severity, or impose runtime-owned failure-mode policy
- it does not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- workflow code and prompt templates still own diagnostic framing, failure-mode clustering, severity ranking, publication gating, and next-action recommendations

## Optional Evaluation Manifest Helpers

`stdlib/evaluation.py` provides a narrow authoring-only seam for workflows that need to validate and canonicalize one workflow-local evaluation case manifest against one selected workflow.

```python
from autoloop_v3.stdlib import write_validated_eval_case_manifest

write_validated_eval_case_manifest(
    ctx,
    "release_candidate_to_go_no_go",
    {
        "cases": [
            {
                "case_id": "baseline_release_readiness",
                "case_kind": "benchmark",
                "prompt": "Assess a routine release candidate with complete evidence.",
                "workflow_parameters": {"mode": "strict"},
                "expected_artifacts": ["assessment_note"],
            }
        ]
    },
)
```

Evaluation helper boundary:

- the helper writes only workflow-local JSON artifacts under `ctx.workflow_folder`
- it refreshes `selected_workflow_capability.json` through `write_selected_workflow_capability_snapshot(...)` instead of duplicating selected-workflow inspection logic
- it validates per-case workflow parameters through the shared loader coercion path instead of re-implementing parameter schema logic
- it validates unique case ids, legal case kinds (`benchmark`, `edge`, `adversarial`), non-empty case prompts, and non-empty expected artifacts
- it validates expected artifacts against the selected workflow's compiled artifact surface derived from the selected-workflow capability snapshot
- it writes the canonical result to `validated_eval_case_manifest.json` by default
- it does not add CLI flags, new `workflow.toml` fields, runtime-owned evaluation execution, or hidden downstream routing
- it does not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- workflows still own evaluation policy, category coverage requirements, prompt semantics, publication gating, and any downstream execution behavior in workflow code and prompt templates

## Optional Workflow Capability Snapshot Helpers

`stdlib/portfolio.py` also provides an opt-in helper for portfolio workflows that need richer importing inspection of workflow parameters and compiled step contracts while keeping the lightweight catalog seam unchanged.

```python
from autoloop_v3.stdlib import write_workflow_capability_snapshot

write_workflow_capability_snapshot(ctx)
```

Capability snapshot boundary:

- the helper writes `workflow_capability_snapshot.json` under `ctx.workflow_folder` by default
- it uses the separate capability-inspection seam to capture catalog metadata plus normalized workflow parameters and compiled step summaries
- compiled step summaries include the declared artifact surface, available routes, route contracts, prompt paths, and whether a typed output schema exists
- it does not add new `workflow.toml` fields and does not change the lightweight non-importing catalog discovery contract
- it reuses only the existing narrow runtime-injected control metadata: `expected_output_schema`, `available_routes`, and `route_contracts`
- it does not auto-rank, auto-select, auto-adapt, or auto-run workflows
- portfolio workflows still own comparison policy, fit-gap reasoning, adaptation policy, and downstream routing in workflow code and prompt templates

## Workflow Composition

Runtime-backed contexts can invoke child workflows by package name or imported main class:

```python
from workflows.child_workflow import ChildWorkflow

result = ctx.invoke_workflow(
    ChildWorkflow,
    message="Do the child task",
    parameters={"mode": "strict"},
)
```

```python
result = ctx.invoke_workflow(
    "child_workflow",
    message="Do the child task",
    parameters={"mode": "strict"},
)
```

Child workflows run as normal workflow packages with their own run ids and run-local artifacts. They are reusable building blocks, not a special execution mode.

For optional authoring-level composition helpers, `stdlib/composition.py` keeps the same runtime semantics while making artifact adoption explicit in workflow code:

```python
from autoloop_v3.stdlib import (
    adopt_child_artifacts,
    require_child_workflow_result,
    run_child_workflow,
)

child = run_child_workflow(
    ctx,
    "child_workflow",
    message="Do the child task",
    parameters={"mode": "strict"},
)
require_child_workflow_result(
    child,
    status="success",
    last_event="evidence_pack_published",
    required_artifacts=("evidence_pack",),
)
adopted = adopt_child_artifacts(
    ctx,
    child,
    mapping={"evidence_pack": "adopted/evidence_pack.md"},
)
```

Composition helper boundary:

- `run_child_workflow(...)` is a thin authoring wrapper over `ctx.invoke_workflow(...)`
- `require_child_workflow_result(...)` validates the expected child status, terminal route, and required artifacts before parent-local adoption
- `adopt_child_artifacts(...)` copies explicitly named child artifacts into `ctx.workflow_folder`
- these helpers do not create hidden runtime sequencing, automatic system steps, or new child-run metadata
- they do not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- parent workflows still own explicit `question` and `blocked` routing for child runs; the validation helper does not propagate or translate those routes automatically
- parent workflows still own which child artifacts are adopted, where they land, and whether overwriting those parent-local files is acceptable

## Recursive And Workflow-Reference Guidance

If a workflow, template, or recursive harness emits Autoloop instructions, keep them workflow-reference-aware and repo-layout-accurate:

- `autoloop run <workflow> <task-id> --root ... --message ...`
- `autoloop resume <workflow> <task-id> --root ...`
- `autoloop answer <workflow> <task-id> --root ... --answer ...`
- explicit file or module refs are allowed when the operator needs them, but recursive wrappers should keep their stable name-first contract unless they have a reason to pin an origin directly
- refer readers to `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `extensions/`, `stdlib/`, `workflows/`, and `.autoloop_recursive/`
