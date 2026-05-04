# Intent Audit <-> Intent Audit Verifier Feedback

- `AUD-000` `non-blocking`
  Audit verified. The reported documentation/test gap is real and material: `46` workflow prompt bodies still contain retired `Reserved routes` wording, representative prompt files still describe `question`, `blocked`, and `failed` as reserved/default routes, and runtime prompt-package tests still assert that wording. `gap_report.md`, `revised_request.md`, and `audit_result.json` classify that follow-up accurately and narrowly.
