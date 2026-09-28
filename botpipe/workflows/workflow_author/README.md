# Workflow Author

`workflow_author` turns a request into a tested, independently reviewed workflow
candidate. One author session understands, builds and repairs; a separate reviewer
session checks the original request, clarification answers, source and test transcript.

```python
from botpipe import Botpipe
from botpipe.workflows.workflow_author import Params, workflow_author

with Botpipe(workspace=".") as runtime:
    run = runtime.run(
        workflow_author,
        Params(package_name="customer_escalation", max_rounds=4),
        request="Turn an escalation into a reviewed customer response.",
    )

if run.ok:
    candidate = run.value
    print(candidate.shipped, candidate.reference, candidate.candidate_root)
    print(candidate.findings)
```

CLI input is a parameter object followed by the request:

```bash
botpipe run workflow_author --workspace . \
  --input '[{"package_name":"customer_escalation"},"Review customer escalations."]'
```

The author writes directly into one run-owned copy of the project, including
`.botpipe/workflows/<package_name>/flow.py`, `workflow.toml`, and
`tests/runtime/test_<package_name>.py`. It never promotes the candidate into the
source workspace. Existing target packages are rejected; choose a new name.
The candidate retains project dependencies and excludes repository/runtime caches.

The brief defines intended outcomes, assumptions, human gates and concrete scenarios.
Material questions pause through `ask_human`; answers are recorded and passed to both
author and reviewer. Findings return to the same author session. An updated brief can
correct an assumption, but must preserve the original request and explicit answers.
Review findings remain explicit through clarification and failed test attempts. The
reviewer also receives the first build-ready brief to detect removed or weakened
scenarios; later explicit human answers can supersede that baseline's assumptions.
Unresolved questions prevent shipping. `max_rounds` bounds build/review and further
clarification cycles; exhaustion returns `shipped=False` with the remaining findings.
`max_provider_turns` bounds provider work, including schema repair, separately.

The runtime validates the exact entry point, catalog metadata, compilation/import,
and generated behavioral tests. Install `botpipe[test]` for pytest. Optional
`target_test_argv` runs an additional check after the mandatory focused tests; it cannot
replace them. Commands use argument lists, not shell interpolation. Timeouts and failed
checks feed the next repair. `validation` records output, errors, the transcript path
and the tested content identity. The reference is returned only after runtime validation.

Tests use `FakeProvider`. The opt-in
`botpipe.workflows.workflow_author.transcript_plugin` records human questions and
answers, agent turns, workflow results and pytest outcomes. The author and reviewer
read this transcript. Warnings about answers absent verbatim from subsequent prompts
are investigation hints: transformed values, deterministic routing and session context
can be legitimate. The heuristic checks strings of at least three words and names the
missing text; shorter answers remain fully recorded. Identical instruction blocks are
printed once and referenced on each turn; changed instructions remain visible.
Tests must assert behavioral consequences, not literal forwarding.
Scripted responses demonstrate only the behavior exercised; they do not prove live
model quality. The reviewer uses `query` for read-only inspection.

Before shipping, including after an interrupted handoff resumes, the runtime checks
that the candidate and transcript still match the successful validation. Completed
runs retain historical results on resume, as elsewhere in Botpipe. Run a new authoring
operation when you want fresh work. Inspect the result before deliberate promotion;
`shipped=True` means the candidate passed this acceptance process, not that it was
published or deployed.
