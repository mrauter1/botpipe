# Criteria

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: docs-tests-and-legacy-removal
- Phase Directory Key: docs-tests-and-legacy-removal
- Phase Title: Docs Tests And Legacy Removal
- Scope: phase-local authoritative verifier artifact

Check these boxes (`- [x]`) only when true.

- [ ] **Correctness / Intent Fidelity**: Changes satisfy the accepted plan and confirmed user intent, and implement the requested behavior correctly.
- [ ] **Behavioral Safety**: Changes do not introduce regression bugs, logical flaws, or unintended behavior unless such behavior change is explicitly required by user intent and explicitly confirmed.
- [ ] **Compatibility / Safety**: No material compatibility, security, data-integrity, or operational regressions were introduced.
- [ ] **Technical Debt / Simplicity**: Changes avoid unnecessary indirection, duplicated logic, scattered ownership, over-engineering, and unrelated refactors.
- [ ] **Maintainability / Validation**: Diffs are cohesive, follow repository conventions, and are supported by appropriate validation, documentation, or notes where needed.

Reviewer note: left unchecked because blocking finding `IMP-001` shows root-scoped workflow resolution is still unsafe across multiple repositories in one Python process.
