# Risk Register

| Risk | Why it matters | Control |
| --- | --- | --- |
| Generic runtime absorbs workflow semantics | That would break the workflow-agnostic runtime boundary | Runtime neutrality tests plus workflow-owned parity modules |
| Extension seam grows into a second execution model | Hidden behavior would undermine the strict kernel | Keep one minimal `Workflow.extensions` seam and contract-test it |
| Session-path strategy leaks exact Autoloop-v1 naming into reusable extension code | Exact `sessions/plan.json` and `sessions/phases/{phase}.json` must remain workflow-owned | Session-path policy tests plus conventions-module ownership |
| Git tracking auto-enables or hides commit policy in runtime config | Git must be explicit and workflow-owned | Git extension design and no-global-enable tests |
| Stdlib grows into a second DSL | Authoring helpers could start hiding topology or semantics | Keep stdlib tiny and document its exact scope |
| Prompt resolution drifts from deterministic provenance | Hidden prompt lookup makes runs harder to explain and reproduce | Prompt resolution tests and explicit workflow prompt paths |
| Raw-log or decisions drift breaks Autoloop-v1 operations | Those artifacts are still operationally important for parity | Dedicated parity tests |
| Retained operational compatibility regresses for `thread_id` or `superloop.*` discovery | Existing persisted data and deployment config still need targeted support | Runtime store and config compatibility tests |
| Documentation drifts back toward observers or compatibility-era authoring | Future work could accidentally freeze the wrong target again | Baseline doc tests now pin the strict kernel, optional extensions, and narrow compatibility scope |
