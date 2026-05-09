# Intent Audit <-> Intent Audit Verifier Feedback

- AUD-001 | resolved | `artifacts/audit/gap_report.md`, `artifacts/audit/revised_request.md`, `tests/strictness/test_no_compat.py` | The active current-run contract now inventories all six final audit/session files explicitly and keeps the classification exact-path-based.
- AUD-002 | resolved | `artifacts/audit/audit_result.json`, `artifacts/audit/gap_report.md`, `tests/strictness/test_no_compat.py` | The repo-root artifact branding walk now treats only the path-bearing audit result as an exact per-file exception, while the remaining audit/session files stay required-clean.
