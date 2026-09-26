# Release Decision Package Checklist

- Confirm the release boundary and target date are explicit.
- Preserve declared-evidence digests and unavailable reasons; label later live discovery separately.
- Record the authoritative go/no-go criteria.
- Distinguish executed checks from planned, stale, unavailable, or unexecuted checks.
- State operational readiness findings and missing approvals.
- State rollback readiness and prerequisites.
- Make blocking issues explicit.
- Record the final recommendation as `go`, `conditional_go`, or `no_go`.
- Confirm `conditional_go` has enforceable conditions and does not rename a mandatory failure.
- Align the stakeholder communication draft to the assessed recommendation.
