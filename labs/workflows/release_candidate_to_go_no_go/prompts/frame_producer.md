# Frame the release decision

Define what is being released and the evidence required for a responsible decision.

- `release_scope_brief` states candidate identity, owner, target environment and date, user or system impact, change boundary, dependencies, and exclusions.
- `decision_criteria` defines mandatory gates, risk tolerances, approval and change-window requirements, rollback expectations, and the semantics of `go`, `conditional_go`, and `no_go` for this release.
- `evidence_intake_register` maps each criterion to immutable declared sources in `evidence_intake`, explicit unavailable records, or permitted live discovery, and names access, freshness, or ownership gaps.

Accept when evidence collection can test concrete release criteria. Rework local ambiguity; replan a changed release boundary or risk policy; ask or block when missing authority or intent prevents a defensible gate. Do not gather full evidence or recommend a decision yet.
