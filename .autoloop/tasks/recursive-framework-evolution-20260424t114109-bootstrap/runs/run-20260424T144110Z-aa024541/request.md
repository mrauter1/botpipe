Below is a standalone implementation plan written for an agentic coding agent. It updates the prior plan around your new authoring goal: **flow-first, optional specs/docs, no enforced folder structure, single-file allowed, recommended two-file shape, full package allowed for mature workflows**. The current repo still documents a strict root `workflow` shim and a required package layout with `workflow.py`, `workflow.toml`, `prompts/`, and `assets/`, so this plan intentionally changes that package contract while preserving the strict root authoring surface and metadata-only manifest principle.  

---

# Autoloop Framework Improvement Plan: Flow-First Flexible Workflow Authoring

## 1. Mission

Improve the Autoloop V3 framework so workflow authoring is:

* easy to read,
* easy to understand,
* easy to reason about,
* uncluttered,
* flexible,
* powerful,
* not tied to a prescribed folder structure.

The workflow flow definition should be the primary human-readable orchestration surface. Specs, schemas, docs, prompts, assets, tests, manifests, and helper surfaces are allowed, but they must be optional. The recommended serious-workflow shape should be two Python files:

```text
flow.py
specs.py
```

But this is a recommendation only. Authors must also be free to keep everything in one script.

The framework should support three authoring forms:

```text
# Form A: single-file workflow
my_workflow.py

# Form B: recommended serious workflow
my_workflow/
  flow.py
  specs.py

# Form C: mature workflow package
my_workflow/
  flow.py or workflow.py
  specs.py
  workflow.toml
  prompts/
  assets/
  docs.md
  tests/
```

Existing package workflows using `workflow.py`, `params.py`, `contracts.py`, `prompts/`, `assets/`, and `workflow.toml` must continue to work. The new system should make that shape optional rather than mandatory.

---

## 2. Architectural North Star

Autoloop should support this authoring experience:

```python
# flow.py

from workflow import Workflow, Session, Artifact, PairStep, SystemStep, SUCCESS, PAUSE, FAIL, GLOBAL
from workflow.primitives import Event, Outcome

from .specs import ReviewPayload, review_contracts


class ReleaseReview(Workflow):
    class State(ReviewPayload.State):
        pass

    review_session = Session()

    request = Artifact("{task_folder}/request.md")
    review_report = Artifact("{workflow_folder}/review_report.md")

    review = PairStep(
        name="review",
        session=review_session,
        producer="prompts/review_producer.md",
        verifier="prompts/review_verifier.md",
        requires=[request],
        produces={"review_report": review_report},
        expected_output_schema=ReviewPayload,
        route_contracts=review_contracts(),
    )

    publish = SystemStep(name="publish")

    entry = review

    transitions = {
        GLOBAL: {
            "question": PAUSE,
            "blocked": PAUSE,
            "failed": FAIL,
        },
        review: {
            "review_complete": publish,
            "needs_rework": review,
        },
        publish: {
            "published": SUCCESS,
        },
    }

    def on_start(self, ctx):
        ctx.open_session(self.review_session)

    @staticmethod
    def on_publish(state, ctx):
        return state, Event("published")
```

The flow file should primarily show:

* state,
* sessions,
* artifacts,
* steps,
* transitions,
* small handlers.

Large schemas, reusable route contracts, validation logic, helper artifact schemas, publication receipts, and docs should live elsewhere if the author chooses.

---

## 3. Non-Negotiable Invariants

Preserve these invariants:

1. The root `workflow` shim remains strict and minimal.
2. Do not expose `Engine`, `compile_workflow`, runtime internals, provider internals, compiler internals, or compatibility aliases from the root `workflow` package.
3. `workflow.toml`, when present, remains metadata-only.
4. `workflow.toml` must not define topology, transitions, prompts, sessions, parameters, artifact semantics, route policy, or execution logic.
5. Specs/docs/prompts/assets/tests/manifests are optional.
6. A workflow must be runnable from a single Python file.
7. A workflow must be runnable from a package directory with `flow.py`.
8. Existing `workflow.py` package workflows remain supported.
9. `specs.py` is a recommendation, not a runtime convention.
10. The runtime must not require `contracts.py`, `params.py`, `specs.py`, `prompts/`, `assets/`, docs, tests, or `workflow.toml`.
11. Shallow discovery must not import workflow modules.
12. Deep inspection and execution may import workflow modules.
13. Public CLI should remain package/message oriented, but workflow references may point to names, modules, or files.
14. Existing package-based CLI workflows must continue to work.
15. Existing child workflow composition through `ctx.invoke_workflow(...)` and stdlib composition helpers must continue to work.
16. Do not introduce a large new workflow DSL.
17. Do not move workflow-specific policy into runtime-owned hidden automation.
18. Do not make helper-surface artifacts mandatory for normal workflow authoring.

