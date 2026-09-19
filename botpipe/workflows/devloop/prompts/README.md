# Devloop prompts

These prompts belong to the packaged `devloop` workflow. They support arbitrary repository tasks: the planner turns the request into phase-specific acceptance criteria, and the runtime supplies the exact criteria for each independent review.

## Stage flow

1. `plan` produces `plan/phase_plan.json`; its verifier writes `plan/review.json`.
2. The plan completion gate validates the plan and review report before activating a phase.
3. `implement` changes the repository for the active phase; its verifier writes the phase `review.json`.
4. When implementation evidence proves the authored phase item is defective, `review_phase_item` narrowly repairs it and its verifier writes `item_review.json`.
5. Unless `skip_test_phase=true`, `test` validates the active phase and its verifier writes the phase test `review.json`.
6. Completion gates update phase state and repeat the phase loop.
7. `audit` compares the finished run with the original request. Its verifier writes `audit/review.json`; a material gap can produce a bounded follow-up run.

Producer artifacts such as `implementation_notes.md`, `test_strategy.md`, and `item_review.md` remain human-readable evidence. Verifier decisions live only in structured review reports.

## Phase-plan contract

The planner writes strict JSON to `{{ task.folder }}/plan/phase_plan.json`. The top level is:

```json
{
  "version": 1,
  "task_id": "exact runtime task id",
  "request_snapshot_ref": "exact runtime request file path",
  "status": "planned",
  "phases": []
}
```

Each phase contains a unique, non-empty `phase_id` of at most 96 UTF-8 bytes, a title and objective, `planned` status, in-scope and out-of-scope lists, dependencies, at least one acceptance criterion, at least one deliverable, risks, and rollback actions. Dependencies that name phase ids must point to earlier phases. Path-safe ids such as `p01-frame` are preferred.

Acceptance criteria should describe observable task outcomes. They need not require a command, test suite, or formal proof when those do not fit the task. The implement and test reviews receive these criteria directly, preserving support for documentation, configuration, investigation, data, and other repository work as well as software changes.

## Structured review contract

Every verifier includes `review_contract.md` and writes one report:

| Review step | Report path |
| --- | --- |
| Plan | `{{ task.folder }}/plan/review.json` |
| Implement | `{{ task.folder }}/implement/phases/{{ state.phase.dir_key }}/review.json` |
| Test | `{{ task.folder }}/test/phases/{{ state.phase.dir_key }}/review.json` |
| Phase-item review | `{{ task.folder }}/plan/phases/{{ state.phase.dir_key }}/item_review.json` |
| Audit | `{{ task.folder }}/audit/review.json` |

The runtime injects `state.review.id`, `state.review.step`, nullable `state.review.phase_id`, and `state.review.criteria`. Implement and test criteria are the active phase acceptance criteria. Plan, phase-item review, and audit criteria state their process-specific semantic obligations.

A report contains:

```json
{
  "review_id": "runtime candidate review token",
  "criteria": [
    {
      "id": "exact runtime criterion id",
      "verdict": "passed",
      "evidence": ["Concrete observed evidence"],
      "reason": "Why the evidence supports the verdict"
    }
  ],
  "findings": [],
  "summary": "",
  "repair_target": "candidate"
}
```

Semantic report completeness is deterministic. `review_id` must match the current token, and `criteria` must contain every runtime id exactly once with no extras. Verdicts are `passed`, `failed`, or `blocked`. Passed criteria require non-empty concrete evidence and a reason that connects the evidence to the criterion. Failed criteria identify observed defects. Blocked criteria identify missing information or evidence that prevents a sound decision; uncertainty must not be reported as success.

`findings` capture material observations outside the supplied criteria and use `{verdict, evidence, reason}`. Passed findings are informational. Any failed or blocked finding prevents acceptance even if all criteria passed. `summary` may be empty. There is no duplicate top-level verdict: the runtime derives pass, rework, or blocked status from criteria and findings.

`repair_target` is optional and defaults to `candidate`. Only an implementation report with a failed criterion or finding may set it to `phase_item`, and only when the authored active phase item itself is impossible, contradictory, missing required dependencies, or mis-scoped. Ordinary implementation defects use `candidate`; unavailable external information is blocked.

## Evidence and token lifecycle

The runtime creates a review token after each producer candidate and before verification. A verifier must echo that exact token. Producer rework or a native question starts a new candidate attempt with a new token, so a report from an earlier attempt is stale. An interrupted verifier attempt can resume with its existing token because the producer candidate has not been rerun. After rework, the verifier inspects the new candidate and records new file observations, values, diffs, or actual command results rather than copying old conclusions.

The token binds the report to the workflow's candidate attempt; it is not a content hash of every repository file or external system. If concurrent external changes make recorded evidence stale, the candidate must be reviewed again.

Evidence remains task-specific. Verifiers run and record an automated check when the stage or request requires one and it is applicable. They do not impose a universal command runner or invent proof requirements for tasks that are properly verified through inspection or other evidence.

Verifiers never mutate producer-owned candidates. Failed reports route the appropriate producer/verifier pair for another attempt. Blocked reports stop the run with their reasons so unavailable evidence is not mistaken for rework or success.

## Completion gates and resume behavior

Completion gates validate candidate artifacts and the semantic review contract. Malformed JSON or schema-invalid reports use the runtime's native artifact failure and retry path. Freshness or completeness errors such as a stale `review_id`, missing or extra criterion ids, or an unsupported `repair_target` fail closed at the gate. The runtime writes `completion_gate_feedback.md` with those contract diagnostics and reruns the relevant producer/verifier pair. Phase-item review retains its existing diagnostic filename `item_review_gate_feedback.md`.

Legacy `criteria.md` and `feedback.md` files are never treated as current decisions. When a resumed legacy checkpoint reaches a migrated completion gate without the required current review request and report, that gate fails closed, records diagnostics, and reruns the relevant pair to create a fresh token-bound report.

An in-flight legacy checkpoint can resume directly inside a verifier without `state.review`. The shared prompt detects this before dereferencing review state and writes a schema-valid diagnostic rejection with `review_id: "unassigned"`, no criteria, and one failed finding requesting a fresh producer/verifier execution. It does not evaluate or accept the candidate and never requests phase-item repair. The missing assignment then follows the same gate-diagnostic and pair-rerun path. Active executions always receive a runtime review assignment; this fallback is only for persisted legacy state.

## Skipped phase tests

With `skip_test_phase=true`, the runtime writes an explicit skipped-test marker to the phase `test_strategy.md` and proceeds without invoking the test verifier. It does not fabricate a passing test review or checklist. The final audit treats that marker as reduced assurance and requests follow-up when material behavior remains unvalidated.
