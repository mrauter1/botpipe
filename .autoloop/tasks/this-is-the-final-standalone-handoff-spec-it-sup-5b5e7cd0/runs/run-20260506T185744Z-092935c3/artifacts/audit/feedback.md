# Intent Audit <-> Intent Audit Verifier Feedback

- `AUD-001` non-blocking: Verified the audit artifacts are internally consistent and evidence-backed. The two reported material gaps are real in the final codebase: current runtime transports do not consume generated `response_schema`, and raw JSON-schema route contracts can lose runtime validation when `jsonschema` is unavailable. The revised request is a direct next-run request for exactly those unresolved gaps, and `audit_result.json` accurately reports `material_gaps_found: true`.
