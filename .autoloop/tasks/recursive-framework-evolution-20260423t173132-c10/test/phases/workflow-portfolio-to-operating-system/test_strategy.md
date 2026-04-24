# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c10
- Pair: test
- Phase ID: workflow-portfolio-to-operating-system
- Phase Directory Key: workflow-portfolio-to-operating-system
- Phase Title: Workflow Portfolio To Operating System
- Scope: phase-local producer artifact

## Behaviors covered

- Discovery and compilation of `workflow_portfolio_to_operating_system`, including explicit typed control contracts on all three pair steps.
- End-to-end runtime proof for capability snapshot, portfolio-health snapshot, lifecycle matrix, governance package, summary, next actions, and deterministic receipt.
- Publish-side rejection for missing scoped evidence, unknown focus-workflow references, summary drift, invalid lifecycle postures, and hidden downstream execution in publication artifacts.
- Architecture-baseline assertions that cycle-10 recursive memory now treats portfolio governance as shipped and decomposition as the next deferred follow-on.

## Preserved invariants checked

- The workflow stops at `operating_system_publication_only` and does not auto-run downstream workflows.
- Publish validation remains artifact-first and deterministic.
- Stable operational portfolio-health fields remain asserted without freezing aliases or descriptions owned by other workflow packages.
- Explicit negative guardrails such as `do not auto-run` remain allowed and do not trigger false-positive publication failure.

## Edge cases

- Zero-run scoped workflows still appear in portfolio-health output through the shared seam.
- Hidden-execution rejection now covers `auto-run`, queue, launch, and automatic phrasing variants across next-actions text and summary `next_action`.
- Negative guardrail phrasing is accepted when it keeps downstream execution explicit rather than implying automation.

## Failure paths

- Missing `workflow_capability_snapshot.json` or `workflow_portfolio_health_snapshot.json`.
- Unknown scoped workflow references.
- Summary posture-count drift and lifecycle-posture drift.
- Invalid lifecycle postures in `portfolio_operating_summary.json`.
- Hidden downstream execution language in `portfolio_next_actions.md` and in summary `next_action`.

## Known gaps

- The current phase proof does not add equivalent hidden-execution-phrase broadening to other workflows; this strategy stays scoped to `workflow_portfolio_to_operating_system`.
- The runtime proof remains targeted rather than repo-wide; broader suites are intentionally out of scope for this phase.

## Flake risks / stabilization

- No network or timing dependence.
- Temporary workspaces are isolated under `tmp_path`.
- Workflow package imports are stabilized by clearing module cache between tests.
- Assertions use deterministic fixtures and exact artifact contents only where the phase owns the contract surface.
