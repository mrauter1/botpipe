# Failure-Mode Diagnostic Checklist

- Confirm `selected_workflow_capability.json` and `selected_workflow_run_history.json` exist and still name the same selected workflow.
- Confirm the filtered run history is non-empty and the run IDs under review stay explicit in the framing artifacts.
- Confirm `failure_mode_manifest.json` defines `selected_workflow_name`, `evidence_run_ids`, `failure_mode_ids`, `failure_modes`, `recurring_weak_point_ids`, and `workflow_name`.
- Confirm every failure mode is backed by concrete run-history evidence and every recurring weak point is surfaced in `recurring_weak_points.md`.
- Confirm `improvement_opportunities.json` ranks explicit opportunities, names the linked failure modes, and sets `publication_boundary` to `diagnostic_publication_only`.
- Confirm `diagnostic_next_actions.md` stops at recommendations and does not imply hidden runtime-owned execution, automatic refinement, or mutation of the selected workflow package.
