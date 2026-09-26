# Assess go or no-go

Apply the accepted criteria to the reviewed evidence and make one explicit recommendation.

- `go_no_go_assessment` states `go`, `conditional_go`, or `no_go`; maps each material criterion to evidence; distinguishes blockers, accepted risk, conditions, and unknowns; and names what could change the recommendation.
- `risk_register.json` ranks decision-relevant risks with evidence, likelihood or uncertainty, consequence, treatment, owner role, and disposition.
- `decision_summary.json` contains `recommended_decision`, `blocking_issue_count`, `executed_checks`, `unexecuted_checks`, `ready_for_packaging`, `authoritative_artifacts`, and `justification_summary`.

`go` requires satisfied mandatory gates and no unresolved release-stopping blocker. `conditional_go` requires explicit, enforceable conditions that fit the defined policy; it is not a way to waive a blocker. Accept when the recommendation follows from evidence and uncertainty. Rework reasoning locally; replan a changed scope or criteria. Do not invent approvals or evidence.
