# Rank causes and choose immediate posture

Use the accepted incident evidence to compare causal hypotheses and define safe near-term action.

- `cause_hypothesis_ranking` states competing hypotheses, supporting and contradicting evidence, confidence, disconfirming tests, and why the current leader ranks first. Correlation is not causation.
- `immediate_mitigation_plan` separates containment, recovery, and reversible risk reduction; include permissions, owners or roles, safety checks, rollback, and stop conditions.
- `validation_plan` sequences the highest-information tests and says what result would update the ranking.
- `incident_summary.json` contains `recommended_posture` (`urgent`, `high`, or `planned`), non-empty `primary_hypothesis`, and non-negative `hardening_backlog_items` consistent with the planned backlog.

Accept when the posture and mitigation are proportionate to impact and uncertainty. Rework analysis defects; replan a changed incident boundary. Do not present the leading hypothesis as proven or authorize unsafe actions implicitly.
