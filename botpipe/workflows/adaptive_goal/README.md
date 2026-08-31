# Adaptive Goal

`adaptive_goal` is a goal-constrained, path-free orchestration workflow built on
Botpipe's existing public workflow API.

It deliberately keeps a tiny static Botpipe control graph while allowing the
semantic work graph to emerge at runtime:

```text
initialize
   ↓
orchestrate
   ↓
validate action
   ↓
dispatch child workflow
   ↓
reconcile state / invalidate stale verification
   ├──────────────→ orchestrate
   ├──────────────→ terminal unsatisfied
   ├──────────────→ blocked
   └──────────────→ final global audit
                         ├── reopen → orchestrate
                         ├── blocked
                         └── complete
```

## Design invariants

1. **The mission is immutable.** `mission.json` is snapshotted from typed run
   input. The orchestrator never gets authority to change criteria, thresholds,
   verifier assignments, or constraints.

2. **Only verifiers can supply criterion observations.** A verifier does not
   write `PASS`; it publishes metrics in `verification_result.json`. The parent
   runtime evaluates those metrics against the mission's deterministic
   `AcceptanceRule`s.

3. **PASS is freshness-bound.** A passing receipt records the exact filesystem
   patterns observed by the verifier and a SHA-256 subject fingerprint. Any
   later action that changes that subject automatically marks the criterion
   `STALE`. External/time-sensitive criteria can additionally use a TTL.

4. **Actions and criteria are separate.** Criteria describe what must be true.
   Capabilities describe work that may help make criteria true. The orchestrator
   chooses one next action from current state instead of executing a precomputed
   SOP.

5. **Unknown work does not generate trusted Botpipe Python on the fly.**
   `kind="ad_hoc"` dispatches the pre-authored `ad_hoc_executor` workflow. That
   workflow is sandboxed, workspace-write, no-network, and independently
   verified.

6. **External side effects require preapproval.** Any capability marked
   `external_reversible`, `external_irreversible`, or
   `preapproval_required=true` is rejected unless its id is listed in
   `preapproved_capabilities`.

7. **Final local PASS receipts are not enough.** A fresh global audit verifies
   the original objective/constraints. It may reopen existing criteria, but may
   not invent new mandatory criteria or weaken the mission.

8. **Child workflow output is durable.** Capabilities publish a standard protocol
   artifact in their own Botpipe workflow folder. The parent reads and validates
   that file after `ctx.invoke_workflow(...)`.

## Capability protocol

A registered action capability must write the path named by
`CapabilitySpec.result_artifact` (default `capability_result.json`) using:

```json
{
  "schema": "botpipe.adaptive-goal.action-result/v1",
  "status": "completed",
  "summary": "What happened",
  "evidence": ["artifact/or/command evidence"],
  "changed_paths": ["relative/path"],
  "metrics": {}
}
```

A verifier capability must write `verification_result.json` by default:

```json
{
  "schema": "botpipe.adaptive-goal.verifier-result/v1",
  "status": "observed",
  "verifier_id": "verify.visual",
  "summary": "Visual audit completed.",
  "observations": {
    "visual_quality": {"score": 91},
    "mobile_quality": {"score": 88}
  },
  "evidence": ["qa/mobile.png", "qa/desktop.png"],
  "observed_paths": {
    "visual_quality": ["site/**"],
    "mobile_quality": ["site/**"]
  }
}
```

The verifier's `status="observed"` is intentionally **not** a pass/fail verdict.
The parent evaluates `score >= 85`, or whatever the immutable mission declares.

## Minimal mission

```python
from botpipe import Botpipe
from botpipe.workflows.adaptive_goal import (
    AcceptanceRule,
    AdaptiveGoalInput,
    AdaptiveGoalWorkflow,
    CapabilityRegistry,
    CapabilitySpec,
    MissionCriterion,
    MissionSpec,
)

mission = MissionSpec(
    id="website-redesign",
    objective="Produce a demonstrably superior private redesign.",
    criteria=[
        MissionCriterion(
            id="visual_quality",
            description="The rendered redesign is visually strong.",
            verifier="verify.visual",
            acceptance=[
                AcceptanceRule(metric="score", operator="ge", value=85)
            ],
            observed_paths=["site/**"],
        ),
        MissionCriterion(
            id="redesign_worthwhile",
            description="The existing site has enough improvement opportunity.",
            verifier="verify.current_site",
            acceptance=[
                AcceptanceRule(metric="deficiency_score", operator="ge", value=65)
            ],
            failure_policy="terminal_unsatisfied",
            ttl_seconds=86400,
        ),
    ],
)

registry = CapabilityRegistry(
    capabilities=[
        CapabilitySpec(
            id="design",
            kind="action",
            workflow="website_design",
            description="Improve the website design.",
            helps=["visual_quality"],
            may_invalidate=["visual_quality"],
            side_effect="workspace",
        ),
        CapabilitySpec(
            id="verify.visual",
            kind="verifier",
            workflow="verify_visual",
            description="Score current rendered redesign.",
            verifies=["visual_quality"],
            observed_paths=["site/**"],
        ),
        CapabilitySpec(
            id="verify.current_site",
            kind="verifier",
            workflow="verify_current_site",
            description="Verify that the current official site is a redesign candidate.",
            verifies=["redesign_worthwhile"],
        ),
    ]
)

client = Botpipe(workspace=".", provider="codex")
result = client.run(
    AdaptiveGoalWorkflow,
    "Complete the adaptive mission.",
    input=AdaptiveGoalInput(mission=mission, registry=registry),
    max_steps=0,
)
```

## Action selection

The orchestrator receives only the immutable mission, trusted capability
metadata, blackboard, status report, and verification ledger. It returns one
`ActionRequest`.

Registered action:

```json
{
  "kind": "capability",
  "capability_id": "design",
  "objective": "Repair the weak hero hierarchy found by the visual verifier.",
  "target_criteria": ["visual_quality"],
  "rationale": "visual_quality is FAIL at 78/100.",
  "expected_evidence": ["new desktop/mobile render"]
}
```

Verifier:

```json
{
  "kind": "verifier",
  "capability_id": "verify.visual",
  "objective": "Measure the current redesign after the hero repair.",
  "target_criteria": ["visual_quality"],
  "rationale": "The relevant site files changed and the old receipt is stale.",
  "expected_evidence": ["visual score and screenshots"]
}
```

Unforeseen local action:

```json
{
  "kind": "ad_hoc",
  "objective": "Extract the product taxonomy from the already-downloaded PDF catalogue.",
  "target_criteria": ["information_sufficient"],
  "rationale": "No registered capability handles this local catalogue format.",
  "expected_evidence": ["structured product taxonomy with page references"]
}
```

## Why `ad_hoc_executor` has no network

An arbitrary LLM-authored objective plus unrestricted network is not an
enforceable no-side-effect boundary. Networked research should therefore be a
pre-authored registered capability with an explicit policy and result contract.
The generic ad-hoc escape hatch is intentionally limited to the local workspace.

## Capability promotion

Dynamic actions are not dynamically generated Botpipe workflows. If repeated
ad-hoc traces reveal a stable useful pattern, an offline optimizer may generate a
**candidate** capability workflow. It should be compiled, tested, evaluated
against historical cases, independently reviewed, and only then added to the
trusted capability registry.
