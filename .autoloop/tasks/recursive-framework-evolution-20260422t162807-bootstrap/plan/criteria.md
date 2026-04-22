# Plan Verification Criteria
Check these boxes (`- [x]`) only when true.

- [ ] **Intent Fidelity**: The plan fully reflects the user’s stated intent and authoritative clarifications without silently changing scope or behavior.
- [ ] **Behavioral Safety**: The plan does not introduce regression bugs, logical flaws, or unintended behavior unless such behavior change is explicitly required by user intent and explicitly confirmed.
- [ ] **Completeness**: Scope, milestones, interfaces, dependencies, validation, rollout, rollback, and operational constraints are concrete and implementation-ready.
- [ ] **Technical Debt**: The plan avoids unnecessary indirection, duplication, scattered ownership, over-engineering, and other avoidable technical debt.
- [ ] **Feasibility / Compatibility**: Sequencing is realistic, risks are surfaced, and compatibility, migration, or backward-compatibility impacts are explicit where relevant.