---

## 4. Target Authoring Forms

### 4.1 Single-file workflow

Supported:

```text
workflows/release_review.py
```

or anywhere by explicit path:

```text
examples/release_review.py
```

The file may contain everything:

```python
from pydantic import BaseModel
from workflow import Workflow, LLMStep, SUCCESS


class ReleasePayload(BaseModel):
    summary: str


class ReleaseReview(Workflow):
    class State(BaseModel):
        summary: str = ""

    ask = LLMStep(
        name="ask",
        producer="prompts/review.md",
        expected_output_schema=ReleasePayload,
    )

    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    @staticmethod
    def on_ask(state, outcome, artifacts):
        return state.model_copy(update={"summary": outcome.payload["summary"]})
```

No manifest required. No package required. No specs file required.

### 4.2 Recommended two-file workflow

Supported and recommended for serious workflows:

```text
workflows/release_review/
  flow.py
  specs.py
```

`flow.py` owns topology and execution.

`specs.py` owns optional supporting declarations:

* Pydantic payload models,
* parameters model,
* route-contract builders,
* artifact validation helpers,
* publication schemas,
* documentation metadata if desired.

The runtime must not special-case `specs.py`. It is just Python imported by the author.

### 4.3 Full mature workflow package

Supported:

```text
workflows/release_review/
  __init__.py
  flow.py
  specs.py
  workflow.toml
  prompts/
  assets/
  docs.md
  tests/
```

Also supported for compatibility with current repo style:

```text
workflows/release_review/
  __init__.py
  workflow.py
  params.py
  contracts.py
  workflow.toml
  prompts/
  assets/
```

This remains a supported mature package shape, not the mandatory minimum.

---

## 5. Workflow Reference Model

Implement a unified `WorkflowReference` resolution model.

A workflow reference may be:

```text
release_review
release_review:ReleaseReview
workflows/release_review.py
workflows/release_review.py:ReleaseReview
workflows/release_review/flow.py
workflows/release_review/flow.py:ReleaseReview
workflows.release_review.flow:ReleaseReview
```

The CLI should continue to look like:

```bash
autoloop run <workflow-ref> <task-id> --message "..."
```

Examples:

```bash
autoloop run release_review task-1 --message "Review this release"
autoloop run workflows/release_review.py task-1 --message "Review this release"
autoloop run workflows/release_review/flow.py:ReleaseReview task-1 --message "Review this release"
```

This should not be implemented as a legacy raw execution mode. It should be a unified workflow-reference resolver that always resolves to a `Workflow` subclass and then runs through the same engine/runtime path.

---

## 6. Loader and Discovery Changes

### 6.1 Add internal `WorkflowReference` model

Add an internal representation with fields like:

```python
@dataclass(frozen=True)
class WorkflowReference:
    original: str
    kind: Literal["catalog_name", "python_file", "python_module", "workflow_class"]
    workflow_name: str
    workflow_class: type[Workflow] | None
    class_name: str | None
    module_name: str | None
    source_path: Path | None
    package_folder: Path
    manifest_path: Path | None
    metadata: WorkflowMetadata
    authoring_shape: Literal["single_file", "flow_package", "workflow_package", "manifest_package", "unknown"]
```

This is internal. Do not expose it through the root `workflow` shim.

### 6.2 Resolve named workflows

For `autoloop run release_review ...`:

1. First check manifest-based catalog entries under `<root>/workflows/*/workflow.toml`.
2. Then check inferred package/file candidates:

   * `<root>/workflows/release_review/flow.py`
   * `<root>/workflows/release_review/workflow.py`
   * `<root>/workflows/release_review.py`
3. Import only during execution or deep inspection.
4. If multiple candidates conflict, fail with a clear ambiguity error.

### 6.3 Resolve file workflows

