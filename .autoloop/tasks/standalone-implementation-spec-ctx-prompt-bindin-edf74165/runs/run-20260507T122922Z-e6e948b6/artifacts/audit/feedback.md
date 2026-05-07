# Intent Audit <-> Intent Audit Verifier Feedback

- AUDIT-001 `blocking`
  The final implementation still diverges from the original contract in two places: `ctx.input.message` remains a supported request alias, and runner-backed contexts still cache `message=` instead of deriving `ctx.message` from the run-local request snapshot. See `gap_report.md` and `revised_request.md`.
