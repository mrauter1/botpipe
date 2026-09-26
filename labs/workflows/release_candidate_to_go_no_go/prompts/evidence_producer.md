# Assemble release evidence

Collect and organize evidence against the accepted decision criteria.

Prefer the captured declared-evidence artifacts and their digests. Label any additional live discovery with its source and observation time; never use a newly discovered file as if it were the unavailable declared version.

- `release_inventory` identifies included changes, versions, dependencies, provenance, and unknown scope.
- `test_evidence_pack` separates executed checks and their results from planned, stale, unavailable, or unexecuted checks; include environment and coverage limits.
- `operational_readiness` covers approvals, deployment capability, observability, capacity, support, and ownership.
- `rollback_readiness` covers method, decision trigger, authority, time and data implications, prerequisites, and rehearsal evidence.
- `blocking_issues` names each candidate blocker, criterion affected, consequence, evidence, owner role if known, and resolution condition.

Return distinct `executed_checks` and `unexecuted_checks`. Accept when an assessor can trace each gate to evidence or an explicit gap. Rework collection or classification defects; replan a changed release scope. Never report a planned, inferred, or merely inspected check as executed.
