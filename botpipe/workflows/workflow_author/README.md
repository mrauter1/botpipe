# Workflow Author

`workflow_author` turns a workflow request into a reviewed package candidate.
It frames the request, designs the fewest coherent steps and their prompts,
builds a complete manifest, materializes it in a run-owned root, validates it,
and performs an independent read-only evaluation review. The packaged API is:

- `workflow_author(params, request="")`
- `Params`
- `WorkflowAuthorResult`

## Python

```python
from botpipe import Botpipe
from botpipe.workflows.workflow_author import Params, workflow_author

params = Params(
    package_name="customer_escalation",
    package_title="Customer escalation",
    aliases=["escalation"],
)

with Botpipe(workspace=".") as runtime:
    run = runtime.run(
        workflow_author,
        params,
        request="Turn an escalation into a reviewed customer response.",
    )

candidate = run.value
print(candidate.package_path)
print(candidate.workflow_reference)
print(candidate.validation.success)
for file in candidate.files:
    print(file.path, file.sha256, file.size_bytes)
```

`package_name` is required. `package_title`, `aliases`, and `workflow_kind` are
optional catalog inputs. `max_provider_turns` defaults to `32` for the complete
run. Prefer `target_test_argv` when the repository needs a test command other
than the automatically selected focused pytest. The legacy
`target_test_command` string remains available for explicit compatibility use;
supply only one test-command form.
The default validation requires pytest in the Python environment; install
`botpipe[test]` to include it.

## CLI

Pass a JSON list containing the parameter object and request:

```bash
botpipe run workflow_author --workspace . \
  --input '[{"package_name":"customer_escalation"},"Turn an escalation into a reviewed customer response."]'
```

The CLI prints the serialized run result. Use `candidate_root`, `package_path`,
and `workflow_reference` to inspect or execute the candidate. `files` records
the path, SHA-256 digest, and byte size of each validated file. `validation`
contains the checks that actually ran and any errors.
`surface_boundary` records the runtime's validation boundary. Before handing
off a candidate, including after an interrupted handoff resumes, the workflow
checks its complete inventory against the recorded surface identity. Resuming
an already completed run returns historical evidence without rerunning checks,
as with other Botpipe workflows.

## Process and proof

Every provider receives the bundled Botpipe authoring and prompting guides.
The packaged entry invokes the reusable builder as a nested durable workflow.
That workflow runs request framing, guide-based design with an independent query
review, manifest build, runtime compile/import/discovery and tests, then semantic
evaluation with another independent query review. Invalid manifests and failed
executable validation get at most three complete build attempts. Source, prompt, implementation-proof,
or behavior defects replan through design and build a fresh candidate;
evaluation-report defects can rework locally. It asks the user only for a
material missing fact.

The package must include `tests/runtime/test_<package_name>.py`. With no explicit
test argv, validation runs that file through focused pytest automatically. An
explicit `target_test_argv` replaces the automatic test command, while the
generated behavioral test remains part of the package. The review rejects
vacuous proof and records what remains unproven; passing a fake or narrow mock
does not establish live-system quality.

The result remains under the run-owned `candidate_root`. Nothing is copied into
the authoritative workspace automatically. Review the returned source, hashes,
validation checks, and residual limitations before deliberately promoting the
package. Validation combines the candidate with a frozen copy of the source
workspace; the returned candidate contains authored files and selected anchors,
so execution may still require the target project's code and dependencies.
