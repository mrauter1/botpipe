# Intent Audit <-> Intent Audit Verifier Feedback

- AUDIT-001 `blocking`
  The final implementation still diverges from the original contract in two places: `ctx.input.message` remains a supported request alias, and runner-backed contexts still cache `message=` instead of deriving `ctx.message` from the run-local request snapshot. See `gap_report.md` and `revised_request.md`.

- AUD-002 `non-blocking`
  Verifier recheck: the audit artifacts classify those two issues correctly as unresolved implementation gaps rather than audit defects. `gap_report.md`, `revised_request.md`, and `audit_result.json` are aligned with the request, decisions ledger, and inspected code/tests, so the audit phase can complete with material follow-up work still pending.