For explicit file references:

```bash
autoloop run path/to/my_workflow.py task-1 --message "..."
```

Rules:

* path must exist;
* path must end in `.py`;
* import the file in an isolated module namespace;
* locate exactly one `Workflow` subclass unless `:ClassName` is specified;
* if multiple workflow classes exist and no class name is specified, raise a clear error;
* package folder should default to the file’s parent directory;
* workflow name should default to:

  1. class attribute `name`, if present;
  2. manifest name, if adjacent manifest exists;
  3. snake-case class name;
  4. sanitized file stem.

### 6.4 Resolve package workflows

For package directories:

* prefer `flow.py`;
* fallback to `workflow.py`;
* support `__init__.py` re-export if present;
* do not require `__init__.py` for explicit path execution;
* do require `__init__.py` only if executing/importing as a normal Python package.

### 6.5 Shallow discovery

Shallow discovery should not import workflow modules.

It should scan:

```text
<root>/workflows/*/workflow.toml
<root>/workflows/*/flow.py
<root>/workflows/*/workflow.py
<root>/workflows/*.py
```

For manifest entries, use manifest metadata.

For inferred entries without manifest, expose minimal inferred metadata:

```json
{
  "workflow_name": "release_review",
  "title": "Release Review",
  "description": null,
  "aliases": [],
  "manifest_path": null,
  "flow_path": "...",
  "authoring_shape": "single_file"
}
```

### 6.6 Deep inspection

Deep inspection may import/compile workflows and should report:

* workflow class,
* state model,
* parameters model if present,
* steps,
* artifacts,
* sessions,
* transitions,
* route contracts,
* expected output schemas,
* prompt paths,
* source path,
* package folder,
* manifest path if present,
* inferred spec/doc/prompt/asset/test paths if present.

---

## 7. Parameter Model Resolution

Current workflows may export parameters from `params.py` or package `__init__.py`. New flexible workflows need a more general rule.

Resolution order:

1. `WorkflowClass.Parameters`, if present.
2. Module-level `Parameters` in the flow module.
3. Package-level exported `Parameters`, if running a package.
4. Existing package convention, if applicable.
5. No parameters.

Do not special-case `specs.py`. If `flow.py` imports `Parameters` from `specs.py`, then option 2 may work because the symbol is present in the flow module. If not, the workflow class can explicitly reference it.

Example:

```python
# specs.py
class Parameters(BaseModel):
    mode: str = "strict"

# flow.py
from .specs import Parameters

class ReviewWorkflow(Workflow):
    Parameters = Parameters
```

or:

```python
class ReviewWorkflow(Workflow):
    class Parameters(BaseModel):
        mode: str = "strict"
```

---

## 8. Prompt Resolution

Prompt paths should resolve relative to `package_folder`.

For each authoring form:

| Shape                 | `package_folder`   |
| --------------------- | ------------------ |
| single file `foo.py`  | `foo.py` parent    |
| package `flow.py`     | package directory  |
| package `workflow.py` | package directory  |
| imported module       | module file parent |
| manifest package      | package directory  |

This allows:

```python
LLMStep(name="ask", producer="prompts/ask.md")
```

to work whether the workflow is single-file or package-based, as long as `prompts/ask.md` exists next to the flow file/package.

Also allow inline prompt text through existing `Prompt` support if the framework already supports it. Do not require a `prompts/` folder.

---

## 9. Specs and Validation Strategy

### 9.1 Do not make `specs.py` magical

`specs.py` is a recommended convention only.

The runtime must not require it, scan it, or treat it as an implicit schema registry.

### 9.2 Add reusable validation helpers

The current workflows are verbose around schema and JSON validation. The fix should not be a large runtime DSL. Add small reusable helpers under stdlib, for example:

```text
stdlib/validation.py
stdlib/json_artifacts.py
stdlib/contracts.py
```

Potential API:

```python
from autoloop_v3.stdlib.validation import (
    ValidationIssue,
    ValidationReport,
    require_non_empty_string,
    require_string_list,
    require_unique_values,
    validate_model_file,
    read_model_file,
    write_model_file,
)
```

Support:

```python
model = read_model_file(path, MyModel)
write_model_file(ctx, "reports/result.json", result_model)
report = validate_model_file(path, MyModel)
```

### 9.3 Keep flow file uncluttered

