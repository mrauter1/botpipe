# Workflow Idea To Workflow Package

Turn the workflow the user selected into a reviewed, executable workspace workflow package. The SOP preserves the request instead of inventing a candidate competition, treats prompts as part of the design, and distinguishes deterministic executable proof from semantic assessment.

Canonical name: `workflow_idea_to_workflow_package`

Aliases: `workflow-builder`, `workflow-idea-builder`

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.workflow_idea_to_workflow_package import Params, workflow_callable

params = Params(package_name="customer_escalation")
result = Botpipe(workspace=".").run(
    workflow_callable,
    params,
    request="Build a workflow that turns an escalation into a reviewed response.",
)
```

`package_name` is required. `package_title`, `aliases`, and `workflow_kind` tune
catalog metadata. `max_provider_turns` defaults to `32` across the whole SOP.
Use `target_test_argv` for an explicit argument-list test command. The optional
`target_test_command` string remains only for compatibility with older callers;
prefer argv because it does not require shell parsing.

The returned `WorkflowAuthorResult` extends the usual lab workflow result with
`package_name`, `candidate_root`, `package_path`, `workflow_reference`, a
validated `files` inventory (`path`, `sha256`, and `size_bytes`), and the typed
runtime `validation` record containing the checks that actually ran and their
errors.

The generated package uses the current workspace-native layout:

```text
.botpipe/workflows/<package_name>/
├── flow.py
├── workflow.toml
└── prompts/ and other support files only when the design needs them
```

Replanning does not reset the shared provider-turn budget. Isolated
materialization permits one focused test at
`tests/runtime/test_<package_name>.py`; the reusable lab engine treats it as
optional by default. The packaged `workflow_author` entry sets
`enforce_generated_test`, so that entry always requires the test. Explicit
`target_test_argv` replaces the automatically selected focused pytest command;
it does not remove the generated test from the package. Neither entry writes
generated files into the authoritative workspace.

This version replaces the retired `authoring_shape` choices with that single discoverable package format; the old parameter is rejected rather than silently ignored. Start a new run when moving from an older workflow version, because its recorded phases and prompts are different.

Writable producer turns run with `workspace-write` in a dedicated run-owned child workspace. The authoritative workspace is supplied separately as `source_workspace` for read-only inspection. Declared artifacts are also rooted inside the producer workspace, so their writable destinations do not widen access to durable run metadata or source files. Independent reviewers remain read-only.

## Executable SOP

| Phase | Purpose and acceptance boundary | Durable artifacts |
| --- | --- | --- |
| `frame_request` | Preserve the selected request and ground its purpose, intended outcome, constraints, evidence, and material assumptions. | `workflow_brief.md` |
| `design_workflow` | Define coherent steps, semantic decisions, evidence handoffs, acceptance/recovery behavior, and only the prompts the workflow needs. An independent read-only query reviewer protects this pre-build boundary. | `workflow_design.md`, `prompt_design.md` |
| `build_package` | Produce exact source bytes for the reviewed design. The runtime materializes them in an isolated candidate and retries at most three builds for invalid manifests or failed executable validation. | `workflow_package_manifest.json`, `implementation_notes.md` |
| `evaluate_package` | Compare actual source and prompts with the request and design, report executable checks, and separate proven from unproven outcomes. An independent read-only query reviewer protects the downstream handoff. | `workflow_evaluation.md`, `workflow_package_summary.json`, `workflow_next_action.md` |

Each step has one coherent work boundary: authoritative evidence in, a defined semantic or implementation job, captured evidence out, and explicit local-rework versus upstream-replan conditions. Python owns loops and branches. The design uses a diagram only if meaningful branching or concurrency would otherwise be hard to understand.

## Materialization and validation

`workflow_package_manifest.json` is a constrained transport envelope for exact source text, not a second workflow DSL. It contains `package_name`, an explicit `.botpipe/workflows/<package_name>/flow.py:<callable>` reference, and the complete `files` inventory. The runtime rejects absolute/traversal paths, files outside the package and optional test boundary, duplicate paths, oversized inventories, symlink escapes, mismatched package names, missing `flow.py` or `workflow.toml`, and mutation of authoritative source.

Validation runs against a frozen, run-owned candidate. It compiles and imports
the referenced callable, checks workspace catalog discovery and metadata, and
runs explicit `target_test_argv` when supplied. With
`enforce_generated_test`, it otherwise runs the generated focused pytest file
automatically. Candidate paths, hashes, checks, errors, and cancellation state
become evaluation inputs. The final semantic review must still inspect purpose,
prompt completeness, contradictions, assumptions, handoffs, downstream
contracts, and actual outcomes. Passing syntax, matching a JSON shape, or
running a fake or narrow mock does not prove live workflow quality.

## Outcomes and recovery

`accepted` requires the phase's complete declared artifact set and advances. A
control outcome may capture partial real evidence, or no artifact when none
exists; the producer must not invent placeholder files before pausing or
redirecting work. `needs_rework` repeats the same phase with typed feedback and
available immutable artifacts. `needs_replan` returns to `frame_request` from
design, or to `design_workflow` from build/evaluation. Evaluation rework is
limited to correcting evaluation/report artifacts against unchanged candidate
bytes. A generated source, prompt, implementation-proof, package-behavior, or
design defect replans through `design_workflow` with the rejected candidate
records and immutable findings, then builds and validates a fresh candidate. A
genuine missing prerequisite suspends through human input. Terminal failures
stop. Invalid manifests and failed executable validation share a bound of three complete build attempts,
and the provider budget spans every rework and replan.
