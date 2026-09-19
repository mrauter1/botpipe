# `devloop`

`devloop` is the default packaged Botpipe workflow. It turns an arbitrary repository task into an explicit phase plan, executes each phase, independently reviews the result, audits the completed run against the original request, and can create bounded follow-up runs for material audit gaps.

It is installed with the `botpipe` package and is discoverable as:

```bash
botpipe workflows show devloop
botpipe workflows show default
```

## Workflow

The workflow has five reviewed stages:

- `plan` produces an ordered `phase_plan.json` with task-specific acceptance criteria.
- `implement` executes the active phase and records implementation evidence.
- `review_phase_item` narrowly repairs an active plan item when implementation proves that item cannot be executed as authored.
- `test` validates the active phase unless `skip_test_phase=true`.
- `audit` checks the complete result against the original request and prepares a standalone revised request when another run is required.

Every verifier writes one JSON review report. The runtime gives it a unique candidate token and an authoritative criterion list. A complete report echoes the token, covers every criterion id exactly once, and gives each criterion a `passed`, `failed`, or `blocked` verdict with a reason and appropriate evidence. Passed criteria require concrete, non-empty evidence. Failed or blocked findings outside the criteria also prevent acceptance. There is no separate checklist, feedback decision, or duplicated top-level verdict; the runtime advances passed reports, routes failed reports to rework, and stops on blocked reports with their reasons.

Implement and test reviews use the active phase's acceptance criteria. Other stages receive criteria for their semantic obligations, such as plan integrity, safe phase-item repair, and audit consistency. This keeps review specific without assuming every task needs a test command or formal proof. Evidence may be repository state, file contents, observed values, diffs, inspection, or actual command output. When an applicable automated check is required, the verifier records its actual result.

The review token belongs to one workflow candidate attempt. Producer rework or a native question produces a new token; an interrupted verifier attempt can resume with the same token when its producer has not rerun. The verifier must inspect a reworked candidate and provide new evidence. The token is not a hash of arbitrary repository or external state, so concurrent changes that invalidate the evidence require another review. Verifiers do not repair their candidates.

An implementation failure normally returns to implementation. If evidence shows the phase-plan item itself is impossible, contradictory, missing dependencies, or mis-scoped, the implementation verifier may set `repair_target: "phase_item"` on a failed report. The workflow then runs the narrow phase-item repair and review before implementation resumes. Missing external information is blocked rather than misclassified as a plan repair.

Malformed JSON and schema-invalid reports use the runtime's native artifact failure and retry behavior. Completion gates fail closed on semantic errors such as stale tokens, incomplete criterion coverage, or invalid repair targeting and write `completion_gate_feedback.md` diagnostics before rerunning the relevant producer/verifier pair. Phase-item review uses `item_review_gate_feedback.md`. Old `criteria.md` and `feedback.md` files never count as current decisions; a resumed legacy checkpoint that reaches a migrated gate without a current review request and report fails closed and reruns the affected pair with a fresh token.

An in-flight legacy checkpoint may resume inside a verifier without a review assignment. The shared verifier contract handles that state before reading review fields and writes a schema-valid diagnostic rejection with `review_id: "unassigned"`, empty criteria, and a failed finding that requests a fresh producer/verifier execution. The report cannot accept the candidate or request phase-item repair. The completion gate records the missing-assignment diagnostic and reruns the affected pair. Current executions always have a runtime assignment; this path exists only for persisted legacy state.

When `skip_test_phase=true`, devloop writes an explicit skip marker to the phase `test_strategy.md`. It does not create a fake passing review or checklist. The final audit treats skipped phase validation as reduced assurance and creates a follow-up request if the remaining evidence does not establish the requested outcome.

Review artifacts are stored with their stages:

| Stage | Review report |
| --- | --- |
| Plan | `plan/review.json` |
| Implement | `implement/phases/<phase>/review.json` |
| Phase-item repair | `plan/phases/<phase>/item_review.json` |
| Test | `test/phases/<phase>/review.json` |
| Audit | `audit/review.json` |
