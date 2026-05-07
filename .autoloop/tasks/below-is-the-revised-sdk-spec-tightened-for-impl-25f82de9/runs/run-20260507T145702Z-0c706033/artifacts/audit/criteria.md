# Intent Audit Criteria
Check these boxes (`- [x]`) only when true.

- [ ] **Intent Ledger Coverage**: The audit considered the immutable request snapshot, raw log clarifications, run decisions, pair artifacts, tests, and final codebase.
- [ ] **Gap Classification**: Each material gap or difference is classified as either unresolved work or an intentional change justified by later clarification or analysis.
- [ ] **Evidence Quality**: Findings cite concrete request points, clarifications, artifacts, files, behavior, or tests rather than broad impressions.
- [ ] **Revised Intent Quality**: `revised_request.md` is a clean next-run request that focuses only on unresolved material gaps.
- [ ] **Machine Result**: `audit_result.json` is valid JSON and accurately reflects whether material gaps remain.
