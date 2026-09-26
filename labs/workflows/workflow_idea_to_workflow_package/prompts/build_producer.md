## Durable typed phase result

Return one JSON result matching the injected phase-specific schema and follow the runtime's `artifact_requirement`. Before returning `accepted`, write every declared artifact and ensure it meets this phase's done criteria. For `needs_rework`, `needs_replan`, `question`, `blocked`, or `failed`, write only real evidence that is already available and useful; a control outcome does not require filler artifacts. Never fabricate a file to satisfy the declared acceptance outputs. Cite only artifacts actually captured.

Resolve relative repository and evidence paths against the injected `source_workspace`. The writable working directory is disposable authoring scratch, not the source repository; represent generated package files only through the declared content manifest.

# Build the workflow package

## Purpose

Author the complete source bytes for the reviewed design. The runtime will materialize them into a run-owned isolated candidate and execute deterministic validation before evaluation.

## Work boundary

Implement the reviewed design and prompt plan. Do not silently redesign the workflow or claim that validation has run.

## Stable obligations

- Write `workflow_package_manifest` as JSON with `package_name`, `workflow_reference`, and a non-empty `files` array. Each file entry requires only repo-relative `path` and complete text `content`; `role` is optional descriptive metadata.
- Keep generated package files under `.botpipe/workflows/<package_name>/`. The only permitted path outside it is the focused test at `tests/runtime/test_<package_name>.py`. Include that test when `enforce_generated_test` is true; direct lab callers that leave the flag false may omit it only when the reviewed design does not need it.
- Include `.botpipe/workflows/<package_name>/flow.py` and `.botpipe/workflows/<package_name>/workflow.toml`. Set `workflow_reference` to `.botpipe/workflows/<package_name>/flow.py:<callable>`.
- Make `workflow.toml` name the requested package and select the generated callable; carry over the supplied title and aliases when present.
- Add contracts, prompts, assets, documentation, or tests only when the reviewed design needs them. Implement every prompt named by `prompt_design`, and do not add ceremonial prompt files.
- Use ordinary Python and the current public Botpipe API. Keep control flow visible. Do not generate route tables, graph frameworks, or a new generic engine.
- Preserve stable prompt obligations from `prompt_design` while allowing the executing provider to choose sound methods. Ground prompt work in supplied evidence, require contradiction and assumption handling, define semantic handoffs, and test substantive completion rather than format alone.
- Implement behavioral tests around the generated workflow entry point. Cover meaningful routing or replay behavior where relevant; do not satisfy the requirement with import-only checks, a fixed quota of assertions, vacuous assertions, or claims that fakes prove live-system quality.
- When `runtime_validation_feedback` is present, repair every relevant manifest, compile, import, discovery, metadata, or test failure in the next complete manifest. Do not repeat rejected bytes.
- When `rejected_candidate_evidence` is present after an evaluation replan, implement the reviewed correction against its exact candidate paths, hashes, checks, and captured findings. Do not repeat the rejected source or prompt behavior.
- Write `implementation_notes` mapping the generated files to the reviewed steps and prompts, explaining deliberate deviations and any remaining limitation.

## Done criteria

Return `accepted` when the manifest is a complete, internally consistent package representation suitable for isolated materialization. Populate `changed_paths` and `evidence_artifacts` from the artifacts; they are proposed build evidence, not proof of runtime validation. If the reviewed design still cannot correct an upstream source or prompt defect, use `needs_replan`; do not use local rework to evade a required redesign.
