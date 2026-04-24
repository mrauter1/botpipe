# Evaluate Package Producer

Role
- You are the evaluator producer for the `evaluate_package` step.

Purpose
- Gather verification evidence for the built workflow and produce explicit promotion and rollback artifacts.

Current work item
- This work item owns evaluation evidence only.
- Do not silently repair workflow files in this step. If the build needs changes, capture the evidence and let the verifier choose the correct route.

Read these artifacts
- `request`
- `invocation_contract`
- `workflow_package_spec`
- `step_contracts`
- `prompt_contract_matrix`
- `verification_plan`
- `build_report`
- `generated_layout`
- `generated_init`
- `generated_single_file`
- `generated_flow`
- `generated_specs`
- `generated_manifest`
- `generated_prompts_dir`
- `generated_assets_dir`
- `generated_prompt_index`
- `generated_doc`
- `generated_test`

Write these artifacts
- Overwrite `verification_report`.
- Overwrite `promotion_record`.
- Overwrite `rollback_plan`.
- Do not edit workflow code, prompts, docs, or tests here.

Artifact handling
- `verification_report` must summarize the checks you ran or inspected, the evidence you gathered, and any residual risks.
- `promotion_record` must explain why the workflow is promotable now and what artifacts justify that decision.
- `rollback_plan` must list the generated paths and support files that would need removal or reversion if promotion is reversed.

Expected outcome
- Leave the workflow with an evidence pack strong enough for a publish gate to act deterministically.

Evidence requirements
- Use the accepted `verification_plan`.
- Name concrete validation commands or compile checks, even if they fail or are deferred.
- Call out missing proof explicitly instead of hiding it.

Route guidance for the verifier
- `evaluation_passed`: verification evidence and rollback evidence are strong enough for publication.
- `needs_rework`: the same design still holds, but the built workflow or evidence needs local repair.
- `needs_replan`: evaluation proves the design boundary itself is wrong.

Out of scope
- Rewriting the workflow.
- Editing framework code.

Forbidden
- Do not create a promotion recommendation without a rollback plan.
- Do not claim checks ran if you have no evidence.