A good flow file should import validation or route helpers, not define pages of validation logic inline.

Example:

```python
from .specs import ReviewPayload, review_contracts, publish_review_receipt
```

Then in handler:

```python
@staticmethod
def on_publish(state, ctx):
    publish_review_receipt(ctx, state)
    return state, Event("published")
```

### 9.4 Do not add root `JsonArtifact` yet

Do not add `JsonArtifact` or `MarkdownArtifact` to the root `workflow` shim in this cycle.

If typed artifact helpers are desired, put them under stdlib and keep them optional:

```python
from autoloop_v3.stdlib.json_artifacts import JsonArtifactSpec
```

But the core `Artifact` primitive should remain simple.

---

## 10. Route Contract Helpers

Add pure helper functions for common route-contract patterns.

Example module:

```text
stdlib/contracts.py
```

Example API:

```python
def review_gate_contracts(
    *,
    complete: str = "review_complete",
    rework: str = "needs_rework",
    required_artifacts: tuple[str, ...] = (),
) -> dict[str, RouteContract]:
    ...
```

Usage:

```python
review = PairStep(
    ...,
    route_contracts=review_gate_contracts(
        complete="review_complete",
        rework="needs_rework",
        required_artifacts=("review_report",),
    ),
)
```

Constraints:

* helpers return normal `RouteContract` dictionaries;
* transitions remain explicit in the flow file;
* do not introduce route objects as the main DSL;
* do not hide routes;
* do not mutate runtime behavior.

---

## 11. Catalog and Capability Surface Changes

Update `core.workflow_catalog`, `core.workflow_capabilities`, and related stdlib helpers to support flexible authoring shapes.

Catalog entries should avoid assuming fixed files like `params.py` or `contracts.py`.

Use more general optional fields:

```json
{
  "workflow_name": "release_review",
  "authoring_shape": "flow_package",
  "source_path": "workflows/release_review/flow.py",
  "package_dir": "workflows/release_review",
  "manifest_path": "workflows/release_review/workflow.toml",
  "flow_path": "workflows/release_review/flow.py",
  "legacy_workflow_path": null,
  "spec_paths": ["workflows/release_review/specs.py"],
  "prompt_paths": ["workflows/release_review/prompts/review_producer.md"],
  "asset_paths": [],
  "doc_paths": [],
  "test_paths": []
}
```

If no specs/docs/prompts/assets/tests exist, use empty lists or nulls. Do not treat absence as an error.

Deep capability inspection should compile the workflow and include the actual compiled contract.

---

## 12. CLI Changes

### 12.1 Update `run`

Current style remains supported:

```bash
autoloop run release_review task-1 --message "..."
```

Add support for file/module/class workflow references:

```bash
autoloop run workflows/release_review.py task-1 --message "..."
autoloop run workflows/release_review.py:ReleaseReview task-1 --message "..."
autoloop run workflows.release_review.flow:ReleaseReview task-1 --message "..."
```

### 12.2 Update `workflows list`

List both manifest workflows and inferred workflows.

Fields:

* name,
* title,
* authoring shape,
* manifest present yes/no,
* source path,
* aliases if any.

Do not import modules during list.

### 12.3 Update `workflows show`

For shallow show, use metadata only when possible.

For deep show, add a flag such as:

```bash
autoloop workflows show release_review --deep
```

or reuse existing behavior if deep inspection already exists.

Deep show may import/compile.

### 12.4 Do not bring back legacy CLI terms

Do not restore:

* `--intent`,
* raw legacy targets,
* provider factory flags,
* old compatibility mode,
* public provider-factory env vars,
* legacy `thread_id`.

---

## 13. Workspace Identity and Run Layout

For named workflows, preserve current workspace behavior.

For file/module workflows, derive stable workflow identity:

1. `Workflow.name` if present.
2. Manifest `name` if present.
3. Workflow class name converted to snake case.
4. File stem fallback.

Persist run metadata with enough origin information:

```json
{
  "workflow": {
    "name": "release_review",
    "reference": "workflows/release_review.py:ReleaseReview",
    "source_path": "workflows/release_review.py",
    "class_name": "ReleaseReview",
    "authoring_shape": "single_file",
    "manifest_path": null
  }
}
```

This prevents single-file workflows from becoming opaque in run history.

---

## 14. Documentation Changes

Update:

