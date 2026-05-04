# Refinement Package Checklist

- Keep the selected workflow fixed; this building block refines one chosen workflow and does not choose a new one.
- Capture both `selected_workflow_capability.json` and `selected_workflow_authoring_surface.json`; workflows that need both views must keep them separate.
- Publish `baseline_workflow_surface/` and `baseline_workflow_manifest.json` before any candidate authoring begins.
- Copy the baseline package into `candidate_workflow_surface/` and preserve every baseline file.
- Keep any added candidate files inside the selected workflow package boundary.
- Do not mutate the authoritative selected workflow package before later promotion.
- Let the workflow derive `candidate_workflow_manifest.json` deterministically from the candidate surface.
- Tie `evaluation_delta_report.md`, `promotion_record.md`, and `rollback_plan.md` directly to the copied baseline evidence and the baseline or candidate manifests.
- Publication must validate the candidate through an isolated overlay or equivalent temp-copy path before writing `workflow_refinement_receipt.json`.
