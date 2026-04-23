# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c3
- Pair: test
- Phase ID: security-remediation-workflow-package
- Phase Directory Key: security-remediation-workflow-package
- Phase Title: Ship Security Remediation Workflow
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Happy path:
- discoverability, compilation, parameter normalization, and full successful runtime execution for `security_finding_to_verified_remediation`
- child evidence-pack composition, parent-local artifact adoption, and deterministic remediation receipt publication
- Preserved invariants:
- child `question` propagation pauses the parent without adopting evidence artifacts
- runtime-injected control contracts remain explicit on the three pair steps
- `deployment_constraints` stay parent-local and are not forwarded into the child workflow's `source_constraints`
- Edge cases:
- repeatable parameter normalization removes blanks and duplicates
- a published child evidence pack with `ready_for_downstream_assessment=false` blocks the parent before any adopted evidence artifacts exist
- Failure paths:
- publish step rejects a missing `selected_remediation`
- direct compose-step seam test guards the child-result contract even outside the full runtime

## Stabilization approach

- All coverage uses temp directories and `ScriptedLLMProvider`; no network, time, or nondeterministic ordering dependencies.
- Workflow-module cache is cleared per test to avoid cross-test import leakage.

## Known gaps

- No dedicated runtime test for a child `blocked` route yet; the current phase requirement only mandates success-path and child-question runtime proof, while direct seam coverage and the new blocked runtime path cover the highest-risk regression on child readiness.