```text
docs/architecture.md
docs/authoring.md
docs/workflows/*.md
recursive_autoloop/run_recursive_autoloop_templates/*.md.tmpl
```

Replace the old package requirement language.

### New authoring doctrine

Docs should say:

```text
A workflow may be authored as:
1. a single Python file,
2. a package with flow.py and optional specs.py,
3. a mature package with manifest, prompts, assets, docs, and tests.
```

Docs should also say:

```text
flow.py + specs.py is the recommended serious-workflow shape, but it is not required.
```

### Keep manifest doctrine

Docs must preserve:

```text
workflow.toml is metadata-only.
```

It may contain:

* name,
* title,
* description,
* aliases.

It must not contain:

* topology,
* transitions,
* prompt definitions,
* session behavior,
* execution semantics,
* route policy,
* schemas,
* artifact contracts.

### Explain specs doctrine

Docs should explain:

```text
specs.py is ordinary Python. It is not required and not special to the runtime.
Use it to keep flow.py readable.
```

---

## 15. Scaffold / Init Changes

Update `autoloop init workflow`.

Add shape options:

```bash
autoloop init workflow release_review --shape single
autoloop init workflow release_review --shape flow-specs
autoloop init workflow release_review --shape package
```

Default should be:

```bash
--shape flow-specs
```

because that is the recommended serious-workflow shape.

### 15.1 Single shape

Generates:

```text
release_review.py
```

### 15.2 Flow-specs shape

Generates:

```text
release_review/
  flow.py
  specs.py
```

Optionally:

```text
release_review/prompts/
```

only if the generated flow uses file prompts.

### 15.3 Package shape

Generates:

```text
release_review/
  __init__.py
  flow.py
  specs.py
  workflow.toml
  prompts/
  assets/
```

Do not generate unused clutter.

---

## 16. Workflow Builder Changes

Update `workflow_idea_to_workflow_package` so generated workflows follow the new doctrine.

### Builder should support target shapes

The builder should be able to produce:

```text
single
flow_specs
package
```

Default: `flow_specs`.

### Builder output expectations

For generated workflows:

* `flow.py` should be readable and mostly topology.
* large schemas go in `specs.py`;
* route-contract helpers go in `specs.py`;
* validation helpers go in `specs.py` or imported stdlib helpers;
* docs are optional;
* manifest is optional unless the workflow is intended for catalog discovery;
* prompts/assets are optional.

### Builder should not require

* `contracts.py`,
* `params.py`,
* `prompts/`,
* `assets/`,
* docs,
* tests,
* manifest.

It may generate them when the chosen shape requires or benefits from them.

---

## 17. Test Plan

Add tests before or alongside implementation.

### 17.1 Strict root shim tests

Assert:

* root `workflow` still exports only the strict authoring surface;
* root does not expose engine/compiler internals;
* new helper modules are not exported from root unless explicitly approved.

### 17.2 Single-file workflow tests

Add a fixture:

```text
tests/fixtures/single_file_workflow.py
```

Test:

```bash
autoloop run tests/fixtures/single_file_workflow.py task-1 --message "..."
```

Assert:

* workflow resolves;
* compiles;
* runs;
* workspace created;
* prompts resolve relative to file parent;
* no manifest required;
* no package required;
* no prompts/assets folders required unless used by the fixture.

### 17.3 File reference class disambiguation tests

Fixture with two workflow classes.

Assert:

* `file.py` without class raises ambiguity error;
* `file.py:ClassA` works.

### 17.4 Flow package tests

Fixture:

```text
tests/fixtures/flow_package/
  flow.py
  specs.py
```

No `workflow.toml`.

Assert:

* direct path run works;
* inferred name run works if under discoverable workflows root;
* specs are imported only because flow imports them;
* no runtime special-casing of specs.

### 17.5 Existing `workflow.py` package tests

Assert current workflows still work.

### 17.6 Manifest package tests

Assert package with `workflow.toml` remains discoverable without import.

### 17.7 Shallow discovery tests

Create:

```text
workflows/a/workflow.toml
workflows/b/flow.py
workflows/c/workflow.py
workflows/d.py
```

Assert:

* list discovers entries;
* modules are not imported;
* manifest metadata used where available;
* inferred metadata used where manifest absent.

### 17.8 Deep inspection tests

Assert deep inspection imports and compiles.

