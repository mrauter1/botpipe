# Portfolio Operating-System Checklist

- Confirm `workflow_capability_snapshot.json` and `workflow_portfolio_health_snapshot.json` both exist and describe the same scoped workflow set.
- Keep the workflow boundary at governance publication only; recommendations may name downstream workflows, but this workflow must not execute them.
- Make lifecycle postures explicit for every analyzed current workflow, even when the recommendation is `keep`.
- Keep create-next recommendations explicit in `portfolio_change_candidates.json` and `workflow_portfolio_operating_system.md`.
- Keep merge and retire guidance explicit, even when the recommendation is "none this cycle".
- Ensure `portfolio_operating_summary.json` matches the lifecycle matrix and change-candidate manifest without summary drift.
- Keep `portfolio_next_actions.md` explicit about the handoff boundary and the exact next action another operator or workflow should take.