### 17.9 Metadata-only manifest tests

Assert `workflow.toml` rejects or ignores semantic fields.

Forbidden fields:

```text
transitions
steps
prompts
sessions
parameters
route_contracts
artifacts
```

Prefer rejection with clear error if parser currently validates manifests.

### 17.10 Parameter resolution tests

Test:

* nested `Workflow.Parameters`;
* module-level `Parameters`;
* package-exported `Parameters`;
* no parameters.

### 17.11 Prompt resolution tests

Test prompt resolution relative to:

* single file parent;
* `flow.py` package dir;
* `workflow.py` package dir;
* manifest package dir.

### 17.12 Catalog shape tests

Assert catalog/capability payloads handle absent:

* manifest,
* specs,
* params,
* contracts,
* prompts,
* assets,
* docs,
* tests.

### 17.13 Validation-helper tests

Test reusable validation helpers:

* read valid Pydantic model file;
* reject invalid JSON;
* reject schema-invalid JSON;
* write model file under workflow folder;
* reject path escape;
* return readable validation feedback.

### 17.14 Builder tests

Assert builder can generate:

* single-file workflow;
* flow/specs workflow;
* full package workflow.

Generated outputs must compile.

---

## 18. Migration Strategy

Do not migrate all existing workflows immediately.

Existing workflows can remain in the current mature package shape.

Update docs and builders so new workflows use the flow-first shape.

Update catalog/capability helpers so they do not assume old package structure.

Gradually migrate selected workflows only if doing so improves readability.

---

## 19. Implementation Order

Implement in this order:

1. Add tests for flexible authoring forms.
2. Add internal workflow-reference model.
3. Extend resolver to support file refs, module refs, `flow.py`, and current `workflow.py`.
4. Update CLI `run` to use the unified resolver.
5. Update prompt/package folder resolution for file and flow-package workflows.
6. Update parameter resolution.
7. Update shallow discovery for manifest and inferred workflows.
8. Update deep inspection/capability serializers for optional files.
9. Add stdlib validation helpers.
10. Add route-contract helper bundles.
11. Update docs.
12. Update `autoloop init workflow`.
13. Update workflow builder.
14. Update recursive templates.
15. Run full tests and fix regressions.

---

## 20. Definition of Done

This work is complete only when:

1. A workflow can be authored and run as one Python file.
2. A workflow can be authored and run as `flow.py` plus optional `specs.py`.
3. Existing `workflow.py` package workflows still work.
4. `workflow.toml` is optional for execution.
5. `workflow.toml` remains metadata-only when present.
6. `specs.py` is recommended but not required.
7. Runtime does not special-case `specs.py`.
8. Docs no longer say every workflow must include `workflow.py`, `workflow.toml`, `prompts/`, and `assets/`.
9. Docs recommend `flow.py` + `specs.py` for serious workflows.
10. CLI can run named workflows, file workflows, and module/class workflows through one resolver.
11. Shallow discovery does not import modules.
12. Deep inspection may import and compile.
13. Catalog/capability surfaces tolerate absent docs/specs/prompts/assets/tests/manifests.
14. Reusable validation helpers reduce repeated schema boilerplate.
15. Route-contract helper bundles reduce repeated route boilerplate without hiding transitions.
16. Workflow builder emits flow-first workflows.
17. Root `workflow` shim remains strict.
18. Full test suite passes.

---

## 21. Guardrails for the Implementing Agent

When implementing:

* Do not introduce a second DSL.
* Do not make `specs.py` required.
* Do not make `workflow.toml` required for execution.
* Do not move semantics into `workflow.toml`.
* Do not expose internals through `workflow`.
* Do not remove current mature package support.
* Do not break existing workflows.
* Do not require docs/tests/prompts/assets for minimal workflows.
* Prefer small, explicit helpers over large framework abstractions.
* Keep the flow file readable.
* Preserve current runtime behavior unless explicitly changing resolver/discovery behavior.
* Add tests for every new supported authoring form.

---

## 22. Summary

The final framework should support this progression:

```text
# tiny / experimental
workflow.py

# serious / recommended
flow.py
specs.py

# mature / cataloged / documented
flow.py
specs.py
workflow.toml
prompts/
assets/
docs.md
tests/
```

The framework should never force authors to start at the mature package shape.

The flow definition is the product. Everything else is optional support.
